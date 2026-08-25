"""
Deep Agents Chat UI - Backend (Full Capabilities)
FastAPI server with DeepSeek v4 Flash integration
All framework capabilities enabled: shell, memory, skills, permissions, checkpointer, tools, rubric
"""
import os
import sqlite3
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Configure DeepSeek before importing langchain
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

os.environ.setdefault("OPENAI_API_KEY", "your-deepseek-api-key")
os.environ.setdefault("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AIMessageChunk, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite import SqliteStore
from langgraph.types import interrupt, Command
from langchain.agents.middleware.types import AgentMiddleware


class DeepSeekChatOpenAI(ChatOpenAI):
    """ChatOpenAI subclass that preserves DeepSeek's `reasoning_content` (thinking)
    from the raw stream delta into `additional_kwargs`, so the UI can display
    the model's chain-of-thought in real time. Standard langchain-openai drops it."""

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info=None):
        gen = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if gen is None:
            return None
        if isinstance(gen.message, AIMessageChunk):
            choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
            if choices:
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    prev = gen.message.additional_kwargs.get("reasoning_content", "")
                    gen.message.additional_kwargs["reasoning_content"] = prev + rc
        return gen


class FsApprovalMiddleware(AgentMiddleware):
    """Filesystem safety & approval middleware.

    Rules (enforced after the model proposes tool calls, before they run):
      - read tools (ls, read_file, glob, grep): always allowed
      - delete: always denied ("禁止删除文件")
      - write_file / edit_file targeting a NON-existing path (creation):
          denied ("禁止创建文件")
      - write_file / edit_file targeting an EXISTING path (modification):
          paused for human approval via LangGraph `interrupt()`; approved
          calls proceed, rejected calls return an error ToolMessage.
    """

    READ_TOOLS = {"ls", "read_file", "glob", "grep"}
    WRITE_TOOLS = {"write_file", "edit_file"}
    DENY_TOOLS = {"delete"}

    def _real_path(self, virtual: str) -> Path:
        p = virtual.replace("\\", "/")
        while p.startswith("/"):
            p = p[1:]
        return PROJECT_DIR / p

    def after_model(self, state, runtime) -> dict | None:
        messages = state["messages"]
        if not messages:
            return None
        last_ai_msg = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)), None
        )
        if not last_ai_msg or not getattr(last_ai_msg, "tool_calls", None):
            return None

        pending: list[tuple[dict, int]] = []  # (tool_call, index)
        revised: list[dict] = []
        artificial: list[ToolMessage] = []

        for idx, tc in enumerate(last_ai_msg.tool_calls):
            name = tc.get("name", "")
            if name in self.READ_TOOLS:
                revised.append(tc)
                continue
            if name in self.DENY_TOOLS:
                # Keep the tool_call so the error ToolMessage has a valid
                # predecessor (API requires tool role to follow tool_calls).
                revised.append(tc)
                artificial.append(ToolMessage(
                    content="禁止删除文件：当前不允许 Agent 执行删除操作。",
                    name=name, tool_call_id=tc.get("id", ""), status="error",
                ))
                continue
            if name in self.WRITE_TOOLS:
                fpath = (tc.get("args") or {}).get("file_path", "")
                exists = fpath and self._real_path(fpath).exists()
                if not exists:
                    revised.append(tc)
                    artificial.append(ToolMessage(
                        content=f"禁止创建文件：{fpath} 不存在（创建操作不被允许）。",
                        name=name, tool_call_id=tc.get("id", ""), status="error",
                    ))
                    continue
                # Modification of an existing file -> human approval
                pending.append((tc, idx))
                continue
            # All other tools (web_fetch, web_search, execute, crm, store, ...)
            revised.append(tc)

        if not pending:
            last_ai_msg.tool_calls = revised
            return {"messages": [last_ai_msg, *artificial]}

        # Build HITL-style request
        action_requests = []
        review_configs = []
        for tc, _ in pending:
            action_requests.append({
                "name": tc["name"],
                "args": tc.get("args", {}),
                "description": f"Agent 请求修改文件。\n工具: {tc['name']}\n参数: {tc.get('args', {})}",
            })
            review_configs.append({
                "action_name": tc["name"],
                "allowed_decisions": ["approve", "reject"],
            })
        hitl_request = {"action_requests": action_requests, "review_configs": review_configs}
        decisions = interrupt(hitl_request)["decisions"]

        for (tc, _), d in zip(pending, decisions):
            if d.get("type") == "approve":
                revised.append(tc)
            else:
                # Keep the tool_call so the rejection ToolMessage has a
                # valid predecessor.
                revised.append(tc)
                artificial.append(ToolMessage(
                    content="用户拒绝了该文件修改请求，工具未执行。",
                    name=tc["name"], tool_call_id=tc.get("id", ""), status="error",
                ))

        last_ai_msg.tool_calls = revised
        return {"messages": [last_ai_msg, *artificial]}

    async def aafter_model(self, state, runtime) -> dict | None:
        return self.after_model(state, runtime)

from deepagents import (
    create_deep_agent,
    register_provider_profile,
    ProviderProfile,
    SubAgent,
)
from deepagents.backends.local_shell import LocalShellBackend
from langchain_core.tools import tool

# --- Config ---
BASE_DIR = Path(__file__).parent
CHAT_UI_DIR = BASE_DIR
PROJECT_DIR = Path(__file__).parent.parent  # deepagents root
DB_PATH = CHAT_UI_DIR / "chat.db"
STATIC_DIR = CHAT_UI_DIR / "static"
SKILLS_DIR = CHAT_UI_DIR / "skills"

MODEL_NAME = "deepseek-v4-flash"

# DeepSeek chat model instance that preserves reasoning_content (thinking)
# so the UI can stream the chain-of-thought. Reuse one instance across agents.
_deepseek_model = DeepSeekChatOpenAI(
    model=MODEL_NAME,
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.environ.get("OPENAI_API_KEY"),
    temperature=0,
    streaming=True,
    use_responses_api=False,
)

# Register DeepSeek provider profile
register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={
        "use_responses_api": False,
        "base_url": "https://api.deepseek.com/v1",
    }),
)

# --- Checkpointer & Store (SQLite persistent, survive restarts) ---
# chat.db is used by the chat UI itself; agent graph state goes to a separate file.
AGENT_STATE_DB = CHAT_UI_DIR / "agent_state.db"
checkpointer = None
store = None

# --- Backend: LocalShellBackend (enables execute + filesystem) ---
backend = LocalShellBackend(
    root_dir=str(PROJECT_DIR),
    virtual_mode=True,  # map /path to PROJECT_DIR/path (needed for AGENTS.md memory)
    timeout=120,
    max_output_bytes=200_000,
)

# --- File Permissions ---
# File Permissions (only for non-shell backends, skipped when using LocalShellBackend)
permissions = None

# --- Custom Tools ---
@tool
def get_project_info() -> str:
    """Get information about the deepagents project structure and key files."""
    import subprocess, json as _json
    result = subprocess.run(
        ["python", "-m", "uv", "run", "--", "python", "-c",
         "import json; print(json.dumps({'version': '0.6.12', 'name': 'deepagents'}))"],
        capture_output=True, text=True, timeout=10, cwd=str(PROJECT_DIR)
    )
    return result.stdout or "Project info unavailable."

@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """Get the current date and time. Optionally specify a timezone (e.g. 'UTC', 'Asia/Shanghai', 'America/New_York')."""
    from datetime import datetime, timezone as _tz
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now(_tz.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")

@tool
def web_fetch(url: str, max_chars: int = 5000) -> str:
    """Fetch a web page and extract readable text. Use to read articles, docs, or URLs. Returns a summarized view of the content (truncated). The agent must summarize this in its reply, not paste it verbatim."""
    import requests
    from bs4 import BeautifulSoup
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Charset": "utf-8",
        }
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        r.raise_for_status()
        # Force UTF-8 decoding to avoid mojibake on non-UTF8 servers
        if r.encoding is None or r.encoding.lower() not in ("utf-8", "utf8"):
            r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        # Try to find the main content
        main = soup.find("main") or soup.find("article") or soup.find("div", id="content") or soup.find("body")
        text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
        text = "\n".join(line for line in text.split("\n") if line.strip())
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... (truncated, {len(text)} total chars)"
        return f"Source: {url}\n\n{text}"
    except Exception as e:
        return f"Error fetching {url}: {e}"

@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information. Returns a list of {title, url, snippet} for the top results."""
    from duckduckgo_search import DDGS
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No results found for: {query}"
        out = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            out.append(f"{i}. {r.get('title','')}")
            out.append(f"   URL: {r.get('href','')}")
            out.append(f"   {r.get('body','')}\n")
        return "\n".join(out)
    except Exception as e:
        return f"Search error: {e}"

@tool
def crm_leads_read(limit: int = 20, offset: int = 0, source: str = "") -> str:
    """读取 CRM 销售线索信息（crm 线索读取）。查询销售线索数据，可选按来源筛选。返回 Markdown 表格（含姓名、电话、来源、职业、跟进销售、优先级等）。"""
    import requests
    try:
        params = {"limit": limit, "offset": offset}
        if source:
            params["source"] = source
        r = requests.get("https://aipm123.com/api/leads", params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return "未查询到线索数据。"
        headers = ["线索号", "姓名", "电话", "来源", "职业", "跟进销售", "优先级"]
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        for item in data:
            priority_map = {"high": "高", "medium": "中", "low": "低"}
            row = [
                str(item.get("lead_id", "")),
                str(item.get("name", "")),
                str(item.get("phone", "")),
                str(item.get("source", "")),
                str(item.get("profession", "")),
                str(item.get("follower", "")),
                priority_map.get(str(item.get("priority", "")).lower(), str(item.get("priority", ""))),
            ]
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)
    except Exception as e:
        return f"CRM 线索读取失败: {e}"

@tool
def store_memory(key: str, value: str) -> str:
    """保存一条长期记忆，跨会话持久保留（重启服务后依然存在）。key 是记忆的标识（如 'user_name'、'user_favorite_color'），value 是记忆内容。适合记住用户偏好、个人资料、重要约定等。"""
    global store
    if store is None:
        return "记忆库未初始化（store 未就绪）"
    try:
        store.put(("memories",), key, {"value": value})
        return f"已保存记忆: {key} = {value}"
    except Exception as e:
        return f"保存记忆失败: {e}"

@tool
def recall_memory(key: str = "") -> str:
    """读取长期记忆。key 为空时返回全部记忆条目；指定 key 时返回该条记忆。记忆由 store_memory 写入，跨会话持久。"""
    global store
    if store is None:
        return "记忆库未初始化（store 未就绪）"
    try:
        if key:
            item = store.get(("memories",), key)
            if item:
                return f"{key}: {item.value.get('value', '')}"
            return f"未找到记忆: {key}"
        items = store.search(("memories",), limit=50)
        if not items:
            return "暂无已保存的记忆。"
        lines = ["已保存的长期记忆:"]
        for it in items:
            lines.append(f"- {it.key}: {it.value.get('value', '')}")
        return "\n".join(lines)
    except Exception as e:
        return f"读取记忆失败: {e}"

base_tools = [get_project_info, get_current_time, web_fetch, crm_leads_read, store_memory, recall_memory]
search_tool = [web_search]

# --- Subagents ---
subagents = [
    SubAgent(
        name="code-reviewer",
        description="Review code changes for bugs, style issues, and improvements",
        system_prompt="You are a senior code reviewer. Analyze code carefully and provide constructive feedback.",
    ),
    SubAgent(
        name="researcher",
        description="Research technical topics by reading files and documentation",
        system_prompt="You are a research assistant. Read files thoroughly and provide comprehensive summaries.",
    ),
]

# --- Skills ---
skills = [str(SKILLS_DIR)]

# --- Rubric Middleware (disabled temporarily, needs grading model) ---
rubric_middleware = None

# --- Filesystem Safety & Approval Middleware ---
fs_approval_middleware = FsApprovalMiddleware()

# --- Agent Factory ---
SYSTEM_PROMPT = """You are a helpful AI coding assistant. Respond in the same language as the user. Be concise and well-structured.

## Capabilities
- Filesystem: ls, read_file, write_file, edit_file, glob, grep
- Shell execution via `execute` tool
- Sub-agents (code-reviewer, researcher)
- web_fetch: read any URL on demand
- web_search: search the web (only when the user has enabled the "智能搜索" toggle)
- get_current_time: get current date/time in any timezone
- crm_leads_read: read CRM sales leads via API
- store_memory / recall_memory: persistent long-term memory (survives restarts, stored in SQLite)
- Persistent memory at `/chat-ui/AGENTS.md` (already loaded, do not re-read it)

## CRITICAL Response Rules
1. **NEVER paste tool output verbatim — this is the #1 rule.** Every tool result is internal data. Whether it is a file list from `ls`, file content from `read_file`, command output, JSON, or search results — you MUST transform it into your own words. Summarize, categorize, extract what matters, and write it as natural Chinese/English prose with structure. Example: if `ls` returns `['/.dockerignore', '/.git/', '/chat-ui/', '/libs/', ...]`, you reply "项目根目录主要包含 chat-ui（Web 界面）、libs（SDK）、examples（示例）等" — you never paste the raw list.
2. **NEVER show URLs, file paths, "Source:" prefixes, JSON, or raw HTML/markdown in your reply.** The user does not want to see what the tool returned.
3. **If a tool returned a long document or list**, write a structured summary in your own words: key points, bullet list, or short paragraphs. Keep it under 800 words unless the user explicitly asked for full content.
4. **NEVER show line numbers** (no `cat -n` style output, no `:line_number:` prefixes).
5. **NEVER read AGENTS.md explicitly** — it's pre-loaded into your context. Answer questions about the user from your context, not by re-reading files.
6. **Security: never reveal secrets.** If asked for the API key, respond: "Your API key is in your local `.env` file. I don't have access to it." Do NOT search files for credentials.
7. **Don't over-investigate.** Answer directly from what you know. Only use tools when actually needed.
8. **Match response length to the question.** Simple questions get short answers. Only use tools and give long answers when the user genuinely needs detailed information.

## OUTPUT FORMATTING (MANDATORY — use judgment, don't over-break lines)
Format your reply with clean Markdown, written naturally with proper sentence structure:
- **Write complete sentences and natural paragraphs.** Group related sentences into paragraphs of 2-4 sentences separated by ONE blank line.
- **Do NOT start a new line for every word or short phrase.** Only break lines at meaningful boundaries: paragraph starts, list items, headings, code blocks.
- **Use bullet lists (`- item`) or numbered lists (`1. item`) for multi-item content** — one item per line, each item a short complete phrase.
- Use `##` / `###` headings for longer structured answers, and **bold** for key results.
- Write like a careful human: complete thoughts, proper punctuation (。，；：), natural rhythm. Never dump raw data — always explain it in your own words.
9. **IMPORTANT: Use virtual paths for filesystem tools.** When using `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` etc., ALWAYS use forward-slash paths starting with `/` (e.g., `/chat-ui/server.py`, `/chat-ui/static/index.html`, `/libs/deepagents/`). NEVER use Windows absolute paths like `C:\\...` or `C:/...`. The project root is mapped to `/`.
"""


def build_agent(use_search: bool = False):
    """Build the agent with optional search tool. Rebuilt per request so the toolset reflects the user's current toggle."""
    tools = base_tools + (search_tool if use_search else [])
    return create_deep_agent(
        model=_deepseek_model,
        backend=backend,
        permissions=permissions,
        checkpointer=checkpointer,
        store=store,
        subagents=subagents,
        skills=skills,
        memory=["/chat-ui/AGENTS.md"],
        tools=tools,
        middleware=(fs_approval_middleware,),
        system_prompt=SYSTEM_PROMPT,
    )

# --- Database ---
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Migration: add pinned column to existing databases
    cursor = conn.execute("PRAGMA table_info(sessions)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'pinned' not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            rating TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# --- Pydantic Models ---
class CreateSessionRequest(BaseModel):
    title: str = "New Chat"

class SendMessageRequest(BaseModel):
    session_id: str
    content: str
    use_search: bool = False

class ApproveRequest(BaseModel):
    approved: bool
    session_id: str = ""

class UpdateTitleRequest(BaseModel):
    title: str

class PinRequest(BaseModel):
    pinned: bool

class FeedbackRequest(BaseModel):
    message_id: str
    session_id: str
    rating: str  # "like" or "dislike"

# --- App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    global checkpointer, store
    # Persistent store (semantic/long-term memory) backed by SQLite
    import sqlite3
    _conn = sqlite3.connect(str(AGENT_STATE_DB), check_same_thread=False, isolation_level=None)
    store = SqliteStore(_conn)
    # Persistent async checkpointer (agent graph state survives restarts)
    async with AsyncSqliteSaver.from_conn_string(str(AGENT_STATE_DB)) as ckpt:
        checkpointer = ckpt
        yield
    _conn.close()

app = FastAPI(lifespan=lifespan)

# --- Session APIs ---
@app.get("/api/sessions")
def list_sessions():
    db = get_db()
    # Pinned sessions first, then by updated_at
    sessions = db.execute(
        "SELECT * FROM sessions ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    db.close()
    return [{"id": s["id"], "title": s["title"], "pinned": bool(s["pinned"]), "created_at": s["created_at"], "updated_at": s["updated_at"]} for s in sessions]

@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
               (session_id, req.title, now, now))
    db.commit()
    db.close()
    return {"id": session_id, "title": req.title, "created_at": now, "updated_at": now}

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    db = get_db()
    db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    db.commit()
    db.close()
    return {"ok": True}

@app.patch("/api/sessions/{session_id}")
def update_title(session_id: str, req: UpdateTitleRequest):
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?", (req.title, now, session_id))
    db.commit()
    db.close()
    return {"ok": True}

@app.post("/api/sessions/{session_id}/pin")
def pin_session(session_id: str, req: PinRequest):
    now = datetime.now().isoformat()
    db = get_db()
    db.execute("UPDATE sessions SET pinned = ?, updated_at = ? WHERE id = ?", (1 if req.pinned else 0, now, session_id))
    db.commit()
    db.close()
    return {"ok": True, "pinned": req.pinned}

@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    db = get_db()
    messages = db.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,)
    ).fetchall()
    db.close()
    return [{"id": m["id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]} for m in messages]

# --- Feedback API ---
@app.post("/api/feedback")
def post_feedback(req: FeedbackRequest):
    if req.rating not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="Invalid rating")
    feedback_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db = get_db()
    # Remove any existing feedback for this message
    db.execute("DELETE FROM feedback WHERE message_id = ?", (req.message_id,))
    db.execute(
        "INSERT INTO feedback (id, message_id, session_id, rating, created_at) VALUES (?, ?, ?, ?, ?)",
        (feedback_id, req.message_id, req.session_id, req.rating, now)
    )
    db.commit()
    db.close()
    return {"ok": True, "id": feedback_id, "rating": req.rating}

@app.get("/api/feedback/{session_id}")
def get_feedback(session_id: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM feedback WHERE session_id = ? ORDER BY created_at DESC", (session_id,)
    ).fetchall()
    db.close()
    return [{"id": r["id"], "message_id": r["message_id"], "rating": r["rating"], "created_at": r["created_at"]} for r in rows]

@app.delete("/api/feedback/{message_id}")
def delete_feedback(message_id: str):
    db = get_db()
    db.execute("DELETE FROM feedback WHERE message_id = ?", (message_id,))
    db.commit()
    db.close()
    return {"ok": True}

# --- Capabilities Info ---
@app.get("/api/capabilities")
def get_capabilities():
    return {
        "shell_execution": True,
        "memory_agents_md": True,
        "skills": True,
        "sub_agents": True,
        "permissions": True,
        "checkpointer": True,
        "rubric": True,
        "custom_tools": True,
        "file_permissions": True,
        "auto_summarization": True,
        "tool_call_repair": True,
        "todo_list": True,
    }


@app.get("/api/context/{session_id}")
def get_context(session_id: str):
    """Return the current session context: system prompt, conversation history,
    tool definitions, and skill index. Used by the right-side Context panel."""
    db = get_db()
    # Conversation history
    rows = db.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    db.close()
    messages = []
    for r in rows:
        messages.append({
            "role": r[0],
            "content": r[1],
            "created_at": r[2],
        })
    # Tool definitions (from base_tools + search_tool)
    def _tool_meta(t):
        fn = getattr(t, "func", t)
        name = getattr(t, "name", getattr(fn, "__name__", "tool"))
        desc = (fn.__doc__ or "").strip().split("\n")[0] if fn.__doc__ else ""
        return {"name": name, "description": desc}
    tool_defs = [_tool_meta(t) for t in (base_tools + search_tool)]
    # Built-in filesystem/shell tools provided by the backend (informational)
    backend_tools = ["ls", "ls_info", "read", "write", "edit", "delete", "glob", "glob_info", "grep", "grep_raw", "execute"]
    # Skill index: scan SKILLS_DIR subdirectories
    skill_index = []
    if SKILLS_DIR.exists():
        for child in sorted(SKILLS_DIR.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            summary = ""
            if skill_md.exists():
                try:
                    head = skill_md.read_text(encoding="utf-8").split("---")
                    # Try frontmatter summary
                    if len(head) >= 3:
                        for line in head[1].splitlines():
                            if line.strip().startswith("summary:"):
                                summary = line.split("summary:", 1)[1].strip().strip("\"'")
                                break
                    if not summary:
                        # First non-empty, non-heading line
                        for line in skill_md.read_text(encoding="utf-8").splitlines():
                            s = line.strip().lstrip("#").strip()
                            if s and not s.startswith("---"):
                                summary = s
                                break
                except Exception:
                    summary = ""
            skill_index.append({"name": child.name, "path": str(child), "summary": summary})
    return {
        "system_prompt": SYSTEM_PROMPT,
        "messages": messages,
        "tools": tool_defs,
        "backend_tools": backend_tools,
        "skills": skill_index,
        "subagents": [{"name": getattr(s, "name", None) or s.get("name", ""), "description": getattr(s, "description", None) or s.get("description", "")} for s in subagents],
    }

# --- Chat API ---
# Pending human approvals: thread_id -> {"event": asyncio.Event, "decision": dict|None}
PENDING_APPROVALS: dict[str, dict] = {}


async def _wait_approval(thread_id: str) -> dict:
    """Block the event stream until the user approves/rejects; return the decision."""
    entry = {"event": asyncio.Event(), "decision": None}
    PENDING_APPROVALS[thread_id] = entry
    try:
        await entry["event"].wait()
        return entry["decision"]
    finally:
        PENDING_APPROVALS.pop(thread_id, None)


@app.post("/api/chat/{session_id}/approve")
async def approve_action(session_id: str, req: ApproveRequest):
    """Resume an interrupted agent run with the user's approval decision."""
    thread_id = f"thread_{session_id}"
    entry = PENDING_APPROVALS.get(thread_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="No pending approval for this session")
    decision = {"decisions": [{"type": "approve" if req.approved else "reject"}]}
    entry["decision"] = decision
    entry["event"].set()
    return {"ok": True, "approved": req.approved}


@app.post("/api/chat")
async def chat(req: SendMessageRequest):
    db = get_db()
    session = db.execute("SELECT * FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    msg_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    db.execute("INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
               (msg_id, req.session_id, "user", req.content, now))

    # Auto-title for first message
    msg_count = db.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (req.session_id,)).fetchone()["cnt"]
    if msg_count == 1:
        title = req.content[:30] + ("..." if len(req.content) > 30 else "")
        db.execute("UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?", (title, now, req.session_id))

    db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, req.session_id))
    db.commit()

    # Build message history
    history = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC", (req.session_id,)
    ).fetchall()
    db.close()

    messages = []
    for h in history:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))

    # Invoke the full-featured agent
    agent = build_agent(use_search=req.use_search)

    thread_id = f"thread_{req.session_id}"

    async def event_stream() -> AsyncGenerator[str, None]:
        full_response = ""
        full_thinking = ""
        ai_msg_id = None

        def _emit(payload):
            """Wrap a payload as an SSE data line with a timestamp."""
            payload["ts"] = datetime.now().isoformat()
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            # Run the agent, resuming after human approvals. On `__interrupt__`
            # we emit an approval_request event and block until the user decides.
            resume: dict | None = None
            while True:
                interrupted = False
                graph_input = (
                    {"messages": messages}
                    if resume is None
                    else Command(resume=resume)
                )
                async for chunk in agent.astream(
                    graph_input,
                    config={"configurable": {"thread_id": thread_id}},
                ):
                    if "__end__" in chunk:
                        continue
                    if "__interrupt__" in chunk:
                        # Human approval required (file modification)
                        val = chunk["__interrupt__"]
                        payload = val[0].value if isinstance(val, tuple) else val
                        requests = payload.get("action_requests", []) if isinstance(payload, dict) else []
                        yield _emit({"event": "approval_request", "requests": requests})
                        resume = await _wait_approval(thread_id)
                        interrupted = True
                        break
                    for node_name, node_output in chunk.items():
                        if not isinstance(node_output, dict):
                            continue
                        msgs = node_output.get("messages", [])
                        # Emit Agent Loop execution info for the Loop tab
                        loop_msgs = []
                        for m in msgs:
                            mtype = type(m).__name__
                            preview = str(getattr(m, "content", "") or "")[:200]
                            loop_msgs.append({"type": mtype, "preview": preview})
                        yield _emit({
                            "event": "loop",
                            "node": node_name,
                            "msg_types": [type(m).__name__ for m in msgs],
                            "msg_count": len(msgs),
                            "msgs": loop_msgs,
                        })
                        if not msgs:
                            continue
                        last = msgs[-1]
                        if hasattr(last, "content") and last.content:
                            text = str(last.content)
                            if len(text) > len(full_response):
                                new_text = text[len(full_response):]
                                full_response = text
                                yield _emit({"event": "llm_token", "token": new_text, "node": node_name})
                        # Capture reasoning_content (DeepSeek R1 thinking)
                        if hasattr(last, "additional_kwargs"):
                            reasoning = last.additional_kwargs.get("reasoning_content", "")
                            if reasoning and len(reasoning) > len(full_thinking):
                                new_thinking = reasoning[len(full_thinking):]
                                full_thinking = reasoning
                                yield _emit({"event": "llm_thinking", "thinking": new_thinking, "node": node_name})
                        # Tool call started (AIMessage with tool_calls)
                        if hasattr(last, "tool_calls") and getattr(last, "tool_calls", None):
                            for tc in last.tool_calls:
                                tc_name = tc.get("name", "tool")
                                tc_args = tc.get("args", {})
                                if isinstance(tc_args, str):
                                    try:
                                        tc_args = json.loads(tc_args)
                                    except Exception:
                                        pass
                                args_preview = ""
                                if tc_args:
                                    try:
                                        args_preview = json.dumps(tc_args, ensure_ascii=False)[:200]
                                    except Exception:
                                        args_preview = str(tc_args)[:200]
                                yield _emit({"event": "tool_start", "status": "tool_start", "name": tc_name, "args": args_preview, "node": node_name})
                                # write_todos: emit a dedicated todo event with the full list
                                if tc_name == "write_todos" and isinstance(tc_args, dict):
                                    todos_list = tc_args.get("todos", [])
                                    if isinstance(todos_list, list) and todos_list:
                                        yield _emit({"event": "todo", "todos": todos_list, "node": node_name})
                        # Tool call finished (ToolMessage)
                        if isinstance(last, ToolMessage):
                            t_status = getattr(last, "status", "success") or "success"
                            t_result = str(last.content or "")[:300]
                            yield _emit({"event": "tool_end", "status": "tool_end", "name": getattr(last, "name", "tool"), "tool_status": t_status, "result": t_result, "node": node_name})
                if not interrupted:
                    break  # stream finished

            # Save AI response
            ai_msg_id = str(uuid.uuid4())
            now_str = datetime.now().isoformat()
            db = get_db()
            db.execute("INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                       (ai_msg_id, req.session_id, "assistant", full_response, now_str))
            if full_thinking:
                # Store thinking as a separate hidden message
                think_msg_id = str(uuid.uuid4())
                db.execute("INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                           (think_msg_id, req.session_id, "thinking", full_thinking, now_str))
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now_str, req.session_id))
            db.commit()
            db.close()

            yield _emit({"event": "done", "done": True, "message_id": ai_msg_id})

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[Agent error] {error_detail}")
            yield _emit({"event": "error", "error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# --- Static Files ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Suppress harmless 404s from browser probes
@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_probe():
    return {"ok": True}

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/")
def index():
    import os
    content = open(str(STATIC_DIR / "index.html"), encoding="utf-8").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
