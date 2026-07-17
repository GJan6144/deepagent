# Deep Agents - Local Chat UI

<div align="center">
  <p>A locally deployed <a href="https://github.com/langchain-ai/deepagents">Deep Agents</a> with a web-based Chat UI, powered by DeepSeek v4 Flash.</p>
</div>

<div align="center">
  <img src=".github/images/logo-dark.svg" width="40%" alt="Deep Agents Logo">
</div>

<br>

## Overview

This project is a local deployment of LangChain's **Deep Agents** framework with a custom web chat interface, similar to DeepSeek Chat or ChatGPT. It provides:

- **Web Chat UI** — browser-based chat interface with session management, streaming responses, and message history
- **Full Framework Capabilities** — shell execution, filesystem access, sub-agents, skills, memory, and more
- **DeepSeek Integration** — uses DeepSeek v4 Flash via OpenAI-compatible API
- **Local Deployment** — runs entirely on your machine, no cloud dependencies

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Install dependencies for each package
cd libs/deepagents && uv sync --all-groups
cd ../code && uv sync --all-groups
cd ../cli && uv sync --all-groups
cd ../../chat-ui
```

### Configure Model

Set environment variables before starting:

```bash
set OPENAI_API_KEY=your_deepseek_api_key
set OPENAI_BASE_URL=https://api.deepseek.com/v1
```

### Run

```bash
# Option 1: Start Chat UI
start.bat       # or double-click start.bat

# Option 2: Python SDK interactive mode
python run_agent.py

# Option 3: dcode terminal agent
run_dcode.bat   # or run_dcode.ps1
```

Then open **http://localhost:8765** in your browser.

## Chat UI Features

| Feature | Description |
|---------|-------------|
| **Session Management** | Create, rename, delete conversations. Sessions grouped by Today / 7 days / 30 days / Monthly |
| **Pin Sessions** | Pin important conversations to the top |
| **Streaming Responses** | Real-time token streaming with stop button |
| **Message Actions** | Copy, regenerate, like/dislike feedback per message |
| **Thinking Display** | Collapsible reasoning/thinking section (model-dependent) |
| **Cross-session Memory** | AGENTS.md stores user info across conversations |
| **Inline Rename** | Click to edit conversation titles directly |
| **Delete Confirmation** | Not-destructive delete with confirmation modal |

## Capabilities

This deployment enables all Deep Agents framework capabilities:

| Capability | Status |
|------------|--------|
| Shell Execution (`execute`) | ✅ Enabled |
| Filesystem Tools (ls, read, write, edit, glob) | ✅ Enabled |
| Framework Memory (AGENTS.md) | ✅ Enabled |
| Skills System | ✅ Enabled |
| Sub-Agents (sync) | ✅ Enabled |
| Checkpointer | ✅ Enabled |
| Custom Tools | ✅ Enabled |
| Auto Summarization | ✅ Enabled |
| Tool Call Repair | ✅ Enabled |
| Todo List | ✅ Enabled |
| Human-in-the-loop | ⏳ Optional |
| Async Sub-Agents | ⏳ Needs remote server |
| Rubric Evaluation | ⏳ Optional |

## Project Structure

```
├── chat-ui/                      # Web Chat UI
│   ├── server.py                 # FastAPI backend
│   ├── start.bat                 # Launch script
│   ├── AGENTS.md                 # Agent memory file
│   ├── chat.db                   # SQLite database (auto-created)
│   ├── skills/                   # Agent skills
│   │   └── project-analyzer/     # Project analysis skill
│   └── static/
│       └── index.html            # Frontend
├── libs/                         # Deep Agents SDK (unmodified)
│   ├── deepagents/               # Core SDK
│   ├── code/                     # dcode terminal agent
│   └── cli/                      # CLI tools
├── launch_dcode.py               # dcode Python wrapper
├── run_agent.py                  # Python SDK interactive mode
├── run_dcode.bat                 # dcode launcher (CMD)
└── run_dcode.ps1                 # dcode launcher (PowerShell)
```

## License

This project is based on **Deep Agents** by LangChain, licensed under the [MIT License](LICENSE).

The original Deep Agents code is Copyright (c) LangChain, Inc. — see [LICENSE](LICENSE) for details.

The Chat UI and additional tooling in this repository are provided under the same MIT license.
