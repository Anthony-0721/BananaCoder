"""MCP client: connect to MCP servers and register their tools/resources/prompts."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import urllib.parse
from contextlib import AsyncExitStack, suppress
from typing import Any

import httpx
from loguru import logger

from banana.tools.base import Tool
from banana.tools.registry import ToolRegistry

_TRANSIENT_EXC_NAMES: frozenset[str] = frozenset((
    "ClosedResourceError", "BrokenResourceError", "EndOfStream",
    "BrokenPipeError", "ConnectionResetError", "ConnectionRefusedError",
    "ConnectionAbortedError", "ConnectionError",
))
_WINDOWS_SHELL_LAUNCHERS: frozenset[str] = frozenset(("npx", "npm", "pnpm", "yarn", "bunx"))
_SANITIZE_RE = re.compile(r"_+")


def _sanitize_name(name: str) -> str:
    return _SANITIZE_RE.sub("_", re.sub(r"[^a-zA-Z0-9_-]", "_", name))


def _is_transient(exc: BaseException) -> bool:
    return type(exc).__name__ in _TRANSIENT_EXC_NAMES


def _windows_command_basename(command: str) -> str:
    return command.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()


def _normalize_windows_stdio_command(command: str, args: list[str] | None,
                                     env: dict[str, str] | None) -> tuple[str, list[str], dict[str, str] | None]:
    normalized_args = list(args or [])
    if os.name != "nt":
        return command, normalized_args, env
    basename = _windows_command_basename(command)
    if basename in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return command, normalized_args, env
    if basename.endswith((".exe", ".com")):
        return command, normalized_args, env
    resolved = shutil.which(command, path=(env or {}).get("PATH")) or command
    resolved_basename = _windows_command_basename(resolved)
    should_wrap = basename in _WINDOWS_SHELL_LAUNCHERS or basename.endswith((".cmd", ".bat")) or resolved_basename.endswith((".cmd", ".bat"))
    if not should_wrap:
        return command, normalized_args, env
    comspec = (env or {}).get("COMSPEC") or os.environ.get("COMSPEC") or "cmd.exe"
    return comspec, ["/d", "/c", command, *normalized_args], env


async def _probe_http_url(url: str, timeout: float = 3.0) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if not port:
        port = 443 if parsed.scheme == "https" else 80
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def _normalize_schema_for_openai(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    raw_type = normalized.get("type")
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item != "null"]
        if "null" in raw_type and len(non_null) == 1:
            normalized["type"] = non_null[0]
            normalized["nullable"] = True
    if "properties" in normalized and isinstance(normalized["properties"], dict):
        normalized["properties"] = {
            name: _normalize_schema_for_openai(prop) if isinstance(prop, dict) else prop
            for name, prop in normalized["properties"].items()
        }
    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = _normalize_schema_for_openai(normalized["items"])
    if normalized.get("type") != "object":
        return normalized
    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])
    return normalized


class MCPToolWrapper(Tool):
    _plugin_discoverable = False

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_{tool_def.name}")
        self._description = tool_def.description or tool_def.name
        raw_schema = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._parameters = _normalize_schema_for_openai(raw_schema)
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types

        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(self._original_name, arguments=kwargs),
                    timeout=self._tool_timeout,
                )
            except asyncio.TimeoutError:
                return f"(MCP tool '{self._name}' timed out after {self._tool_timeout}s)"
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling() > 0:
                    raise
                return f"(MCP tool '{self._name}' was cancelled)"
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP tool '{self._name}' failed: {type(exc).__name__})"
            else:
                parts = []
                for block in result.content:
                    if isinstance(block, types.TextContent):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                return "\n".join(parts) or "(no output)"
        return "(MCP tool call failed)"


class MCPResourceWrapper(Tool):
    _plugin_discoverable = False
    read_only = True

    def __init__(self, session, server_name: str, resource_def, resource_timeout: int = 30):
        self._session = session
        self._uri = resource_def.uri
        self._name = _sanitize_name(f"mcp_{server_name}_resource_{resource_def.name}")
        desc = resource_def.description or resource_def.name
        self._description = f"[MCP Resource] {desc}\nURI: {self._uri}"
        self._parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        self._resource_timeout = resource_timeout

    @property
    def name(self) -> str: return self._name

    @property
    def description(self) -> str: return self._description

    @property
    def parameters(self) -> dict[str, Any]: return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types
        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.read_resource(self._uri),
                    timeout=self._resource_timeout,
                )
            except asyncio.TimeoutError:
                return "(MCP resource timed out)"
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP resource failed: {type(exc).__name__})"
            else:
                parts = []
                for block in result.contents:
                    if isinstance(block, types.TextResourceContents):
                        parts.append(block.text)
                    else:
                        parts.append(f"[Binary: {len(getattr(block, 'blob', b''))} bytes]")
                return "\n".join(parts) or "(no output)"
        return "(MCP resource failed)"


class MCPPromptWrapper(Tool):
    _plugin_discoverable = False
    read_only = True

    def __init__(self, session, server_name: str, prompt_def, prompt_timeout: int = 30):
        self._session = session
        self._prompt_name = prompt_def.name
        self._name = _sanitize_name(f"mcp_{server_name}_prompt_{prompt_def.name}")
        desc = prompt_def.description or prompt_def.name
        self._description = f"[MCP Prompt] {desc}"
        self._prompt_timeout = prompt_timeout
        properties = {}
        required = []
        for arg in prompt_def.arguments or []:
            properties[arg.name] = {"type": "string", "description": getattr(arg, "description", "") or ""}
            if arg.required:
                required.append(arg.name)
        self._parameters = {"type": "object", "properties": properties, "required": required}

    @property
    def name(self) -> str: return self._name

    @property
    def description(self) -> str: return self._description

    @property
    def parameters(self) -> dict[str, Any]: return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types
        for attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    self._session.get_prompt(self._prompt_name, arguments=kwargs),
                    timeout=self._prompt_timeout,
                )
            except Exception as exc:
                if _is_transient(exc) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                return f"(MCP prompt failed: {type(exc).__name__})"
            else:
                parts = []
                for msg in result.messages:
                    content = msg.content
                    if isinstance(content, types.TextContent):
                        parts.append(content.text)
                    else:
                        parts.append(str(content))
                return "\n".join(parts) or "(no output)"
        return "(MCP prompt failed)"


async def connect_mcp_servers(mcp_servers: dict, registry: ToolRegistry) -> dict[str, AsyncExitStack]:
    """Connect to configured MCP servers and register their tools/resources/prompts."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    async def connect_single_server(name: str, cfg) -> tuple[str, AsyncExitStack | None]:
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        try:
            transport_type = cfg.get("type", "")
            # Merge top-level Authorization into headers for convenience
            headers: dict[str, str] = dict(cfg.get("headers") or {})
            if "Authorization" in cfg and "Authorization" not in headers:
                headers["Authorization"] = cfg["Authorization"]
            if not transport_type:
                if cfg.get("command"):
                    transport_type = "stdio"
                elif cfg.get("url"):
                    transport_type = "sse" if cfg["url"].rstrip("/").endswith("/sse") else "streamableHttp"
                else:
                    logger.warning(f"MCP server '{name}': no command or url, skipping")
                    with suppress(Exception):
                        await server_stack.aclose()
                    return name, None

            if transport_type == "stdio":
                command, args, env = _normalize_windows_stdio_command(
                    cfg["command"], cfg.get("args"), cfg.get("env"),
                )
                params = StdioServerParameters(command=command, args=args, env=env)
                read, write = await server_stack.enter_async_context(stdio_client(params))
            elif transport_type == "sse":
                if not await _probe_http_url(cfg["url"]):
                    logger.warning(f"MCP server '{name}': unreachable, skipping")
                    with suppress(Exception):
                        await server_stack.aclose()
                    return name, None
                read, write = await server_stack.enter_async_context(sse_client(cfg["url"]))
            elif transport_type == "streamableHttp":
                if not await _probe_http_url(cfg["url"]):
                    logger.warning(f"MCP server '{name}': unreachable, skipping")
                    with suppress(Exception):
                        await server_stack.aclose()
                    return name, None
                http_client = httpx.AsyncClient(
                    headers=headers or None, follow_redirects=True, timeout=None)
                try:
                    read, write, _ = await server_stack.enter_async_context(
                        streamable_http_client(cfg["url"], http_client=http_client))
                except Exception:
                    with suppress(Exception):
                        await http_client.aclose()
                    raise
            else:
                logger.warning(f"MCP server '{name}': unknown transport '{transport_type}'")
                with suppress(Exception):
                    await server_stack.aclose()
                return name, None

            session = await server_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            enabled_tools = set(cfg.get("enabled_tools", ["*"]))
            allow_all = "*" in enabled_tools
            tool_timeout = cfg.get("tool_timeout", 30)

            tools_result = await session.list_tools()
            for tool_def in tools_result.tools:
                wrapped_name = _sanitize_name(f"mcp_{name}_{tool_def.name}")
                if not allow_all and tool_def.name not in enabled_tools and wrapped_name not in enabled_tools:
                    continue
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=tool_timeout)
                registry.register(wrapper)
                logger.debug(f"MCP: registered tool '{wrapper.name}' from '{name}'")

            return name, server_stack
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning(f"MCP server '{name}': connection failed: {e}")
            with suppress(BaseException):
                await server_stack.aclose()
            return name, None

    server_stacks: dict[str, AsyncExitStack] = {}
    for name, cfg in mcp_servers.items():
        try:
            result = await connect_single_server(name, cfg)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning(f"MCP server '{name}': unexpected error during connection: {e}")
            continue
        if result is not None and result[1] is not None:
            server_stacks[result[0]] = result[1]
    return server_stacks
