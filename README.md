<div align="center">
  <img src=".github/images/logo-dark.svg" width="40%" alt="Deep Agents Logo">
</div>

# Deep Agents - 本地部署 Chat UI

<div align="center">
  <p>基于 <a href="https://github.com/langchain-ai/deepagents">Deep Agents</a> 框架的本地部署版 Web 聊天界面，接入 DeepSeek v4 Flash 模型。</p>
</div>

<br>

## 概述

本项目是 LangChain **Deep Agents** 框架的本地部署版本，附带一个自定义的 Web 聊天界面（类似 DeepSeek Chat 或 ChatGPT）。提供以下能力：

- **Web 聊天界面** — 浏览器端会话管理、流式输出、消息历史
- **完整框架能力** — Shell 执行、文件系统访问、子 Agent、技能系统、持久化记忆等
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

启动前设置环境变量：

```bash
set OPENAI_API_KEY=你的deepseek_api_key
set OPENAI_BASE_URL=https://api.deepseek.com/v1
```

### 启动

```bash
# 方式一：启动 Web Chat UI
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
| **会话管理** | 新建、重命名（内联编辑）、删除会话。按今天/7天/30天/月分组 |
| **会话置顶** | 将重要会话固定在顶部 |
| **流式输出** | 实时逐字输出，可点击停止按钮中断 |
| **消息操作** | 每条消息支持复制、重新生成、点赞/点踩 |
| **思考过程** | 可折叠显示模型的推理过程（取决于模型是否支持） |
| **跨会话记忆** | Agent 通过读写 AGENTS.md 文件实现跨会话记忆 |
| **删除确认** | 删除会话时弹出居中确认弹窗，防止误删 |
| **右键菜单** | 右键或点击 ⋮ 按钮可重命名、置顶/取消置顶、删除 |

## 已启用的框架能力

| 能力 | 状态 |
|------|------|
| Shell 执行 (`execute`) | ✅ 已启用 |
| 文件系统工具 (ls, read, write, edit, glob, grep) | ✅ 已启用 |
| 框架记忆 (AGENTS.md) | ✅ 已启用 |
| 技能系统 (Skills) | ✅ 已启用 |
| 子 Agent (同步) | ✅ 已启用 |
| 状态检查点 (Checkpointer) | ✅ 已启用 |
| 自定义工具 | ✅ 已启用 |
| 自动摘要 | ✅ 已启用 |
| 工具调用修复 | ✅ 已启用 |
| 任务清单 (Todo List) | ✅ 已启用 |
| 人工介入 (Human-in-the-loop) | ⏳ 可选配置 |
| 异步子 Agent | ⏳ 需要远程服务器 |
| 评分系统 (Rubric) | ⏳ 可选配置 |

## 项目结构

```
├── chat-ui/                          # Web 聊天界面
│   ├── server.py                     # FastAPI 后端
│   ├── start.bat                     # 启动脚本
│   ├── AGENTS.md                     # Agent 记忆文件
│   ├── chat.db                       # SQLite 数据库（自动创建）
│   ├── skills/                       # Agent 技能
│   │   └── project-analyzer/         # 项目分析技能
│   └── static/
│       └── index.html                # 前端页面
├── libs/                             # Deep Agents SDK（未修改）
│   ├── deepagents/                   # 核心 SDK
│   ├── code/                         # dcode 终端 Agent
│   └── cli/                          # CLI 工具
├── launch_dcode.py                   # dcode Python 封装
├── run_agent.py                      # Python SDK 交互模式
├── run_dcode.bat                     # dcode 启动脚本 (CMD)
└── run_dcode.ps1                     # dcode 启动脚本 (PowerShell)
```

## 许可证

本项目基于 **Deep Agents** by LangChain，遵循 [MIT 许可协议](LICENSE)。

- 原始 Deep Agents 代码版权归 LangChain, Inc. 所有
- Chat UI 及附加脚本同样遵循 MIT 许可协议
