"""3-layer context compression."""
from __future__ import annotations

from typing import TYPE_CHECKING

from banana.prompts.context import (
    SUMMARY_SYSTEM_PROMPT,
    CONTEXT_COMPRESSED_PREFIX,
    HARD_RESET_PREFIX,
    CONTEXT_ACK,
    HARD_RESET_ACK,
)

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider


def _approx_tokens(text: str) -> int:
    return len(text) // 3


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += _approx_tokens(content)
        tool_calls = m.get("tool_calls")
        if tool_calls:
            total += _approx_tokens(str(tool_calls))
    return total


class ContextManager:
    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        self._snip_at = int(max_tokens * 0.50)
        self._summarize_at = int(max_tokens * 0.70)
        self._collapse_at = int(max_tokens * 0.90)

    @staticmethod
    def estimate_tokens(messages: list[dict]) -> int:
        return estimate_tokens(messages)

    async def compress(self, messages: list[dict], provider: "LLMProvider | None" = None) -> str:
        """Compress if over thresholds. Returns '' or 'snip'/'summarize'/'collapse'."""
        current = estimate_tokens(messages)
        compressed = ""

        if current > self._snip_at:
            if self._snip_tool_outputs(messages):
                compressed = "snip"
                current = estimate_tokens(messages)

        if current > self._summarize_at and len(messages) > 10:
            if await self._summarize(messages, provider, keep_recent=8):
                compressed = "summarize"
                current = estimate_tokens(messages)

        if current > self._collapse_at and len(messages) > 4:
            await self._hard_collapse(messages, provider)
            compressed = "collapse"

        return compressed

    @staticmethod
    def _snip_tool_outputs(messages: list[dict]) -> bool:
        changed = False
        for m in messages:
            if m.get("role") != "tool":
                continue
            content = m.get("content", "")
            if not isinstance(content, str) or len(content) <= 1500:
                continue
            lines = content.splitlines()
            if len(lines) <= 6:
                continue
            m["content"] = (
                "\n".join(lines[:3])
                + f"\n... ({len(lines)} lines snipped) ...\n"
                + "\n".join(lines[-3:])
            )
            changed = True
        return changed

    async def _summarize(self, messages: list[dict], provider, keep_recent: int = 8) -> bool:
        if len(messages) <= keep_recent:
            return False
        old = messages[:-keep_recent]
        recent = messages[-keep_recent:]  # Store BEFORE clearing
        summary = await self._get_summary(old, provider)
        messages.clear()
        messages.append({"role": "user", "content": f"{CONTEXT_COMPRESSED_PREFIX}\n{summary}"})
        messages.append({"role": "assistant", "content": CONTEXT_ACK})
        messages.extend(recent)  # Use stored recent
        return True

    async def _hard_collapse(self, messages: list[dict], provider):
        tail = messages[-4:] if len(messages) > 4 else messages[-2:]
        summary = await self._get_summary(messages[:-len(tail)], provider)
        messages.clear()
        messages.append({"role": "user", "content": f"{HARD_RESET_PREFIX}\n{summary}"})
        messages.append({"role": "assistant", "content": HARD_RESET_ACK})
        messages.extend(tail)

    async def _get_summary(self, messages: list[dict], provider) -> str:
        flat = "\n".join(
            f"[{m.get('role', '?')}] {str(m.get('content', ''))[:300]}"
            for m in messages
        )
        if provider:
            try:
                resp = await provider.chat(
                    messages=[
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": flat[:12000]},
                    ],
                )
                return resp.content or "(summary unavailable)"
            except Exception:
                pass
        return self._extract_key_info(messages)

    @staticmethod
    def _extract_key_info(messages: list[dict]) -> str:
        import re
        files_seen = set()
        for m in messages:
            text = m.get("content", "")
            if isinstance(text, str):
                for match in re.finditer(r'[\w./\-]+\.\w{1,5}', text):
                    files_seen.add(match.group())
        parts = []
        if files_seen:
            parts.append(f"Files: {', '.join(sorted(files_seen)[:20])}")
        return "\n".join(parts) or "(no extractable context)"
