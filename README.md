<div align="center">
  <img src=".github/images/logo-dark.svg" width="40%" alt="Deep Agents Logo">
</div>

# Deep Agents - 本地部署 Chat UI

<div align="center">
  <p>基于 <a href="https://github.com/langchain-ai/deepagents">Deep Agents</a> 框架的本地部署版 Web 聊天界面，接入 DeepSeek v4 Flash 模型。</p>
</div>

<br>

## 概述

本项目是 LangChain **Deep Agents** 框架的本地部署版本，附带一个自定义的 Web 聊天界面（类似 DeepSeek Chat 或 ChatGPT）。

### 核心能力

- **Web 聊天界面** — 浏览器端会话管理、流式输出、消息历史，按时间自动分组
- **完整框架能力** — Shell 执行、文件系统访问、子 Agent、技能系统、持久化记忆等
- **联网搜索** — 输入框左下角可开关的「智能搜索」按钮，基于 DuckDuckGo（无需 API Key）
- **网页抓取** — Agent 可自动读取任意 URL 内容并摘要
- **日期/时间感知** — Agent 知晓当前日期和时间，支持任意时区
- **DeepSeek 集成** — 通过 OpenAI 兼容 API 接入 DeepSeek v4 Flash
- **本地运行** — 完全在本地执行，无云端依赖

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装依赖

```bash
# 安装各包的依赖
cd libs/deepagents && uv sync --all-groups
cd ../code && uv sync --all-groups
cd ../cli && uv sync --all-groups
cd ../../chat-ui
```

### 配置模型

创建 `chat-ui/.env` 文件（不会上传到 GitHub）：

```ini
OPENAI_API_KEY=你的deepseek_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

参考 `chat-ui/.env.example` 模板。

### 启动

```bash
# 方式一：启动 Web Chat UI（推荐）
cd chat-ui
start.bat                          # 或双击 start.bat
# 浏览器打开 http://localhost:8765

# 方式二：Python SDK 交互模式
python run_agent.py

# 方式三：dcode 终端编码助手
run_dcode.bat                      # CMD
# 或
run_dcode.ps1                      # PowerShell
```

## Chat UI 功能

| 功能 | 说明 |
|------|------|
| **会话管理** | 新建、内联重命名、删除（确认弹窗）。按置顶/今天/7天/30天/月自动分组 |
| **会话置顶** | 右键或 ⋮ 按钮 → 置顶/取消置顶，置顶的会话固定在顶部区域 |
| **联网搜索开关** | 输入框左下角的「智能搜索」胶囊按钮，默认关闭，点击开启 |
| **流式输出** | 实时逐字输出，可点击红色停止按钮中断 |
| **消息操作** | 每条消息支持复制、重新生成、点赞/点踩（记录到数据库） |
| **思考过程** | 可折叠显示模型的推理过程（取决于模型是否支持） |
| **跨会话记忆** | Agent 通过读写 AGENTS.md 文件实现跨会话记忆 |
| **右键菜单** | 右键或点击 ⋮ 按钮可重命名、置顶/取消置顶、删除 |
| **删除确认** | 删除会话时弹出居中确认弹窗（取消/删除该对话） |

## Agent 自定义工具

| 工具 | 始终可用 | 说明 |
|------|---------|------|
| `get_current_time` | ✅ | 获取当前日期时间，支持指定时区（默认 Asia/Shanghai） |
| `web_fetch` | ✅ | 抓取任意 URL 并提取正文纯文本（自动摘要，无需开关） |
| `web_search` | ⏹ 需开启搜索 | DuckDuckGo 搜索，返回5条标题+URL+摘要，无需 API Key |
| `get_project_info` | ✅ | 查看项目结构信息和版本 |

## 已启用的框架能力

| 能力 | 状态 |
|------|------|
| Shell 执行 (`execute`) | ✅ 已启用 |
| 文件系统工具 (ls, read, write, edit, glob, grep) | ✅ 已启用 |
| 框架记忆 (AGENTS.md) | ✅ 已启用 |
| 技能系统 (Skills) | ✅ 已启用 |
| 子 Agent (同步: code-reviewer, researcher) | ✅ 已启用 |
| 状态检查点 (Checkpointer) | ✅ 已启用 |
| 自动摘要 (Auto-summarization) | ✅ 已启用 |
| 工具调用修复 (Tool call repair) | ✅ 已启用 |
| 任务清单 (Todo List) | ✅ 已启用 |
| 人工介入 (Human-in-the-loop) | ⏳ 可选配置 |
| 异步子 Agent | ⏳ 需要远程服务器 |
| 评分系统 (Rubric) | ⏳ 可选配置 |

## 项目结构

```
├── chat-ui/                          # Web 聊天界面
│   ├── server.py                     # FastAPI 后端（Agent 逻辑 + API）
│   ├── start.bat                     # 启动脚本
│   ├── .env                          # 模型配置（本地，不上传）
│   ├── .env.example                  # 配置模板
│   ├── AGENTS.md                     # Agent 记忆文件
│   ├── chat.db                       # SQLite 数据库（自动创建，不上传）
│   ├── skills/                       # Agent 技能
│   │   └── project-analyzer/         # 项目分析技能
│   └── static/
│       └── index.html                # 前端页面（单页应用）
├── libs/                             # Deep Agents SDK（LangChain 官方，未修改）
│   ├── deepagents/                   # 核心 SDK
│   ├── code/                         # dcode 终端 Agent
│   └── cli/                          # CLI 工具
├── launch_dcode.py                   # dcode Python 封装（含 DeepSeek 配置）
├── run_agent.py                      # Python SDK 交互模式
├── run_dcode.bat                     # dcode 启动脚本 (CMD)
├── run_dcode.ps1                     # dcode 启动脚本 (PowerShell)
├── .gitignore                        # 排除 .env / chat.db / .venv
└── README.md                         # 本文件
```

## 常见问题

### API Key 如何配置？
创建 `chat-ui/.env` 文件写入 `OPENAI_API_KEY=你的key`，server.py 启动时自动读取。不要修改 `.env.example`。

### 如何关闭联网搜索？
默认关闭。输入框左下角的「智能搜索」按钮，点击可切换开启/关闭。

### 数据存在哪里？
SQLite 文件：`chat-ui/chat.db`。删除此文件即清空所有会话记录。

### 如何更改模型？
修改 `chat-ui/server.py` 中的 `MODEL_NAME = "你的模型名"`，及 `.env` 中的 `OPENAI_BASE_URL`。

## 许可证

本项目基于 **Deep Agents** by LangChain，遵循 [MIT 许可协议](LICENSE)。

- 原始 Deep Agents 代码版权归 LangChain, Inc. 所有
- Chat UI 及附加脚本同样遵循 MIT 许可协议
