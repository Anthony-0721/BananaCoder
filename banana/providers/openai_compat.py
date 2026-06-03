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
            "model": model, "messages": messages,
            "max_tokens": max(1, max_tokens), "temperature": temperature,
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
        on_reasoning: Callable[[str], Awaitable[None]] | None = None,
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
            stream = await self._client.chat.completions.create(**params)
        except Exception:
            params.pop("stream_options", None)
            try:
                stream = await self._client.chat.completions.create(**params)
            except Exception as e:
                return self._handle_error(e)

        content_parts: list[str] = []
        tc_map: dict[int, dict[str, str]] = {}
        prompt_tok, completion_tok = 0, 0
        actual_finish: str | None = None

        async for chunk in stream:
            if chunk.usage:
                prompt_tok = chunk.usage.prompt_tokens or 0
                completion_tok = chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                actual_finish = choice.finish_reason
            delta = choice.delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and on_reasoning:
                await on_reasoning(reasoning)
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

        fin = actual_finish or ("tool_calls" if tool_calls else "stop")
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
