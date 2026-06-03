"""Sub-agent manager."""
from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from banana.prompts.subagent import AGENT_DEFINITIONS

if TYPE_CHECKING:
    from banana.providers.base import LLMProvider
    from banana.tools.registry import ToolRegistry


class SubagentManager:
    """Manages subagent execution.

    Supports both synchronous (run_subagent) and background (spawn) modes.
    Background agents run as asyncio.Tasks; results are collected via
    collect_completed() and injected into the main agent's message loop.
    """

    def __init__(self, provider: "LLMProvider", tools: "ToolRegistry"):
        self.provider = provider
        self.tools = tools
        self._background_tasks: dict[str, asyncio.Task] = {}
        self._completed: dict[str, str] = {}

    def _filter_tools(self, definition) -> "ToolRegistry":
        if definition.tools is None:
            return self.tools
        from banana.tools.registry import ToolRegistry
        filtered = ToolRegistry()
        for tool_name in definition.tools:
            tool = self.tools.get(tool_name)
            if tool:
                filtered.register(tool)
        return filtered

    async def run_subagent(self, prompt: str, agent_type: str = "Explore",
                           timeout: int = 300) -> str:
        """Run a subagent synchronously and return the result text."""
        definition = AGENT_DEFINITIONS.get(agent_type)
        if not definition:
            return f"Unknown agent type '{agent_type}'. Available: {', '.join(AGENT_DEFINITIONS)}"

        sub_tools = self._filter_tools(definition)

        from banana.agent.runner import AgentRunner
        runner = AgentRunner(
            provider=self.provider,
            tools=sub_tools,
            subagent_manager=None,
            system_prompt_override=definition.system_prompt,
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            result = await asyncio.wait_for(
                runner.run(messages),
                timeout=timeout,
            )
            return result.text
        except asyncio.TimeoutError:
            return f"Sub-agent timed out after {timeout}s"

    # ---- Background subagent API ----

    async def spawn(self, prompt: str, agent_type: str = "Explore",
                    timeout: int = 300) -> str:
        """Launch a background subagent.

        Returns immediately with a task ID. The result is stored internally
        and can be retrieved via collect_completed(). The main agent's loop
        will inject completed results automatically on each iteration.
        """
        task_id = uuid.uuid4().hex[:8]

        task = asyncio.create_task(
            self._run_background(task_id, prompt, agent_type, timeout),
        )
        self._background_tasks[task_id] = task
        task.add_done_callback(lambda _: self._background_tasks.pop(task_id, None))

        return task_id

    async def _run_background(self, task_id: str, prompt: str,
                              agent_type: str, timeout: int):
        """Execute a subagent in background and store the result."""
        try:
            result = await self.run_subagent(prompt, agent_type, timeout)
            if len(result) > 5000:
                result = result[:4500] + f"\n... (truncated, {len(result)} chars total)"
            self._completed[task_id] = result
        except Exception as e:
            self._completed[task_id] = f"[Background agent error] {e}"

    def collect_completed(self) -> list[tuple[str, str]]:
        """Return all completed background agent results and clear them.

        Returns list of (task_id, result) tuples for the main loop to inject.
        """
        results = list(self._completed.items())
        self._completed.clear()
        return results

    def cancel_all_background(self):
        """Cancel all running background tasks."""
        for task in self._background_tasks.values():
            task.cancel()
        self._background_tasks.clear()
        self._completed.clear()
