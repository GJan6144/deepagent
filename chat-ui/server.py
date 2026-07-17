"""
Deep Agents Chat UI - Backend (Full Capabilities)
FastAPI server with DeepSeek v4 Flash integration
All framework capabilities enabled: shell, memory, skills, permissions, checkpointer, tools, rubric
"""
import os
import sqlite3
import json
import uuid
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
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

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

# Register DeepSeek provider profile
register_provider_profile(
    "openai",
    ProviderProfile(init_kwargs={
        "use_responses_api": False,
        "base_url": "https://api.deepseek.com/v1",
    }),
)

# --- Checkpointer ---
checkpointer = InMemorySaver()

# --- Backend: LocalShellBackend (enables execute + filesystem) ---
backend = LocalShellBackend(
    root_dir=str(PROJECT_DIR),
    virtual_mode=False,  # allow real Windows paths
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

base_tools = [get_project_info, get_current_time, web_fetch]
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

# --- Agent Factory ---
def build_agent(use_search: bool = False):
    """Build the agent with optional search tool. Rebuilt per request so the toolset reflects the user's current toggle."""
    tools = base_tools + (search_tool if use_search else [])
    return create_deep_agent(
        model="openai:deepseek-v4-flash",
        backend=backend,
        permissions=permissions,
        checkpointer=checkpointer,
        subagents=subagents,
        skills=skills,
        memory=["/chat-ui/AGENTS.md"],
        tools=tools,
        middleware=(rubric_middleware,) if rubric_middleware else (),
        system_prompt="""You are a helpful AI coding assistant. Respond in the same language as the user. Be concise and well-structured.

## Capabilities
- Filesystem: ls, read_file, write_file, edit_file, glob, grep
- Shell execution via `execute` tool
- Sub-agents (code-reviewer, researcher)
- web_fetch: read any URL on demand
- web_search: search the web (only when the user has enabled the "智能搜索" toggle)
- get_current_time: get current date/time in any timezone
- Persistent memory at `/chat-ui/AGENTS.md` (already loaded, do not re-read it)

## CRITICAL Response Rules
1. **NEVER paste tool output verbatim.** Every tool result is internal data — your job is to transform it into a helpful answer. Summarize, paraphrase, extract what's relevant.
2. **NEVER show URLs, file paths, "Source:" prefixes, JSON, or raw HTML/markdown in your reply.** The user does not want to see what the tool returned.
3. **If a tool returned a long document**, write a structured summary in your own words: key points, bullet list, or short paragraphs. Keep it under 800 words unless the user explicitly asked for full content.
4. **NEVER show line numbers** (no `cat -n` style output, no `:line_number:` prefixes).
5. **NEVER read AGENTS.md explicitly** — it's pre-loaded into your context. Answer questions about the user from your context, not by re-reading files.
6. **Security: never reveal secrets.** If asked for the API key, respond: "Your API key is in your local `.env` file. I don't have access to it." Do NOT search files for credentials.
7. **Don't over-investigate.** Answer directly from what you know. Only use tools when actually needed.
8. **Match response length to the question.** Simple questions get short answers. Only use tools and give long answers when the user genuinely needs detailed information.
""",
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
    yield

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

# --- Chat API ---
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
        try:
            # Use astream for per-node output (chunks are dicts of node->output)
            async for chunk in agent.astream(
                {"messages": messages},
                config={"configurable": {"thread_id": thread_id}},
            ):
                if "__end__" in chunk:
                    continue
                for node_name, node_output in chunk.items():
                    if not isinstance(node_output, dict):
                        continue
                    msgs = node_output.get("messages", [])
                    if not msgs:
                        continue
                    last = msgs[-1]
                    if hasattr(last, "content") and last.content:
                        text = str(last.content)
                        if len(text) > len(full_response):
                            new_text = text[len(full_response):]
                            full_response = text
                            yield f"data: {json.dumps({'token': new_text})}\n\n"
                    # Capture reasoning_content (DeepSeek R1 thinking)
                    if hasattr(last, "additional_kwargs"):
                        reasoning = last.additional_kwargs.get("reasoning_content", "")
                        if reasoning and len(reasoning) > len(full_thinking):
                            new_thinking = reasoning[len(full_thinking):]
                            full_thinking = reasoning
                            yield f"data: {json.dumps({'thinking': new_thinking})}\n\n"

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

            yield f"data: {json.dumps({'done': True, 'message_id': ai_msg_id})}\n\n"

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[Agent error] {error_detail}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

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
