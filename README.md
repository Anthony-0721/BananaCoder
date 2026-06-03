# BananaCoder

A personal AI coding assistant built from scratch with Python asyncio — pure CLI, no LangChain.

## Features

**LLM**
- Multi-provider: OpenAI-compatible + Anthropic with automatic fallback chains
- Prompt caching with Anthropic `cache_control` markers
- Streaming token output with Rich rendering

**Tools**
- Bash execution with 3-mode security sandbox (normal / fast / yolo)
- File operations: read, write, edit (with diff preview)
- File state tracking — warns before editing unread files
- Self-inspection tool for runtime state queries
- Code search: glob and regex grep
- Web: Tavily search + fetch (with SSRF protection)
- Subagent dispatch: Explore, Plan, general-purpose agents
- MCP (Model Context Protocol) client: stdio, SSE, streamableHttp transports
- TodoWrite for task tracking
- AskUser for interactive confirmation

**Context Management**
- 3-layer compression: snip (50%) → summarize (70%) → collapse (90%)
- Auto-triggered per LLM round based on token threshold
- Context window percentage tracking in token stats
- Configurable `context_window_tokens` from config.json
- Session persistence with atomic writes

**Agent**
- Configurable max tool rounds (default 50)
- Per-turn token stats with timing
- Task planning guidance in system prompt
- Edit diff preview via unified diff format
- Runtime state introspection for self-awareness

**Security**
- 3 tiers: `normal` (safe=auto, write=confirm, unknown=block) / `fast` (safe+write=auto) / `yolo` (all auto)
- Configurable pattern whitelist/blacklist
- SSRF protection: blocks private/internal IP URLs
- Optional workspace restriction for file and bash operations

**CLI**
- Interactive REPL with `prompt_toolkit` input history and Rich output
- Slash command system: `/help`, `/clear`, `/session`, `/status`, `/mode`, `/model`, `/memory`, `/remember`, `/forget`, `/export`, `/history`, `/tool`, `/skill`
- CommandRouter with 4-level dispatch (priority → exact → prefix → interceptor)
- Single-shot mode: `banana "explain this code"`

**Memory & Hooks**
- Persistent memory via `MEMORY.md` file with `/remember` and `/forget` commands
- Hook system with 6 lifecycle methods: `on_chat_start`, `on_chat_end`, `on_tool_start`, `on_tool_end`, `on_token`, `on_error`

**Skills**
- Loadable skill files (SKILL.md) from `.banana/skills/` or `~/.bananacoder/skills/`
- `always` skills auto-injected into system prompt

## Installation

```bash
# Requirements: Python 3.11+
git clone https://github.com/Anthony-0721/BananaCoder.git
cd BananaCoder
pip install -e .
```

## Configuration

Create `~/.bananacoder/config.json`:

```json
{
  "providers": {
    "openai": {
      "api_key": "sk-...",
      "api_base": "https://api.openai.com/v1"
    },
    "deepseek": {
      "api_key": "sk-...",
      "api_base": "https://api.deepseek.com/v1"
    }
  },
  "model_presets": {
    "default": {
      "model": "deepseek-chat",
      "provider": "deepseek",
      "max_tokens": 8192,
      "temperature": 0.7
    }
  },
  "fallback_models": ["gpt-4o-mini"],
  "fallback_providers": {
    "gpt-4o-mini": "openai"
  },
  "tools": {
    "tavily_api_key": "tvly-..."
  },
  "security": {
    "mode": "normal",
    "restrict_to_workspace": true
  },
  "agent": {
    "max_tool_rounds": 50,
    "max_tool_result_chars": 80000
  },
  "mcp_servers": {}
}
```

Environment variables are supported via `${VAR_NAME}` syntax in config values.

## Usage

```bash
# Interactive REPL
banana

# Single-shot
banana "what does git status do?"

# Specific session
banana --session my-project
```

In the REPL, type `/help` to see all available commands.

## MCP Servers

Configure MCP servers in `~/.bananacoder/config.json` under `mcp_servers`:

```json
{
  "mcp_servers": {
    "bailian": {
      "type": "streamableHttp",
      "url": "https://your-mcp-server.com/mcp",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

Supported transports: `stdio`, `sse`, `streamableHttp`.

## Project Structure

```
banana/
├── agent/          # Agent loop, runner, context compression, subagent
├── cli/            # App entry point, display, command router + builtins
├── command/        # CommandRouter with tiered dispatch
├── config/         # Pydantic config models + loader
├── memory/         # Persistent memory store (MEMORY.md)
├── providers/      # OpenAI-compat + Anthropic + factory + fallback
├── security/       # Sandbox modes, SSRF protection
├── session/        # Session persistence with atomic writes
├── skills/         # SKILL.md loader
└── tools/          # Bash, filesystem, search, web, MCP, agent, ask, todo, skill, memory
```

## Development

```bash
pip install -e ".[dev]"

# Run tests with coverage report
python run_tests.py

# Run tests only (no coverage)
python run_tests.py --quick

# Generate HTML coverage report
python run_tests.py --html
```

## Credits

BananaCoder draws design inspiration from:
- [nanobot](https://github.com/nanobot) — LLM provider, messagebus, MCP, and tool systems
- [CoreCoder](https://github.com/he-yufeng/CoreCoder) — Claude Code reverse-engineered design
- [chcode](https://github.com/flymohan/chcode) — CLI AI coding assistant patterns
