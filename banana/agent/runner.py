"""AgentRunner: executes LLM <-> Tools loop."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from banana.providers.base import LLMProvider, LLMResponse
from banana.prompts.system import FALLBACK_SYSTEM_PROMPT
from banana.agent.context import ContextManager
from banana.hook import HookContext
from banana.tools.registry import ToolRegistry


@dataclass
class RunResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration: float = 0.0
    iterations: int = 0


class AgentRunner:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry,
        subagent_manager=None,
        system_prompt_override: str | None = None,
        hook_manager=None,
        max_rounds: int = 50,
        max_tool_result_chars: int = 80000,
        context_window_tokens: int = 128_000,
    ):
        self.provider = provider
        self.tools = tools
        self.subagent_manager = subagent_manager
        self.system_prompt_override = system_prompt_override
        self.hook_manager = hook_manager
        self.max_rounds = max_rounds
        self.max_tool_result_chars = max_tool_result_chars
        self.context = ContextManager(max_tokens=context_window_tokens)

    async def run(
        self, messages: list[dict[str, Any]],
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_tool: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_result: Callable[[str, str], Awaitable[None]] | None = None,
        on_llm_start: Callable[[], Awaitable[None]] | None = None,
        on_turn_complete: Callable[..., Awaitable[None]] | None = None,
        on_reasoning: Callable[[str], Awaitable[None]] | None = None,
    ) -> RunResult:
        system_msg = self.system_prompt_override or FALLBACK_SYSTEM_PROMPT
        empty_count = 0
        total_prompt = 0
        total_completion = 0
        iterations = 0

        for _ in range(self.max_rounds):
            iterations += 1
            turn_start = time.monotonic()

            # Compression with notification
            before_tok = self.context.estimate_tokens(messages)
            compressed_type = await self.context.compress(messages, self.provider)
            if compressed_type and on_turn_complete:
                after_tok = self.context.estimate_tokens(messages)
                await on_turn_complete(0, 0, 0.0, info=f"Context: {before_tok}→{after_tok} ({compressed_type})")

            full = [{"role": "system", "content": system_msg}] + messages

            if self.hook_manager:
                hctx = HookContext(messages=full, iteration=_)
                await self.hook_manager.before_llm_call(hctx)

            if on_llm_start:
                await on_llm_start()

            response = await self.provider.chat_stream_with_retry(
                messages=full,
                tools=self.tools.get_definitions() if len(self.tools) > 0 else None,
                on_content_delta=on_token,
                on_reasoning=on_reasoning,
            )
            turn_elapsed = time.monotonic() - turn_start
            total_prompt += response.usage.get("prompt_tokens", 0)
            total_completion += response.usage.get("completion_tokens", 0)

            if response.finish_reason == "error":
                msg = response.content or "Model error"
                messages.append({"role": "assistant", "content": msg})
                if on_token:
                    await on_token(msg)
                if on_turn_complete:
                    await on_turn_complete(total_prompt, total_completion, turn_elapsed, window=self.context.max_tokens)
                return RunResult(msg, total_prompt, total_completion, turn_elapsed, iterations)

            if response.finish_reason == "length" and response.content:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": "Continue from where you left off. Response was truncated."})
                continue

            if not response.content and not response.tool_calls:
                empty_count += 1
                if empty_count >= 3:
                    if on_turn_complete:
                        await on_turn_complete(total_prompt, total_completion, turn_elapsed, window=self.context.max_tokens)
                    return RunResult("(empty)", total_prompt, total_completion, turn_elapsed, iterations)
                messages.append({"role": "user", "content": "Please respond with text."})
                continue
            empty_count = 0

            messages.append(self._build_assistant_message(response))

            if not response.tool_calls:
                if on_turn_complete:
                    await on_turn_complete(total_prompt, total_completion, turn_elapsed, window=self.context.max_tokens)
                return RunResult(response.content or "", total_prompt, total_completion, turn_elapsed, iterations)

            tool_results = await self._execute_tools(response.tool_calls, on_tool)
            turn_elapsed = time.monotonic() - turn_start
            for tc, result in zip(response.tool_calls, tool_results):
                truncated = self._truncate_result(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": truncated,
                })
                if on_tool_result:
                    await on_tool_result(tc.name, truncated)

            if on_turn_complete:
                await on_turn_complete(total_prompt, total_completion, turn_elapsed, window=self.context.max_tokens)

        if on_turn_complete:
            await on_turn_complete(total_prompt, total_completion, turn_elapsed, window=self.context.max_tokens)
        return RunResult("(max rounds)", total_prompt, total_completion, time.monotonic() - turn_start, iterations)

    async def _execute_tools(self, tool_calls, on_tool=None) -> list[str]:
        blocked: set[str] = set()
        if self.hook_manager:
            for tc in tool_calls:
                hctx = HookContext(tool_name=tc.name, tool_args=tc.arguments)
                if not await self.hook_manager.before_tool_execute(hctx):
                    blocked.add(tc.id)

        parallel_calls = []
        serial_calls = []
        for tc in tool_calls:
            if tc.id in blocked:
                continue
            tool = self.tools.get(tc.name)
            if tool and tool.concurrency_safe:
                parallel_calls.append(tc)
            else:
                serial_calls.append(tc)

        results: list[tuple[int, str]] = []

        for tc in tool_calls:
            if tc.id in blocked:
                results.append((tool_calls.index(tc), "Error: Blocked by hook policy"))

        if parallel_calls:
            if on_tool:
                for tc in parallel_calls:
                    await on_tool(tc.name, tc.arguments)
            parallel_results = await asyncio.gather(
                *(self.tools.execute(tc.name, tc.arguments) for tc in parallel_calls),
                return_exceptions=True,
            )
            for tc, r in zip(parallel_calls, parallel_results):
                results.append((tool_calls.index(tc), str(r) if not isinstance(r, Exception) else f"Error: {r}"))

        for tc in serial_calls:
            idx = tool_calls.index(tc)
            if on_tool:
                await on_tool(tc.name, tc.arguments)
            r = await self.tools.execute(tc.name, tc.arguments)
            results.append((idx, str(r)))

        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    def _build_assistant_message(self, response: LLMResponse) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": response.content or None}
        if response.tool_calls:
            import json
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                }
                for tc in response.tool_calls
            ]
        return msg

    def _truncate_result(self, result: str) -> str:
        if len(result) <= self.max_tool_result_chars:
            return result
        return result[:self.max_tool_result_chars] + f"\n\n... (truncated, {len(result)} chars total)"
