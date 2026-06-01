"""Base LLM provider interface."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
