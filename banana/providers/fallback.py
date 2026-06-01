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
