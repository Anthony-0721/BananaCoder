"""Agent hook system (simplified from nanobot's AgentHook).

Hooks are lifecycle callbacks that can modify agent behavior.
Register hooks via Python API or config.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookContext:
    """Mutable context passed through hook lifecycle.

    Inspired by nanobot's AgentHookContext but simplified
    for BananaCoder's single-agent architecture.
    """
    messages: list[dict[str, Any]] = field(default_factory=list)
    llm_response: Any = None          # LLMResponse
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""
    iteration: int = 0
    stop_reason: str | None = None
    error: str | None = None


class AgentHook(ABC):
    """Base class for agent lifecycle hooks.

    Subclass and override any method. All methods are optional
    and default to no-op. Inspired by nanobot's AgentHook.
    """

    async def before_llm_call(self, ctx: HookContext):
        """Called before each LLM API call. Can modify ctx.messages."""

    async def after_llm_call(self, ctx: HookContext):
        """Called after LLM response is received. Can inspect ctx.llm_response."""

    async def before_tool_execute(self, ctx: HookContext) -> bool:
        """Called before a tool executes. Return False to block execution.
        The blocked result message will be returned to the LLM."""
        return True

    async def after_tool_execute(self, ctx: HookContext):
        """Called after a tool completes. Can inspect ctx.tool_result."""

    async def on_turn_start(self, ctx: HookContext):
        """Called at the start of each user turn."""

    async def on_turn_end(self, ctx: HookContext):
        """Called at the end of each user turn."""


class HookManager:
    """Manages and dispatches a list of hooks.

    Inspired by nanobot's CompositeHook — runs hooks in order,
    catches per-hook exceptions to prevent one from breaking others.
    """

    def __init__(self, hooks: list[AgentHook] | None = None):
        self._hooks = hooks or []

    def register(self, hook: AgentHook):
        self._hooks.append(hook)

    def unregister(self, hook: AgentHook):
        self._hooks.remove(hook)

    async def _dispatch(self, method: str, ctx: HookContext, **extra):
        for hook in self._hooks:
            try:
                fn = getattr(hook, method)
                await fn(ctx, **extra)
            except Exception:
                pass  # Hook errors shouldn't break agent

    async def before_llm_call(self, ctx: HookContext):
        await self._dispatch("before_llm_call", ctx)

    async def after_llm_call(self, ctx: HookContext):
        await self._dispatch("after_llm_call", ctx)

    async def before_tool_execute(self, ctx: HookContext) -> bool:
        """Returns False if any hook blocks the tool."""
        for hook in self._hooks:
            try:
                if not await hook.before_tool_execute(ctx):
                    return False
            except Exception:
                pass
        return True

    async def after_tool_execute(self, ctx: HookContext):
        await self._dispatch("after_tool_execute", ctx)

    async def on_turn_start(self, ctx: HookContext):
        await self._dispatch("on_turn_start", ctx)

    async def on_turn_end(self, ctx: HookContext):
        await self._dispatch("on_turn_end", ctx)
