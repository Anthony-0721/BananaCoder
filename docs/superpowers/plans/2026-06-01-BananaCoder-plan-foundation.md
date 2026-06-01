# BananaCoder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure CLI AI coding assistant with multi-provider LLM support, fallback chains, MCP integration, subagents, skills, and session management.

**Architecture:** Python asyncio from scratch. Provider layer (nanobot-style) fills the engine room; Agent layer (CoreCoder-style) keeps the loop simple; Tool layer (nanobot-style) provides the extensibility surface. Dependency direction: CLI → Agent → {Provider, Tools, Session}.

**Tech Stack:** Python 3.11+, asyncio, openai SDK, anthropic SDK, mcp SDK, pydantic, rich, prompt-toolkit, httpx, pyyaml, loguru, aiofiles, json-repair

---

## File Structure Map

```
bananacoder/
├── pyproject.toml
├── banana/
│   ├── __init__.py
│   ├── __main__.py                    # python -m banana entry
│   ├── config/
│   │   ├── __init__.py
│   │   ├── schema.py                  # Pydantic models: Config, ProviderConfig, ModelPresetConfig, MCPServerConfig
│   │   └── loader.py                  # load_config(), resolve_env_vars()
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                    # LLMResponse, ToolCallRequest, GenerationSettings, LLMProvider ABC
│   │   ├── openai_compat.py           # OpenAICompatProvider
│   │   ├── anthropic.py               # AnthropicProvider
│   │   ├── fallback.py                # FallbackProvider
│   │   └── factory.py                 # make_provider(config)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                    # Tool ABC, Schema, tool_parameters decorator
│   │   ├── registry.py                # ToolRegistry
│   │   ├── bash.py                    # BashTool
│   │   ├── filesystem.py              # ReadFileTool, WriteFileTool, EditTool
│   │   ├── search.py                  # GlobTool, GrepTool
│   │   ├── web.py                     # WebSearchTool, WebFetchTool
│   │   ├── agent_tool.py              # AgentTool (subagent launcher)
│   │   ├── ask.py                     # AskUserTool
│   │   ├── todo.py                    # TodoWriteTool
│   │   ├── skill_tool.py              # LoadSkillTool
│   │   └── mcp.py                     # MCPToolWrapper, MCPResourceWrapper, MCPPromptWrapper, connect_mcp_servers()
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py                  # SkillsLoader
│   ├── session/
│   │   ├── __init__.py
│   │   └── manager.py                 # Session, SessionManager
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── context.py                 # ContextManager (3-layer compression)
│   │   ├── runner.py                  # AgentRunner (LLM <-> tools loop)
│   │   ├── subagent.py                # SubagentManager, AgentDefinition
│   │   └── loop.py                    # Agent (main orchestrator)
│   └── cli/
│       ├── __init__.py
│       ├── display.py                 # Display (Rich rendering, streaming)
│       └── app.py                     # BananaApp (argparse, REPL, slash commands)
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_provider_base.py
    ├── test_provider_openai.py
    ├── test_provider_fallback.py
    ├── test_tool_registry.py
    ├── test_tools.py
    ├── test_mcp.py
    ├── test_skills_loader.py
    ├── test_session.py
    ├── test_context.py
    ├── test_agent_runner.py
    └── test_cli.py
```

---

## Task Group 1: Project Scaffolding

### Task 1: Initialize project structure

**Files:**
- Create: `pyproject.toml`
- Create: `banana/__init__.py`
- Create: `banana/__main__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bananacoder"
version = "0.1.0"
description = "A personal AI coding assistant"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0",
    "anthropic>=0.30",
    "pydantic>=2.0",
    "rich>=13.0",
    "prompt-toolkit>=3.0",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "loguru>=0.7",
    "aiofiles>=24.0",
    "mcp>=1.0",
    "json-repair>=0.30",
]

[project.scripts]
banana = "banana.cli.app:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
]
```

- [ ] **Step 2: Create banana/__init__.py**

```python
"""BananaCoder - A personal AI coding assistant."""
__version__ = "0.1.0"
```

- [ ] **Step 3: Create banana/__main__.py**

```python
"""Allow running as python -m banana."""
from banana.cli.app import main

main()
```

- [ ] **Step 4: Create all empty __init__.py files for package structure**

```
banana/config/__init__.py
banana/providers/__init__.py
banana/tools/__init__.py
banana/skills/__init__.py
banana/session/__init__.py
banana/agent/__init__.py
banana/cli/__init__.py
```

All contain: empty or `"""Package docstring."""`

- [ ] **Step 5: Create tests/conftest.py with async fixture support**

```python
import pytest
from pathlib import Path
import tempfile
import os


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_home():
    """Mock HOME for config/session tests."""
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        os.environ["HOME"] = d
        os.environ["USERPROFILE"] = d
        yield Path(d)
        if old:
            os.environ["HOME"] = old
            os.environ["USERPROFILE"] = old
```

- [ ] **Step 6: Install in dev mode and verify**

```bash
cd e:/BananaCoder && pip install -e ".[dev]" 2>&1 | tail -5
```
Expected: Successfully installed bananacoder

---

## Task Group 2: Config Layer

### Task 2: Config schema

**Files:**
- Create: `banana/config/schema.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for Config model**

```python
# tests/test_config.py
import pytest
from banana.config.schema import (
    ProviderConfig,
    ModelPresetConfig,
    MCPServerConfig,
    AgentConfig,
    Config,
)


class TestProviderConfig:
    def test_minimal_provider(self):
        p = ProviderConfig(api_key="sk-xxx")
        assert p.api_key == "sk-xxx"
        assert p.api_base is None

    def test_full_provider(self):
        p = ProviderConfig(
            api_key="sk-xxx",
            api_base="https://api.deepseek.com/v1",
            extra_headers={"X-Custom": "value"},
            extra_body={"stream": True},
        )
        assert p.api_base == "https://api.deepseek.com/v1"
        assert p.extra_headers == {"X-Custom": "value"}


class TestModelPresetConfig:
    def test_defaults(self):
        m = ModelPresetConfig(model="deepseek-chat", provider="deepseek")
        assert m.max_tokens == 4096
        assert m.temperature == 0.7
        assert m.context_window_tokens == 128000

    def test_to_generation_settings(self):
        m = ModelPresetConfig(
            model="deepseek-chat",
            provider="deepseek",
            temperature=0.3,
            max_tokens=8192,
            reasoning_effort="high",
        )
        gs = m.to_generation_settings()
        assert gs.temperature == 0.3
        assert gs.max_tokens == 8192
        assert gs.reasoning_effort == "high"


class TestMCPServerConfig:
    def test_stdio_server(self):
        cfg = MCPServerConfig(
            type="stdio",
            command="npx",
            args=["-y", "mcp-server"],
            enabled_tools=["*"],
        )
        assert cfg.type == "stdio"
        assert cfg.command == "npx"

    def test_http_server(self):
        cfg = MCPServerConfig(
            type="streamableHttp",
            url="http://localhost:3000/mcp",
            headers={"Authorization": "Bearer xxx"},
            enabled_tools=["query"],
        )
        assert cfg.url == "http://localhost:3000/mcp"
        assert cfg.enabled_tools == ["query"]


class TestConfig:
    def test_minimal_config(self):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek")
            },
        )
        assert cfg.model_presets["default"].model == "deepseek-chat"

    def test_resolve_preset(self, temp_dir):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
                "fast": ModelPresetConfig(model="deepseek-chat", provider="deepseek", max_tokens=1024),
            },
        )
        resolved = cfg.resolve_preset("fast")
        assert resolved.max_tokens == 1024

    def test_get_provider_name(self):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
            },
        )
        preset = cfg.model_presets["default"]
        assert cfg.get_provider_name("deepseek-chat", preset=preset) == "deepseek"

    def test_fallback_models(self):
        cfg = Config(
            providers={
                "deepseek": ProviderConfig(api_key="sk-xxx"),
                "qwen": ProviderConfig(api_key="sk-yyy", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"),
            },
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
            },
            fallback_models=["qwen-plus"],
            fallback_providers={"qwen-plus": "qwen"},
        )
        assert cfg.fallback_models == ["qwen-plus"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd e:/BananaCoder && python -m pytest tests/test_config.py -v 2>&1 | tail -20
```
Expected: ModuleNotFoundError for banana.config.schema

- [ ] **Step 3: Write banana/config/schema.py**

```python
"""Pydantic config models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None
    region: str | None = None
    profile: str | None = None


class ModelPresetConfig(BaseModel):
    model: str
    provider: str
    max_tokens: int = 4096
    temperature: float = 0.7
    reasoning_effort: str | None = None
    context_window_tokens: int = 128000

    def to_generation_settings(self) -> GenerationSettings:
        from banana.providers.base import GenerationSettings
        return GenerationSettings(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
        )


class MCPServerConfig(BaseModel):
    type: str = ""  # "stdio", "sse", "streamableHttp"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    url: str = ""
    headers: dict[str, str] | None = None
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])
    tool_timeout: int = 30


class AgentConfig(BaseModel):
    max_tool_rounds: int = 50
    max_tool_result_chars: int = 80000


class ToolsConfig(BaseModel):
    disabled: list[str] = Field(default_factory=list)


class Config(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_presets: dict[str, ModelPresetConfig] = Field(default_factory=dict)
    fallback_models: list[str] = Field(default_factory=list)
    fallback_providers: dict[str, str] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    def resolve_preset(self, name: str | None) -> ModelPresetConfig:
        return self.model_presets[name or "default"]

    def get_provider_name(self, model: str, *, preset: ModelPresetConfig) -> str:
        return preset.provider

    def get_provider(self, model: str, *, preset: ModelPresetConfig) -> ProviderConfig:
        name = self.get_provider_name(model, preset=preset)
        return self.providers.get(name, ProviderConfig())

    def get_api_key(self, model: str, *, preset: ModelPresetConfig) -> str:
        p = self.get_provider(model, preset=preset)
        return p.api_key

    def get_api_base(self, model: str, *, preset: ModelPresetConfig) -> str | None:
        p = self.get_provider(model, preset=preset)
        return p.api_base
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd e:/BananaCoder && python -m pytest tests/test_config.py -v 2>&1 | tail -20
```
Expected: all pass

### Task 3: Config loader

**Files:**
- Create: `banana/config/loader.py`
- Modify: `tests/test_config.py` (add loader tests)

- [ ] **Step 1: Add loader tests to tests/test_config.py**

```python
import json
from banana.config.loader import load_config, resolve_env_vars


class TestConfigLoader:
    def test_load_from_path(self, temp_home):
        config_dir = temp_home / ".bananacoder"
        config_dir.mkdir(parents=True)
        cfg = {
            "providers": {"deepseek": {"api_key": "sk-xxx"}},
            "model_presets": {"default": {"model": "deepseek-chat", "provider": "deepseek"}},
        }
        (config_dir / "config.json").write_text(json.dumps(cfg))

        result = load_config(config_dir / "config.json")
        assert result.providers["deepseek"].api_key == "sk-xxx"

    def test_load_defaults(self):
        result = load_config(None)
        assert isinstance(result, Config)

    def test_resolve_env_vars(self):
        import os
        os.environ["TEST_KEY"] = "env-value"
        cfg = Config(
            providers={"test": ProviderConfig(api_key="$TEST_KEY")},
            model_presets={"default": ModelPresetConfig(model="m", provider="test")},
        )
        resolved = resolve_env_vars(cfg)
        assert resolved.providers["test"].api_key == "env-value"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd e:/BananaCoder && python -m pytest tests/test_config.py::TestConfigLoader -v 2>&1 | tail -10
```

- [ ] **Step 3: Write banana/config/loader.py**

```python
"""Config loading from disk with env-var interpolation."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from banana.config.schema import Config


def _default_config_path() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "~"
    return Path(home).expanduser() / ".bananacoder" / "config.json"


def load_config(path: Path | None = None) -> Config:
    """Load config from JSON file. Returns defaults if file doesn't exist."""
    target = path or _default_config_path()
    if not target.exists():
        return Config()
    raw = json.loads(target.read_text(encoding="utf-8"))
    return Config.model_validate(raw)


def resolve_env_vars(config: Config) -> Config:
    """Replace $VAR and ${VAR} patterns in provider values with env-var values."""

    def _resolve(val: str) -> str:
        pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)|\$\{([^}]+)\}")
        def _replacer(m: re.Match) -> str:
            var = m.group(1) or m.group(2)
            return os.environ.get(var, "")
        return pattern.sub(_replacer, val)

    providers = {}
    for name, p in config.providers.items():
        providers[name] = p.model_copy(update={
            "api_key": _resolve(p.api_key) if p.api_key else p.api_key,
            "api_base": _resolve(p.api_base) if p.api_base else p.api_base,
        })

    return config.model_copy(update={"providers": providers})
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd e:/BananaCoder && python -m pytest tests/test_config.py::TestConfigLoader -v
```

---

## Task Group 3: Provider Layer

### Task 4: Provider base types

**Files:**
- Create: `banana/providers/base.py`
- Create: `tests/test_provider_base.py`

- [ ] **Step 1: Write banana/providers/base.py**

```python
"""Base LLM provider interface."""
from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None
    error_status_code: int | None = None
    error_type: str | None = None
    error_should_retry: bool | None = None
    retry_after: float | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass(frozen=True)
class GenerationSettings:
    temperature: float = 0.7
    max_tokens: int = 4096
    reasoning_effort: str | None = None


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    _CHAT_RETRY_DELAYS = (1, 2, 4)
    _PERSISTENT_MAX_DELAY = 60
    _PERSISTENT_IDENTICAL_ERROR_LIMIT = 10
    _RETRY_HEARTBEAT_CHUNK = 30
    _TRANSIENT_ERROR_MARKERS = (
        "429", "rate limit", "500", "502", "503", "504", "overloaded",
        "timeout", "timed out", "connection", "server error",
        "temporarily unavailable",
    )
    _RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
    _NON_RETRYABLE_429_TOKENS = frozenset({
        "insufficient_quota", "quota_exceeded", "quota_exhausted",
        "billing_hard_limit_reached", "insufficient_balance",
        "credit_balance_too_low", "billing_not_active", "payment_required",
    })
    _RETRYABLE_429_TOKENS = frozenset({
        "rate_limit_exceeded", "rate_limit_error", "too_many_requests",
        "request_limit_exceeded", "overloaded_error",
    })
    _SENTINEL = object()

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base
        self.generation = GenerationSettings()

    # --- Subclass contract ---

    @abstractmethod
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def get_default_model(self) -> str:
        ...

    # --- Streaming (optional override) ---

    async def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        response = await self.chat(messages=messages, tools=tools, model=model,
                                   max_tokens=max_tokens, temperature=temperature,
                                   reasoning_effort=reasoning_effort, tool_choice=tool_choice)
        if on_content_delta and response.content:
            await on_content_delta(response.content)
        return response

    # --- Retry logic ---

    async def _safe_chat(self, **kwargs: Any) -> LLMResponse:
        try:
            return await self.chat(**kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")

    async def _safe_chat_stream(self, **kwargs: Any) -> LLMResponse:
        try:
            return await self.chat_stream(**kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")

    @classmethod
    def _is_transient_error(cls, content: str | None) -> bool:
        err = (content or "").lower()
        return any(marker in err for marker in cls._TRANSIENT_ERROR_MARKERS)

    @classmethod
    def _is_transient_response(cls, response: LLMResponse) -> bool:
        if response.error_should_retry is not None:
            return bool(response.error_should_retry)
        if response.error_status_code is not None:
            status = int(response.error_status_code)
            if status == 429:
                return cls._is_retryable_429(response)
            if status in cls._RETRYABLE_STATUS_CODES or status >= 500:
                return True
        return cls._is_transient_error(response.content)

    @classmethod
    def _is_retryable_429(cls, response: LLMResponse) -> bool:
        type_token = (response.error_type or "").strip().lower()
        code_token = ""
        content = (response.content or "").lower()
        if any(t in content for t in ("insufficient_quota", "quota exceeded", "billing")):
            return False
        if type_token in cls._NON_RETRYABLE_429_TOKENS:
            return False
        if type_token in cls._RETRYABLE_429_TOKENS:
            return True
        if any(t in content for t in ("rate limit", "too many requests", "retry")):
            return True
        return True

    async def chat_with_retry(self, **kwargs: Any) -> LLMResponse:
        return await self._run_with_retry(self._safe_chat, kwargs, kwargs.get("messages", []))

    async def chat_stream_with_retry(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int | None = None,
        temperature: float | None = None, reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        max_tokens = max_tokens or self.generation.max_tokens
        temperature = temperature or self.generation.temperature
        reasoning_effort = reasoning_effort or self.generation.reasoning_effort
        kw = dict(messages=messages, tools=tools, model=model,
                  max_tokens=max_tokens, temperature=temperature,
                  reasoning_effort=reasoning_effort, tool_choice=tool_choice,
                  on_content_delta=on_content_delta)
        return await self._run_with_retry(self._safe_chat_stream, kw, messages)

    async def _run_with_retry(
        self, call: Callable[..., Awaitable[LLMResponse]],
        kw: dict[str, Any], original_messages: list[dict[str, Any]],
    ) -> LLMResponse:
        attempt = 0
        delays = list(self._CHAT_RETRY_DELAYS)
        last_error_key: str | None = None
        identical_count = 0
        last_response: LLMResponse | None = None

        while True:
            attempt += 1
            response = await call(**kw)
            if response.finish_reason != "error":
                return response
            last_response = response
            error_key = ((response.content or "").strip().lower() or None)
            if error_key and error_key == last_error_key:
                identical_count += 1
            else:
                last_error_key = error_key
                identical_count = 1 if error_key else 0

            if not self._is_transient_response(response):
                return response

            if identical_count >= self._PERSISTENT_IDENTICAL_ERROR_LIMIT:
                return response

            if attempt > len(delays):
                break

            base_delay = delays[min(attempt - 1, len(delays) - 1)]
            await asyncio.sleep(base_delay)

        return last_response or await call(**kw)

    # --- Message sanitization helpers ---

    @staticmethod
    def _sanitize_empty_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) and not content:
                clean = dict(msg)
                clean["content"] = None if (msg.get("role") == "assistant" and msg.get("tool_calls")) else "(empty)"
                result.append(clean)
                continue
            result.append(msg)
        return result

    @staticmethod
    def _enforce_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not messages:
            return messages
        merged: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            if (merged and role != "system" and role not in ("tool",)
                    and merged[-1].get("role") == role and role in ("user", "assistant")):
                prev = merged[-1]
                if role == "assistant":
                    if bool(msg.get("tool_calls")):
                        merged[-1] = dict(msg)
                        continue
                    if bool(prev.get("tool_calls")):
                        continue
                prev_content = prev.get("content") or ""
                curr_content = msg.get("content") or ""
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    prev["content"] = (prev_content + "\n\n" + curr_content).strip()
                else:
                    merged[-1] = dict(msg)
            else:
                merged.append(dict(msg))
        while merged and merged[-1].get("role") == "assistant":
            merged.pop()
        return merged
```

- [ ] **Step 2: Write tests for LLMResponse and ToolCallRequest**

```python
# tests/test_provider_base.py
from banana.providers.base import LLMResponse, ToolCallRequest, GenerationSettings, LLMProvider


class TestToolCallRequest:
    def test_create(self):
        tc = ToolCallRequest(id="call_1", name="bash", arguments={"command": "ls"})
        assert tc.id == "call_1"
        assert tc.name == "bash"
        assert tc.arguments == {"command": "ls"}


class TestLLMResponse:
    def test_text_only(self):
        r = LLMResponse(content="Hello")
        assert r.has_tool_calls is False

    def test_with_tool_calls(self):
        r = LLMResponse(
            content=None,
            tool_calls=[ToolCallRequest(id="1", name="bash", arguments={"command": "ls"})],
            finish_reason="tool_calls",
        )
        assert r.has_tool_calls is True

    def test_error_response(self):
        r = LLMResponse(content="Rate limit exceeded", finish_reason="error",
                        error_status_code=429, error_type="rate_limit_exceeded")
        assert r.finish_reason == "error"
        assert r.error_status_code == 429


class TestGenerationSettings:
    def test_defaults(self):
        gs = GenerationSettings()
        assert gs.temperature == 0.7
        assert gs.max_tokens == 4096


class TestTransientDetection:
    def test_rate_limit_is_transient(self):
        r = LLMResponse(content="rate limit exceeded", finish_reason="error",
                        error_status_code=429, error_type="rate_limit_exceeded")
        assert LLMProvider._is_transient_response(r) is True

    def test_quota_not_transient(self):
        r = LLMResponse(content="insufficient_quota", finish_reason="error",
                        error_status_code=429, error_type="insufficient_quota")
        assert LLMProvider._is_transient_response(r) is False

    def test_500_is_transient(self):
        r = LLMResponse(content="server error", finish_reason="error", error_status_code=500)
        assert LLMProvider._is_transient_response(r) is True

    def test_400_not_transient(self):
        r = LLMResponse(content="bad request", finish_reason="error", error_status_code=400)
        assert LLMProvider._is_transient_response(r) is False


class TestSanitizeMessages:
    def test_empty_content_fix(self):
        msgs = [{"role": "assistant", "content": ""}]
        result = LLMProvider._sanitize_empty_content(msgs)
        assert result[0]["content"] == "(empty)"

    def test_role_alternation_merges_same_role(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "there"},
        ]
        result = LLMProvider._enforce_role_alternation(msgs)
        assert len(result) == 1
        assert "hi" in result[0]["content"]
        assert "there" in result[0]["content"]
```

- [ ] **Step 3: Run tests to verify pass**

```bash
cd e:/BananaCoder && python -m pytest tests/test_provider_base.py -v
```

### Task 5: OpenAI compat provider

**Files:**
- Create: `banana/providers/openai_compat.py`
- Create: `tests/test_provider_openai.py`

- [ ] **Step 1: Write banana/providers/openai_compat.py**

```python
"""OpenAI-compatible provider."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from banana.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI and OpenAI-compatible APIs (DeepSeek, Qwen, Kimi, GLM, Ollama...)."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None,
                 default_model: str = "gpt-4o", extra_headers: dict[str, str] | None = None,
                 extra_body: dict[str, Any] | None = None):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        client_kw: dict[str, Any] = {"max_retries": 0}
        if api_key:
            client_kw["api_key"] = api_key
        if api_base:
            client_kw["base_url"] = api_base
        if extra_headers:
            client_kw["default_headers"] = extra_headers
        self._client = AsyncOpenAI(**client_kw)
        self.extra_body = extra_body

    def get_default_model(self) -> str:
        return self.default_model

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        model = model or self.default_model
        messages = self._sanitize_empty_content(messages)
        messages = self._enforce_role_alternation(messages)

        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice or "auto"
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        if self.extra_body:
            params["extra_body"] = self.extra_body

        try:
            completion = await self._client.chat.completions.create(**params)
        except Exception as e:
            return self._handle_error(e)

        choice = completion.choices[0]
        msg = choice.message
        fin = choice.finish_reason or "stop"
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=fin,
            usage={"prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
                   "completion_tokens": completion.usage.completion_tokens if completion.usage else 0},
            reasoning_content=getattr(msg, "reasoning_content", None),
        )

    async def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        model = model or self.default_model
        messages = self._sanitize_empty_content(messages)
        messages = self._enforce_role_alternation(messages)

        params: dict[str, Any] = {
            "model": model, "messages": messages,
            "max_tokens": max(1, max_tokens), "temperature": temperature,
            "stream": True,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice or "auto"
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        if self.extra_body:
            params["extra_body"] = self.extra_body

        try:
            params["stream_options"] = {"include_usage": True}
            stream = self._client.chat.completions.create(**params)
        except Exception:
            params.pop("stream_options", None)
            try:
                stream = self._client.chat.completions.create(**params)
            except Exception as e:
                return self._handle_error(e)

        content_parts: list[str] = []
        tc_map: dict[int, dict[str, str]] = {}
        prompt_tok, completion_tok = 0, 0

        async for chunk in stream:
            if chunk.usage:
                prompt_tok = chunk.usage.prompt_tokens or 0
                completion_tok = chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                if on_content_delta:
                    await on_content_delta(delta.content)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    if tc_delta.id:
                        tc_map[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_map[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_map[idx]["args"] += tc_delta.function.arguments

        tool_calls = []
        for idx in sorted(tc_map):
            raw = tc_map[idx]
            try:
                args = json.loads(raw["args"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            tool_calls.append(ToolCallRequest(id=raw["id"], name=raw["name"], arguments=args))

        fin = "tool_calls" if tool_calls else "stop"
        return LLMResponse(
            content="".join(content_parts) or None,
            tool_calls=tool_calls,
            finish_reason=fin,
            usage={"prompt_tokens": prompt_tok, "completion_tokens": completion_tok},
        )

    def _handle_error(self, exc: Exception) -> LLMResponse:
        from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError

        msg = str(exc)
        status = None
        error_type = None
        retryable = None

        if isinstance(exc, RateLimitError):
            status = 429
            error_type = "rate_limit_exceeded"
            retryable = "insufficient_quota" not in msg.lower() and "quota" not in msg.lower()
        elif isinstance(exc, APITimeoutError):
            status = 408
            error_type = "timeout"
            retryable = True
        elif isinstance(exc, APIConnectionError):
            status = 503
            error_type = "connection"
            retryable = True
        elif isinstance(exc, APIError):
            status = getattr(exc, "status_code", None)
            retryable = status is not None and status >= 500

        return LLMResponse(
            content=msg, finish_reason="error",
            error_status_code=status, error_type=error_type,
            error_should_retry=retryable,
        )
```

- [ ] **Step 2: Write tests**

```python
# tests/test_provider_openai.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from banana.providers.openai_compat import OpenAICompatProvider
from banana.providers.base import LLMResponse


class TestOpenAICompatProvider:
    def test_get_default_model(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="deepseek-chat")
        assert p.get_default_model() == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_chat_text_response(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="test-model")
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 5
        p._client.chat.completions.create = AsyncMock(return_value=mock_completion)

        resp = await p.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "Hello!"
        assert resp.finish_reason == "stop"
        assert not resp.has_tool_calls

    @pytest.mark.asyncio
    async def test_chat_tool_call_response(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="test-model")
        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "bash"
        mock_tc.function.arguments = '{"command": "ls"}'
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = [mock_tc]
        mock_choice.finish_reason = "tool_calls"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 5
        p._client.chat.completions.create = AsyncMock(return_value=mock_completion)

        resp = await p.chat(messages=[{"role": "user", "content": "list files"}])
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "bash"
        assert resp.tool_calls[0].arguments == {"command": "ls"}
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_provider_openai.py -v
```

### Task 6: Anthropic provider

**Files:**
- Create: `banana/providers/anthropic.py`

- [ ] **Step 1: Write banana/providers/anthropic.py**

```python
"""Anthropic provider using the native SDK."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from anthropic import AsyncAnthropic, APIError, RateLimitError, APITimeoutError, APIConnectionError

from banana.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models using the native Messages API."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None,
                 default_model: str = "claude-sonnet-4-20250514",
                 extra_headers: dict[str, str] | None = None):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        client_kw: dict[str, Any] = {"max_retries": 0}
        if api_key:
            client_kw["api_key"] = api_key
        if api_base:
            client_kw["base_url"] = api_base
        if extra_headers:
            client_kw["default_headers"] = extra_headers
        self._client = AsyncAnthropic(**client_kw)

    def get_default_model(self) -> str:
        return self.default_model

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        model = model or self.default_model
        system, anthropic_msgs, tools_anthropic = self._convert_messages(messages, tools)

        params: dict[str, Any] = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        if tools_anthropic:
            params["tools"] = tools_anthropic

        try:
            resp = await self._client.messages.create(**params)
        except Exception as e:
            return self._handle_error(e)

        text = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(
                    id=block.id, name=block.name, arguments=block.input or {},
                ))

        return LLMResponse(
            content=text or None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage={"prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens},
        )

    def _convert_messages(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None):
        """Convert OpenAI-format messages and tools to Anthropic format."""
        system_parts: list[str] = []
        anthropic_msgs: list[dict[str, Any]] = []
        tools_anthropic: list[dict[str, Any]] | None = None

        if tools:
            tools_anthropic = []
            for t in tools:
                fn = t.get("function", t)
                tools_anthropic.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content") or ""

            if role == "system":
                system_parts.append(content if isinstance(content, str) else str(content))
                continue

            if role == "tool":
                anthropic_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content if isinstance(content, str) else str(content),
                    }],
                })
                continue

            if role == "assistant":
                out_blocks: list[dict[str, Any]] = []
                if content:
                    out_blocks.append({"type": "text", "text": content if isinstance(content, str) else str(content)})
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", tc)
                    out_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": fn.get("arguments", {}) if isinstance(fn.get("arguments"), dict) else {},
                    })
                anthropic_msgs.append({"role": "assistant", "content": out_blocks or content})
                continue

            # user role
            if isinstance(content, str):
                anthropic_msgs.append({"role": "user", "content": content})
            else:
                anthropic_msgs.append({"role": "user", "content": str(content)})

        system = "\n".join(system_parts) if system_parts else None
        return system, anthropic_msgs, tools_anthropic

    def _handle_error(self, exc: Exception) -> LLMResponse:
        msg = str(exc)
        status = None
        error_type = None
        retryable = None

        if isinstance(exc, RateLimitError):
            status = 429
            error_type = "rate_limit_exceeded"
        elif isinstance(exc, APITimeoutError):
            status = 408
            retryable = True
        elif isinstance(exc, APIConnectionError):
            status = 503
            retryable = True
        elif isinstance(exc, APIError):
            status = getattr(exc, "status_code", None)
            retryable = status is not None and status >= 500

        return LLMResponse(content=msg, finish_reason="error",
                           error_status_code=status, error_type=error_type,
                           error_should_retry=retryable)
```

### Task 7: Fallback provider + factory

**Files:**
- Create: `banana/providers/fallback.py`
- Create: `banana/providers/factory.py`
- Create: `tests/test_provider_fallback.py`

- [ ] **Step 1: Write banana/providers/fallback.py**

```python
"""Fallback provider chains."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from banana.providers.base import LLMProvider, LLMResponse


class FallbackProvider(LLMProvider):
    """Chain multiple providers: on transient error, try the next one."""

    def __init__(self, providers: list[LLMProvider], default_model: str = ""):
        super().__init__()
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self._chain = providers
        self.default_model = default_model or providers[0].get_default_model()

    def get_default_model(self) -> str:
        return self.default_model

    async def chat(self, **kwargs: Any) -> LLMResponse:
        last: LLMResponse | None = None
        for provider in self._chain:
            resp = await provider.chat(**kwargs)
            if resp.finish_reason != "error":
                return resp
            if not self._is_transient_response(resp):
                return resp
            last = resp
        return last or LLMResponse(content="All providers failed", finish_reason="error")

    async def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
        model: str | None = None, max_tokens: int = 4096, temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        last: LLMResponse | None = None
        for provider in self._chain:
            resp = await provider.chat_stream(
                messages=messages, tools=tools, model=model,
                max_tokens=max_tokens, temperature=temperature,
                reasoning_effort=reasoning_effort, tool_choice=tool_choice,
                on_content_delta=on_content_delta,
            )
            if resp.finish_reason != "error":
                return resp
            if not self._is_transient_response(resp):
                return resp
            last = resp
        return last or LLMResponse(content="All providers failed", finish_reason="error")
```

- [ ] **Step 2: Write banana/providers/factory.py**

```python
"""Create providers from config."""
from __future__ import annotations

from banana.config.schema import Config
from banana.providers.base import LLMProvider
from banana.providers.openai_compat import OpenAICompatProvider
from banana.providers.anthropic import AnthropicProvider
from banana.providers.fallback import FallbackProvider


def _make_single_provider(config: Config, model: str, provider_name: str | None = None) -> LLMProvider:
    """Create a single provider for a model."""
    preset = config.model_presets.get("default")
    if not preset:
        raise ValueError("No default model preset configured")
    name = provider_name or config.get_provider_name(model, preset=preset)
    p = config.providers.get(name)
    api_key = p.api_key if p else ""
    api_base = p.api_base if p else None

    if name == "anthropic":
        return AnthropicProvider(
            api_key=api_key, api_base=api_base,
            default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        return OpenAICompatProvider(
            api_key=api_key, api_base=api_base,
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            extra_body=p.extra_body if p else None,
        )


def make_provider(config: Config) -> LLMProvider:
    """Create the full provider chain from config."""
    default_preset = config.model_presets.get("default")
    if not default_preset:
        raise ValueError("No default model preset in config")

    primary = _make_single_provider(config, default_preset.model)
    primary.generation = default_preset.to_generation_settings()

    fallback_providers = []
    for fb_model in config.fallback_models:
        fb_name = config.fallback_providers.get(fb_model, "openai_compat")
        fb = _make_single_provider(config, fb_model, provider_name=fb_name)
        fallback_providers.append(fb)

    if fallback_providers:
        return FallbackProvider([primary] + fallback_providers)
    return primary
```

- [ ] **Step 3: Write fallback tests**

```python
# tests/test_provider_fallback.py
import pytest
from banana.providers.base import LLMResponse, LLMProvider
from banana.providers.fallback import FallbackProvider


class FakeProvider(LLMProvider):
    def __init__(self, name: str, responses: list[LLMResponse]):
        super().__init__()
        self.name = name
        self._responses = responses
        self._call_count = 0

    def get_default_model(self) -> str:
        return self.name

    async def chat(self, **kwargs):
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return LLMResponse(content=f"OK from {self.name}")

    async def chat_stream(self, **kwargs):
        return await self.chat(**kwargs)


class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_first_succeeds(self):
        p1 = FakeProvider("p1", [LLMResponse(content="hello from p1")])
        fb = FallbackProvider([p1])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "hello from p1"

    @pytest.mark.asyncio
    async def test_fallback_on_transient(self):
        p1 = FakeProvider("p1", [LLMResponse(content="rate limit", finish_reason="error",
                                              error_status_code=429, error_type="rate_limit_exceeded")])
        p2 = FakeProvider("p2", [LLMResponse(content="hello from fallback")])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "hello from fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_on_quota(self):
        p1 = FakeProvider("p1", [LLMResponse(content="quota exceeded", finish_reason="error",
                                              error_status_code=429, error_type="insufficient_quota")])
        p2 = FakeProvider("p2", [])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_all_fail(self):
        p1 = FakeProvider("p1", [LLMResponse(content="e1", finish_reason="error", error_status_code=500)])
        p2 = FakeProvider("p2", [LLMResponse(content="e2", finish_reason="error", error_status_code=500)])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.finish_reason == "error"
```

- [ ] **Step 4: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_provider_fallback.py -v
```

---

## Task Group 4: Tool System

### Task 8: Tool base + registry

**Files:**
- Create: `banana/tools/base.py`
- Create: `banana/tools/registry.py`
- Create: `tests/test_tool_registry.py`

- [ ] **Step 1: Write banana/tools/base.py**

```python
"""Base classes for tools."""
from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, Callable, TypeVar

_ToolT = TypeVar("_ToolT", bound="Tool")

_JSON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "array": list, "object": dict,
}


class Schema:
    """JSON Schema fragment validation."""

    @staticmethod
    def resolve_json_schema_type(t: Any) -> str | None:
        if isinstance(t, list):
            return next((x for x in t if x != "null"), None)
        return t

    @staticmethod
    def subpath(path: str, key: str) -> str:
        return f"{path}.{key}" if path else key

    @staticmethod
    def validate_json_schema_value(val: Any, schema: dict[str, Any], path: str = "") -> list[str]:
        raw_type = schema.get("type")
        nullable = (isinstance(raw_type, list) and "null" in raw_type) or schema.get("nullable", False)
        t = Schema.resolve_json_schema_type(raw_type)
        label = path or "parameter"

        if nullable and val is None:
            return []
        if t == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
            return [f"{label} should be integer"]
        if t == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
            return [f"{label} should be number"]
        if t in _JSON_TYPE_MAP and t not in ("integer", "number") and not isinstance(val, _JSON_TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors: list[str] = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {Schema.subpath(path, k)}")
            for k, v in val.items():
                if k in props:
                    errors.extend(Schema.validate_json_schema_value(v, props[k], Schema.subpath(path, k)))
        if t == "array":
            if "minItems" in schema and len(val) < schema["minItems"]:
                errors.append(f"{label} must have at least {schema['minItems']} items")
            if "maxItems" in schema and len(val) > schema["maxItems"]:
                errors.append(f"{label} must be at most {schema['maxItems']} items")
            if "items" in schema:
                for i, item in enumerate(val):
                    errors.extend(Schema.validate_json_schema_value(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))
        return errors


class Tool(ABC):
    """Base class for all tools."""

    _BOOL_TRUE = frozenset(("true", "1", "yes"))
    _BOOL_FALSE = frozenset(("false", "0", "no"))

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]: ...

    @property
    def read_only(self) -> bool:
        return False

    @property
    def concurrency_safe(self) -> bool:
        return self.read_only and not self.exclusive

    @property
    def exclusive(self) -> bool:
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any: ...

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params
        return self._cast_object(params, schema)

    def _cast_object(self, obj: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        props = schema.get("properties", {})
        return {k: self._cast_value(v, props[k]) if k in props else v for k, v in obj.items()}

    def _cast_value(self, val: Any, schema: dict[str, Any]) -> Any:
        t = Schema.resolve_json_schema_type(schema.get("type"))
        if t == "string" and isinstance(val, str):
            return val
        if isinstance(val, str) and t in ("integer", "number"):
            try:
                return int(val) if t == "integer" else float(val)
            except ValueError:
                return val
        if t == "string":
            return val if val is None else str(val)
        if t == "boolean" and isinstance(val, str):
            low = val.lower()
            if low in self._BOOL_TRUE:
                return True
            if low in self._BOOL_FALSE:
                return False
        return val

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        if not isinstance(params, dict):
            return [f"parameters must be an object, got {type(params).__name__}"]
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return Schema.validate_json_schema_value(params, {**schema, "type": "object"}, "")

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool_parameters(schema: dict[str, Any]) -> Callable[[type[_ToolT]], type[_ToolT]]:
    """Class decorator: attach JSON Schema and inject parameters property."""
    def decorator(cls: type[_ToolT]) -> type[_ToolT]:
        frozen = deepcopy(schema)

        @property
        def parameters(self: Any) -> dict[str, Any]:
            return deepcopy(frozen)

        cls.parameters = parameters  # type: ignore[assignment]
        abstract = getattr(cls, "__abstractmethods__", None)
        if abstract is not None and "parameters" in abstract:
            cls.__abstractmethods__ = frozenset(abstract - {"parameters"})  # type: ignore[misc]
        return cls
    return decorator
```

- [ ] **Step 2: Write banana/tools/registry.py**

```python
"""Tool registry for dynamic tool management."""
from __future__ import annotations

from typing import Any

from banana.tools.base import Tool


class ToolRegistry:
    """Registry for agent tools with cached definitions."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._cached_definitions: list[dict[str, Any]] | None = None

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self._cached_definitions = None

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        self._cached_definitions = None

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        if self._cached_definitions is not None:
            return self._cached_definitions

        definitions = [tool.to_schema() for tool in self._tools.values()]
        builtins: list[dict[str, Any]] = []
        mcp_tools: list[dict[str, Any]] = []
        for schema in definitions:
            name = schema["function"]["name"]
            if name.startswith("mcp_"):
                mcp_tools.append(schema)
            else:
                builtins.append(schema)

        builtins.sort(key=lambda s: s["function"]["name"])
        mcp_tools.sort(key=lambda s: s["function"]["name"])
        self._cached_definitions = builtins + mcp_tools
        return self._cached_definitions

    def prepare_call(self, name: str, params: dict[str, Any]) -> tuple[Tool | None, dict[str, Any], str | None]:
        if not isinstance(params, dict):
            return None, params, (
                f"Error: Tool '{name}' parameters must be a JSON object, got {type(params).__name__}."
            )

        tool = self._tools.get(name)
        if not tool:
            return None, params, (
                f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"
            )

        cast_params = tool.cast_params(params)
        errors = tool.validate_params(cast_params)
        if errors:
            return tool, cast_params, (
                f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            )
        return tool, cast_params, None

    async def execute(self, name: str, params: dict[str, Any]) -> Any:
        _HINT = "\n\n[Analyze the error above and try a different approach.]"
        tool, cast_params, error = self.prepare_call(name, params)
        if error:
            return error + _HINT

        try:
            assert tool is not None
            result = await tool.execute(**cast_params)
            if isinstance(result, str) and result.startswith("Error"):
                return result + _HINT
            return result
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + _HINT
```

- [ ] **Step 3: Write tests**

```python
# tests/test_tool_registry.py
import pytest
from banana.tools.base import Tool, tool_parameters
from banana.tools.registry import ToolRegistry


class FakeReadTool(Tool):
    name = "read_file"
    description = "Read a file"
    parameters = {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
    }
    read_only = True

    async def execute(self, file_path: str) -> str:
        return f"contents of {file_path}"


class FakeWriteTool(Tool):
    name = "write_file"
    description = "Write a file"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> str:
        return f"wrote {file_path}"


class TestToolRegistry:
    def test_register_and_get(self):
        r = ToolRegistry()
        t = FakeReadTool()
        r.register(t)
        assert r.get("read_file") is t
        assert r.has("read_file")

    def test_get_definitions(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        r.register(FakeWriteTool())
        defs = r.get_definitions()
        assert len(defs) == 2
        names = [d["function"]["name"] for d in defs]
        assert names == ["read_file", "write_file"]

    @pytest.mark.asyncio
    async def test_execute_success(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        result = await r.execute("read_file", {"file_path": "/tmp/test.txt"})
        assert "contents of" in str(result)

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        r = ToolRegistry()
        result = await r.execute("nonexistent", {})
        assert "not found" in str(result)

    @pytest.mark.asyncio
    async def test_execute_missing_required(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        result = await r.execute("read_file", {})
        assert "missing" in str(result).lower()

    def test_unregister(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        r.unregister("read_file")
        assert not r.has("read_file")
```

- [ ] **Step 4: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_tool_registry.py -v
```

---

## Task Group 5: Session Layer

### Task 9: Session manager

**Files:**
- Create: `banana/session/manager.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write banana/session/manager.py**

```python
"""Session persistence and management."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles


@dataclass
class Session:
    id: str
    project: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class SessionManager:
    def __init__(self, storage_dir: Path, project_dir: Path):
        self._storage = storage_dir / "sessions"
        self._project_hash = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()[:12]
        self._active_id = "default"

    # --- Path helpers ---

    def _project_dir(self) -> Path:
        return self._storage / self._project_hash

    def _session_path(self, session_id: str) -> Path:
        return self._project_dir() / session_id / "messages.json"

    def _meta_path(self, session_id: str) -> Path:
        return self._project_dir() / session_id / "meta.json"

    def _index_path(self) -> Path:
        return self._storage / "index.json"

    # --- Index management ---

    def _load_index(self) -> dict:
        path = self._index_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"sessions": {}, "active": "default"}

    def _save_index(self, index: dict):
        self._index_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self._index_path()) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._index_path())

    # --- CRUD ---

    async def load(self, session_id: str | None = None) -> Session:
        sid = session_id or self._active_id
        msg_path = self._session_path(sid)
        meta_path = self._meta_path(sid)

        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {"id": sid, "project": str(self._project_hash),
                    "created_at": time.time(), "summary": ""}

        if msg_path.exists():
            async with aiofiles.open(msg_path, "r", encoding="utf-8") as f:
                messages = json.loads(await f.read())
        else:
            messages = []

        return Session(
            id=sid, project=meta.get("project", ""),
            messages=messages, summary=meta.get("summary", ""),
            created_at=meta.get("created_at", time.time()),
            updated_at=meta.get("updated_at", time.time()),
        )

    async def save(self, session: Session):
        session.updated_at = time.time()
        dir_path = self._session_path(session.id).parent
        dir_path.mkdir(parents=True, exist_ok=True)

        # Write messages
        tmp_msg = str(self._session_path(session.id)) + ".tmp"
        async with aiofiles.open(tmp_msg, "w", encoding="utf-8") as f:
            content = json.dumps(session.messages, ensure_ascii=False, indent=2)
            await f.write(content)
            await f.flush()
        os.fsync(os.open(tmp_msg, os.O_RDONLY))
        os.replace(tmp_msg, self._session_path(session.id))

        # Write meta
        tmp_meta = str(self._meta_path(session.id)) + ".tmp"
        meta = {
            "id": session.id, "project": session.project,
            "created_at": session.created_at, "updated_at": session.updated_at,
            "summary": session.summary,
        }
        async with aiofiles.open(tmp_meta, "w", encoding="utf-8") as f:
            await f.write(json.dumps(meta, ensure_ascii=False, indent=2))
            await f.flush()
        os.fsync(os.open(tmp_meta, os.O_RDONLY))
        os.replace(tmp_meta, self._meta_path(session.id))

        # Update index
        index = self._load_index()
        index["sessions"][session.id] = {
            "id": session.id, "project": session.project,
            "created_at": session.created_at, "updated_at": session.updated_at,
            "message_count": len(session.messages), "summary": session.summary,
        }
        index["active"] = self._active_id
        self._save_index(index)

    async def switch(self, session_id: str) -> Session:
        self._active_id = session_id
        index = self._load_index()
        index["active"] = session_id
        self._save_index(index)
        return await self.load(session_id)

    async def new(self, session_id: str) -> Session:
        session = Session(id=session_id, project=str(self._project_hash))
        await self.save(session)
        return await self.switch(session_id)

    async def delete(self, session_id: str):
        import shutil
        dir_path = self._project_dir() / session_id
        if dir_path.exists():
            shutil.rmtree(dir_path)
        index = self._load_index()
        index["sessions"].pop(session_id, None)
        if index["active"] == session_id:
            index["active"] = "default"
        self._save_index(index)

    async def list_sessions(self) -> list[dict]:
        index = self._load_index()
        return list(index["sessions"].values())

    async def compact(self, session: Session, provider=None, keep_recent: int = 20):
        """Compress old messages into a summary using LLM."""
        if len(session.messages) <= keep_recent:
            return

        old = session.messages[:-keep_recent]
        recent = session.messages[-keep_recent:]

        summary = session.summary or ""
        if provider and old:
            flat = "\n".join(
                f"[{m['role']}] {str(m.get('content', ''))[:200]}"
                for m in old
            )
            try:
                resp = await provider.chat(
                    messages=[
                        {"role": "system", "content": (
                            "Summarize this conversation in 2-3 sentences. "
                            "Include: files edited, decisions made, errors encountered."
                        )},
                        {"role": "user", "content": flat[:8000]},
                    ],
                )
                summary = resp.content or summary
            except Exception:
                pass

        session.messages = [
            {"role": "user", "content": f"[History summary]\n{summary}"},
            {"role": "assistant", "content": "Got it. I have the context from our previous conversation."},
        ] + recent
        session.summary = summary
        await self.save(session)
```

- [ ] **Step 2: Write tests**

```python
# tests/test_session.py
import pytest
from banana.session.manager import Session, SessionManager


class TestSession:
    def test_create(self):
        s = Session(id="test", project="myproj")
        assert s.id == "test"
        assert s.messages == []


class TestSessionManager:
    @pytest.fixture
    def mgr(self, temp_home):
        return SessionManager(temp_home / ".bananacoder", temp_home / "projects" / "test")

    @pytest.mark.asyncio
    async def test_load_creates_empty(self, mgr):
        s = await mgr.load()
        assert s.id == "default"
        assert s.messages == []

    @pytest.mark.asyncio
    async def test_save_and_reload(self, mgr):
        s = Session(id="default", project="test")
        s.messages = [{"role": "user", "content": "hello"}]
        await mgr.save(s)

        loaded = await mgr.load()
        assert loaded.messages == s.messages

    @pytest.mark.asyncio
    async def test_switch(self, mgr):
        await mgr.new("other")
        s1 = await mgr.load()
        assert s1.id == "other"

    @pytest.mark.asyncio
    async def test_delete(self, mgr):
        s = Session(id="todelete", project="test", messages=[{"role": "user", "content": "x"}])
        await mgr.save(s)
        await mgr.delete("todelete")
        loaded = await mgr.load("todelete")
        assert loaded.messages == []

    @pytest.mark.asyncio
    async def test_list(self, mgr):
        await mgr.new("a")
        await mgr.new("b")
        sessions = await mgr.list_sessions()
        ids = [s["id"] for s in sessions]
        assert "a" in ids
        assert "b" in ids
```

- [ ] **Step 3: Run tests**

```bash
cd e:/BananaCoder && python -m pytest tests/test_session.py -v
```

---

At this point the foundation is complete. The remaining task groups (Tools implementation, MCP, Skills, Agent, CLI) will be in a continuation file due to plan size limits. The foundation tasks above establish the entire dependency substrate: config → provider → tools base/registry → session.

**Foundation verification:**
```bash
cd e:/BananaCoder && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all 30+ tests pass
