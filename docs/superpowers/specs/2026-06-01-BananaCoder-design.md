# BananaCoder 设计文档

## 概述

BananaCoder 是一个纯 CLI 的 AI 编程助手，Python asyncio 从零搭建。核心架构借鉴 nanobot 的 Provider/Tool 系统和 CoreCoder 的 Agent 简洁性。

### 参考来源

| 层 | 主要参考 | 理由 |
|----|----------|------|
| Provider | nanobot 90% | 多 provider + fallback + 智能重试成熟 |
| Agent Loop | CoreCoder 70% + nanobot 30% | 简单循环 + 并行工具 + 空响应恢复 |
| Tool System | nanobot 80% | ToolRegistry + Schema 校验 + 缓存排序 |
| Context | CoreCoder 60% + nanobot 40% | 3层压缩 + autocompact |
| Session | 自研 | 比 nanobot 简（不需 channel），比 CoreCoder 全 |
| Skill | nanobot 90% | SKILL.md + requirements 检查 + always 机制 |
| MCP | nanobot 95% | 完整 stdio/SSE/HTTP 客户端 + tools/resources/prompts 自动注册 |

---

## 架构总览

```
                    ┌──────────┐
                    │   CLI    │  用户交互、Rich 渲染
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │  Agent   │  对话循环、子代理、上下文
                    └─┬───┬───┘
                      │   │
           ┌──────────▼┐ ┌▼──────────┐
           │  Provider │ │   Tools   │  LLM 多 provider   │ 工具注册 & Skill
           │  + fallback│ │  + MCP    │  + fallback 链      │ + MCP 自动注册
           └───────────┘ └─────┬─────┘
                               │
                      ┌────────▼────────┐
                      │    Session      │  持久化、压缩
                      └─────────────────┘
```

依赖方向：CLI → Agent → {Provider, Tools, Session}。每层只依赖下层抽象。

### 数据流

```
User Input
  → Agent.loop()
    → session.load()        # 恢复历史
    → context.compress()    # 压缩超长上下文
    → AgentRunner.run()
      → provider.chat_stream()  # LLM 调用（流式）
        → content → 流式输出
        → tool_calls → 并行执行
      → 循环直到无 tool_call 或超限
    → session.save()        # 持久化
  → 输出最终回复
```

---

## 模块设计

### 1. Provider 层

#### 1.1 核心数据结构 (`providers/base.py`)

```python
@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest]
    finish_reason: str = "stop"        # stop | tool_calls | error | length
    usage: dict[str, int]
    reasoning_content: str | None = None    # DeepSeek-R1 / Kimi
    thinking_blocks: list[dict] | None = None  # Anthropic extended thinking
    # 结构化错误（用于重试决策）
    error_status_code: int | None = None
    error_type: str | None = None
    error_should_retry: bool | None = None
    retry_after: float | None = None

@dataclass
class GenerationSettings:
    temperature: float = 0.7
    max_tokens: int = 4096
    reasoning_effort: str | None = None
```

#### 1.2 Provider 抽象基类

`LLMProvider` ABC 定义契约：
- 子类必须实现：`chat()`, `get_default_model()`
- 子类可选覆盖：`chat_stream()`（默认回退到非流式）
- 基类提供：`chat_with_retry()`, `chat_stream_with_retry()`

基类内置通用逻辑（全部继承自 nanobot）：
- 智能重试：standard 模式最多 3 次 [1s, 2s, 4s]，persistent 模式持续重试最长 60s
- 可重试：429(rate_limit), 408, 409, 5xx, timeout, connection
- 不可重试：429(quota_exceeded), 400, 401, 403
- 消息 sanitize：修复空 content、合并同 role 消息、去掉末尾 assistant
- 图片降级：不支持图片的 provider 自动替换为占位文本

#### 1.3 Provider 实现

- `OpenAICompatProvider`：覆盖 90% 模型（DeepSeek/Qwen/Kimi/GLM/Ollama...）
- `AnthropicProvider`：Anthropic 原生 SDK，支持 extended thinking
- `FallbackProvider`：主模型失败自动切备用，对 Agent 透明

#### 1.4 Provider Factory

`make_provider(config)` 从配置创建 provider chain：
主 provider + 可选 fallback 列表 → FallbackProvider 包装

### 2. Agent 层

#### 2.1 Agent 主循环 (`agent/loop.py`)

```python
class Agent:
    def __init__(self, provider, tools, session, config):
        ...

    async def chat(self, user_input, *, on_token=None, on_tool=None) -> str:
        messages = await self.session.load()
        messages.append({"role": "user", "content": user_input})
        await self._context.compress(messages, self.provider)

        runner = AgentRunner(provider, tools, subagent_manager, config)
        result = await runner.run(messages, on_token=on_token, on_tool=on_tool)

        await self.session.save(messages)
        return result
```

#### 2.2 AgentRunner (`agent/runner.py`)

LLM ↔ Tools 多轮循环：
1. 构建 system prompt（含 skills 摘要）
2. 调用 provider.chat_stream_with_retry()
3. 纯文本 → 返回结果
4. 有 tool_calls → 并行执行（concurrency_safe 并行，exclusive 串行）
5. tool results 追加到 messages，继续循环
6. 最大轮次保护（默认 50）

#### 2.3 Subagent (`agent/subagent.py`)

预定义类型：Explore（只读探索）、Plan（方案设计）、general-purpose（通用）

- 共享 provider（含 fallback 能力）
- 独立 messages 历史（隔离执行）
- 可选工具过滤（read_only 子代理只能调用只读工具）
- 超时控制（默认 300s）

#### 2.4 上下文管理 (`agent/context.py`)

3 层压缩策略：
- Layer 1 (50%)：截断超长工具结果（>1500 字符保留首尾）
- Layer 2 (70%)：LLM 摘要旧对话（保留最近 8 条）
- Layer 3 (90%)：硬压缩（保留摘要 + 最近 4 条）

### 3. Tool 层

#### 3.1 Tool 抽象 (`tools/base.py`)

```python
class Tool(ABC):
    name: str          # 工具名称
    description: str   # 描述
    parameters: dict   # JSON Schema
    read_only: bool = False
    concurrency_safe: bool = False
    exclusive: bool = False

    async def execute(self, **kwargs) -> Any: ...
    def to_schema(self) -> dict: ...  # OpenAI function calling 格式
```

`@tool_parameters(schema)` 类装饰器自动注入 parameters property。

#### 3.2 ToolRegistry (`tools/registry.py`)

- `register(tool)` / `unregister(name)`
- `get_definitions()` — 稳定排序（builtin 按名称 + mcp_ 按名称），带缓存
- `prepare_call(name, params)` — cast → validate
- `execute(name, params)` — 完整执行流程

#### 3.3 第一期内置工具

| 工具 | 功能 | 并发 |
|------|------|------|
| bash | Shell 执行（Git Bash / PowerShell 自适应） | exclusive |
| read_file | 读取文件 | concurrency_safe |
| write_file | 写入文件 | exclusive |
| edit | 精确文本替换 | exclusive |
| glob | 文件名模式匹配 | concurrency_safe |
| grep | 正则内容搜索 | concurrency_safe |
| web_search | 网络搜索 | concurrency_safe |
| web_fetch | 获取网页内容 | concurrency_safe |
| agent | 启动子代理 | exclusive |
| ask_user | 交互式问答 | exclusive |
| todo_write | 任务列表管理 | exclusive |
| load_skill | 加载 Skill 完整指令 | concurrency_safe |

#### 3.4 MCP 客户端 (`tools/mcp.py`)

完整移植 nanobot 的 MCP 实现，支持三种传输方式：

**传输方式**：
- `stdio`：本地进程通信（command + args + env）
- `SSE`：HTTP Server-Sent Events
- `streamableHttp`：HTTP Streamable Transport

**自动注册机制**：

`connect_mcp_servers(mcp_config, registry)` 在 Agent 启动时调用：

1. 遍历配置的 MCP 服务器
2. 根据 `type` 字段选择传输方式（自动推断：有 command → stdio，URL 以 /sse 结尾 → SSE，其他 → streamableHttp）
3. 建立连接 → 初始化 ClientSession
4. 遍历服务器的 tools → 包装为 `MCPToolWrapper` → `registry.register()`
5. 遍历服务器的 resources → 包装为 `MCPResourceWrapper` → `registry.register()`
6. 遍历服务器的 prompts → 包装为 `MCPPromptWrapper` → `registry.register()`
7. 返回 `dict[name, AsyncExitStack]` 用于生命周期管理

**包装器设计**：

```python
class MCPToolWrapper(Tool):
    """将 MCP tool 包装为 BananaCoder Tool"""
    _plugin_discoverable = False
    # name: mcp_{server_name}_{tool_name}（sanitize 处理特殊字符）
    # description: 来自 MCP tool 定义
    # parameters: 来自 MCP tool inputSchema（自动适配 OpenAI 格式）
    # execute(): 调用 MCP session.call_tool()，含超时 + 重试

class MCPResourceWrapper(Tool):
    """将 MCP resource 包装为只读 Tool"""
    # execute(): 调用 MCP session.read_resource(uri)

class MCPPromptWrapper(Tool):
    """将 MCP prompt 包装为只读 Tool"""
    # execute(): 调用 MCP session.get_prompt(name, arguments)
```

**鲁棒性处理（全部借鉴 nanobot）**：

- 连接前 HTTP 探测（`_probe_http_url`）：避免进入 anyio cancel scope 后崩溃
- Windows stdio 包装：`npx`/`npm` 等通过 `cmd.exe /d /c` 启动
- 工具名 sanitize：非 `[a-zA-Z0-9_-]` 字符替换为 `_`
- Schema 适配：MCP 的 nullable union type → OpenAI 兼容格式
- 可启用/禁用单个工具：`enabled_tools: ["*"]` 或 `["tool_a", "tool_b"]`
- 未匹配工具警告
- 瞬断重试（1 次）：`ClosedResourceError`/`BrokenResourceError`/`ConnectionResetError` 等
- 超时控制：每个工具独立可配 `tool_timeout`
- 每个服务器独立 AsyncExitStack：避免 cancel scope 冲突

**配置模型**：

```json
// ~/.bananacoder/config.json
{
  "mcp_servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-filesystem", "."],
      "enabled_tools": ["*"],
      "tool_timeout": 30
    },
    "database": {
      "type": "streamableHttp",
      "url": "http://localhost:3000/mcp",
      "headers": {"Authorization": "Bearer xxx"},
      "enabled_tools": ["query", "list_tables"],
      "tool_timeout": 60
    }
  }
}
```

### 4. Skill 层

#### 4.1 Skill 规范

Skill 目录结构：
```
<skill-name>/
├── SKILL.md          # 必需：YAML frontmatter + Markdown 指令
├── scripts/          # 可选：可执行脚本
├── references/       # 可选：参考文档
└── assets/           # 可选：模板和资源
```

SKILL.md 格式：
```markdown
---
name: my-skill
description: 当用户需要做 X 时使用此 skill
metadata:
  nanobot:
    always: false
    requires:
      bins: [git]
      env: [GITHUB_TOKEN]
---

# Skill 指令内容
...
```

#### 4.2 搜索路径（参考 nanobot）

```
项目级: .banana/skills/<name>/SKILL.md     （优先，项目专属）
用户级: ~/.bananacoder/skills/<name>/SKILL.md （全局可用）
```

项目级覆盖用户级同名 skill。

#### 4.3 SkillsLoader (`skills/loader.py`)

核心方法：

- `list_skills(filter_unavailable=True)` — 扫描所有 skill 目录，解析 frontmatter
- `load_skill(name)` — 加载完整 SKILL.md 内容（去除 frontmatter）
- `build_skills_summary(exclude)` — 生成摘要注入 system prompt
- `get_always_skills()` — 返回标记 always=true 且满足依赖的 skill
- `load_skills_for_context(names)` — 按名称批量加载完整内容
- `_check_requirements(meta)` — 检查 CLI 工具和环境变量依赖

always 技能在 Agent 启动时自动注入 system prompt，无需 LLM 调用 load_skill。

#### 4.4 load_skill 工具 (`tools/skill_tool.py`)

注册为 Tool，LLM 判断用户意图匹配 skill 描述时调用，返回完整指令内容。

### 5. Session 层

#### 5.1 存储模型

```
~/.bananacoder/
├── config.json
├── sessions/
│   ├── index.json              # session 索引（按项目分组）
│   └── <session_id>/
│       ├── messages.json       # 完整消息历史
│       └── meta.json           # 元信息
```

- 每个项目目录自动关联一个 default session
- 同一项目可创建多个命名 session
- 原子写入（写临时文件 → fsync → rename）

#### 5.2 SessionManager (`session/manager.py`)

```python
class SessionManager:
    async def load(session_id="default") -> Session
    async def save(session)
    async def switch(session_id)
    async def new(session_id) -> Session
    async def delete(session_id)
    async def list_sessions() -> list[dict]
    async def compact(session, provider)    # 后台自动压缩
```

自动压缩触发条件：
- messages > 100 条
- 估算 token > context_window * 0.7
- 空闲 > 30s 后台执行

压缩策略：保留最近 20 条 → LLM 摘要旧对话 → 替换为摘要

### 6. CLI 层

#### 6.1 两种运行模式

```bash
# 单次执行
$ banana "解释这个文件"
$ banana --session bugfix "修这个 bug"
$ banana --model deepseek-chat "写个爬虫"

# 交互式 REPL
$ banana
> 帮我看看项目结构
> /session list
> /model qwen-plus
> exit
```

#### 6.2 交互模式

- prompt_toolkit 输入（多行编辑、历史）
- Rich 渲染流式输出（Markdown 高亮）
- 工具调用状态实时显示
- Ctrl+C 中断当前生成

#### 6.3 斜杠命令

```
/session list|new|switch|delete
/model [name]
/config
/yolo on|off
/clear
/status
/exit
```

---

## 项目结构

```
bananacoder/
├── pyproject.toml
├── banana/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── app.py              # CLI 主入口 + 交互循环
│   │   └── display.py          # Rich 格式化输出
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # LLMProvider ABC + LLMResponse
│   │   ├── openai_compat.py    # OpenAI 兼容 provider
│   │   ├── anthropic.py        # Anthropic 原生 provider
│   │   ├── fallback.py         # FallbackProvider
│   │   └── factory.py          # make_provider()
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py             # Agent 主循环
│   │   ├── runner.py           # AgentRunner（LLM ↔ Tools）
│   │   ├── subagent.py         # 子代理管理
│   │   └── context.py          # 上下文压缩
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Tool ABC + tool_parameters
│   │   ├── registry.py         # ToolRegistry
│   │   ├── bash.py
│   │   ├── filesystem.py       # read_file + write_file + edit
│   │   ├── search.py           # glob + grep
│   │   ├── web.py              # web_search + web_fetch
│   │   ├── agent_tool.py       # subagent 启动工具
│   │   ├── ask.py              # ask_user
│   │   ├── todo.py             # todo_write
│   │   ├── skill_tool.py       # load_skill
│   │   └── mcp.py              # MCP 客户端
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py           # SkillsLoader
│   ├── session/
│   │   ├── __init__.py
│   │   └── manager.py          # SessionManager
│   └── config/
│       ├── __init__.py
│       ├── schema.py           # Pydantic 配置模型
│       └── loader.py           # 配置加载
└── tests/
    └── ...
```

---

## 依赖

```
# pyproject.toml
[project]
dependencies = [
    "openai>=1.0",          # OpenAI 兼容 provider
    "anthropic>=0.30",      # Anthropic provider
    "pydantic>=2.0",        # 配置模型
    "rich>=13.0",           # 终端渲染
    "prompt-toolkit>=3.0",  # 交互输入
    "httpx>=0.27",          # HTTP 客户端
    "pyyaml>=6.0",          # Skill frontmatter 解析
    "loguru>=0.7",          # 日志
    "aiofiles>=24.0",       # 异步文件 IO
    "mcp>=1.0",             # MCP SDK
    "json-repair>=0.30",    # 修复 LLM 输出的畸形 JSON
]
```

---

## 配置示例

```json
// ~/.bananacoder/config.json
{
  "providers": {
    "deepseek": {
      "api_key": "sk-xxx",
      "api_base": "https://api.deepseek.com/v1"
    },
    "anthropic": {
      "api_key": "sk-ant-xxx"
    }
  },
  "model_presets": {
    "default": {
      "model": "deepseek-chat",
      "provider": "deepseek",
      "max_tokens": 8192,
      "temperature": 0.7,
      "context_window_tokens": 128000
    }
  },
  "fallback_models": [
    {"model": "qwen-plus", "provider": "openai_compat", "api_base": "https://..."}
  ],
  "tools": {
    "disabled": []
  },
  "mcp_servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-filesystem", "."],
      "enabled_tools": ["*"],
      "tool_timeout": 30
    }
  },
  "agent": {
    "max_tool_rounds": 50,
    "max_tool_result_chars": 80000
  }
}
```
