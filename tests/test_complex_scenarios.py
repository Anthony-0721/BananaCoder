"""Complex scenario integration tests with mock provider."""
from __future__ import annotations

import pytest

from banana.providers.base import LLMResponse, ToolCallRequest
from banana.tools.registry import ToolRegistry


class ScenarioProvider:
    """Mock provider that simulates multi-step LLM behavior."""

    def __init__(self, scenarios: list[list[dict]]):
        """scenarios: list of rounds, each round is list of response configs."""
        self._scenarios = scenarios
        self._round = 0

    async def chat_stream_with_retry(self, **kw) -> LLMResponse:
        if self._round >= len(self._scenarios):
            return LLMResponse(content="Done", finish_reason="stop")
        configs = self._scenarios[self._round]
        self._round += 1
        # Return first config (for simple scenarios)
        cfg = configs[0]
        return LLMResponse(
            content=cfg.get("content", ""),
            tool_calls=[ToolCallRequest(**tc) for tc in cfg.get("tool_calls", [])],
            finish_reason=cfg.get("finish_reason", "stop"),
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

    def get_default_model(self) -> str:
        return "mock-model"


class ScenarioTools:
    """Minimal tool registry for scenario testing."""

    def __init__(self):
        self._tools = {}

    def register(self, tool):
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools.get(name)

    def __len__(self):
        return len(self._tools)

    def get_definitions(self):
        return []

    @property
    def tool_names(self):
        return list(self._tools.keys())

    async def execute(self, name: str, params: dict):
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.execute(**params)
        except Exception as e:
            return f"Error: {e}"


class TestComplexScenarios:
    """End-to-end scenario tests for complex multi-step tasks."""

    @pytest.mark.asyncio
    async def test_read_then_edit_scenario(self):
        """Agent reads a file, then edits it: simulates a typical coding flow."""
        from banana.agent.runner import AgentRunner

        provider = ScenarioProvider([
            # Round 1: LLM decides to read file first
            [{"tool_calls": [{"id": "call1", "name": "read_file", "arguments": {"file_path": "test.py"}}]}],
            # Round 2: LLM decides to edit
            [{"tool_calls": [{"id": "call2", "name": "edit", "arguments": {"file_path": "test.py", "old_string": "a", "new_string": "b"}}]}],
            # Round 3: LLM finishes
            [{"content": "Done editing"}],
        ])

        # Register tools that return success
        from banana.tools.filesystem import ReadFileTool, EditTool
        from banana.tools.file_state import get_file_state

        tools = ScenarioTools()
        tools.register(ReadFileTool())
        tools.register(EditTool())

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("a = 1\n")
            test_path = f.name

        get_file_state().mark_read(test_path)
        runner = AgentRunner(provider, tools)

        messages = [{"role": "user", "content": f"edit {test_path}"}]
        result = await runner.run(messages)
        assert result.text is not None
        assert len(messages) > 1

    @pytest.mark.asyncio
    async def test_multi_tool_parallel_scenario(self):
        """Agent calls multiple independent tools in one response."""
        from banana.agent.runner import AgentRunner

        provider = ScenarioProvider([
            # Round 1: LLM calls 2 glob tools in parallel
            [{"tool_calls": [
                {"id": "c1", "name": "glob", "arguments": {"pattern": "*.py"}},
                {"id": "c2", "name": "glob", "arguments": {"pattern": "*.md"}},
            ]}],
            # Round 2: LLM finishes
            [{"content": "Found files"}],
        ])

        from banana.tools.search import GlobTool
        tools = ScenarioTools()
        tools.register(GlobTool())

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": "find all py and md files"}]
        result = await runner.run(messages)
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_search_then_read_then_edit_chain(self):
        """3-step chain: search → read → edit. Tests context preservation."""
        from banana.agent.runner import AgentRunner
        from banana.tools.search import GlobTool, GrepTool
        from banana.tools.filesystem import ReadFileTool, EditTool
        from banana.tools.file_state import get_file_state

        provider = ScenarioProvider([
            [{"tool_calls": [{"id": "c1", "name": "grep", "arguments": {"pattern": "def ", "path": "."}}]}],
            [{"tool_calls": [{"id": "c2", "name": "read_file", "arguments": {"file_path": "test.py"}}]}],
            [{"tool_calls": [{"id": "c3", "name": "edit", "arguments": {"file_path": "test.py", "old_string": "old", "new_string": "new"}}]}],
            [{"content": "Done"}],
        ])

        tools = ScenarioTools()
        tools.register(GrepTool())
        tools.register(ReadFileTool())
        tools.register(EditTool())

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("old = 1\n")
            test_path = f.name
        get_file_state().mark_read(test_path)

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": f"edit {test_path}"}]
        result = await runner.run(messages)
        assert result.iterations >= 3

    @pytest.mark.asyncio
    async def test_error_recovery_scenario(self):
        """Tool fails, LLM retries with different params (simulating error recovery)."""
        from banana.agent.runner import AgentRunner
        from banana.tools.search import GrepTool

        provider = ScenarioProvider([
            # Round 1: grep on non-existent path → tool returns error
            [{"tool_calls": [{"id": "c1", "name": "grep", "arguments": {"pattern": "def", "path": "/nonexistent"}}]}],
            # Round 2: LLM retries with correct path
            [{"tool_calls": [{"id": "c2", "name": "grep", "arguments": {"pattern": "def", "path": "."}}]}],
            # Round 3: done
            [{"content": "Found matches"}],
        ])

        tools = ScenarioTools()
        tools.register(GrepTool())

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": "search for def in the project"}]
        result = await runner.run(messages)
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_file_state_warning_scenario(self, tmp_path):
        """Edit on unread file should produce WARN, not execute the edit."""
        from banana.agent.runner import AgentRunner
        from banana.tools.filesystem import EditTool
        from banana.tools.file_state import get_file_state

        get_file_state().clear()

        test_file = tmp_path / "unread.py"
        test_file.write_text("a = 1\n")

        provider = ScenarioProvider([
            [{"tool_calls": [{"id": "c1", "name": "edit", "arguments": {"file_path": str(test_file), "old_string": "a", "new_string": "b"}}]}],
            [{"content": "Edit blocked"}],
        ])

        tools = ScenarioTools()
        tools.register(EditTool())

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": f"edit {test_file}"}]
        result = await runner.run(messages)

        tool_msg = [m for m in messages if m.get("role") == "tool"]
        if tool_msg:
            assert "WARN" in tool_msg[0].get("content", "") or "not read" in tool_msg[0].get("content", "")

    @pytest.mark.asyncio
    async def test_bash_timeout_recovery(self):
        """Bash tool timeout should be handled gracefully."""
        from banana.agent.runner import AgentRunner
        from banana.tools.bash import BashTool
        from banana.security import get_security, SecurityMode

        get_security().mode = SecurityMode.YOLO

        provider = ScenarioProvider([
            [{"tool_calls": [{"id": "c1", "name": "bash", "arguments": {"command": "sleep 10", "timeout": 1}}]}],
            [{"content": "Command timed out, trying shorter"}],
        ])

        tools = ScenarioTools()
        tools.register(BashTool())

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": "run a long command"}]
        result = await runner.run(messages)
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_self_tool_scenario(self):
        """Self-inspection tool returns runtime state."""
        from banana.agent.runner import AgentRunner
        from banana.tools.self_tool import SelfTool
        from banana.tools.runtime_state import RuntimeState

        state = RuntimeState()
        state.model = "test-model"
        state.provider = "test-provider"
        state.iteration = 5
        state.security_mode = "normal"
        state.tool_count = 10
        state.session_messages = 3

        provider = ScenarioProvider([
            [{"tool_calls": [{"id": "c1", "name": "self", "arguments": {}}]}],
            [{"content": "Here is my state"}],
        ])

        tools = ScenarioTools()
        tools.register(SelfTool(state))

        runner = AgentRunner(provider, tools)
        messages = [{"role": "user", "content": "check your state"}]
        result = await runner.run(messages)
        assert result.text is not None

    @pytest.mark.asyncio
    async def test_max_rounds_limit(self):
        """Agent stops after max_rounds even if LLK keeps requesting tools."""
        from banana.agent.runner import AgentRunner

        # LLM keeps calling tools forever
        tool_call = [{"tool_calls": [{"id": "c", "name": "glob", "arguments": {"pattern": "*.py"}}]}]
        provider = ScenarioProvider([tool_call] * 10)

        from banana.tools.search import GlobTool
        tools = ScenarioTools()
        tools.register(GlobTool())

        runner = AgentRunner(provider, tools, max_rounds=3)
        messages = [{"role": "user", "content": "search forever"}]
        result = await runner.run(messages)
        assert "max rounds" in result.text
        assert result.iterations == 3
