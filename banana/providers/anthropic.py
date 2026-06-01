"""Anthropic provider using the native SDK."""
from __future__ import annotations

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

        # Prompt caching: cache system + tools (stable across turns)
        if isinstance(system, str) and system:
            system = [
                {"type": "text", "text": system},
                {"type": "text", "text": "<cached>", "cache_control": {"type": "ephemeral"}},
            ]
        if tools_anthropic:
            tools_anthropic[-1]["cache_control"] = {"type": "ephemeral"}

        # Cache the last few messages too (they're stable within a turn)
        if anthropic_msgs and len(anthropic_msgs) >= 2:
            anthropic_msgs[-2].setdefault("cache_control", {"type": "ephemeral"})

        params: dict[str, Any] = {
            "model": model, "messages": anthropic_msgs,
            "max_tokens": max(1, max_tokens), "temperature": temperature,
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
