import pytest
from banana.tools.bash import BashTool
from banana.tools.filesystem import ReadFileTool, WriteFileTool, EditTool
from banana.tools.search import GlobTool, GrepTool
from banana.tools.todo import TodoWriteTool
from banana.tools.agent_tool import AgentTool


class TestBashTool:
    @pytest.fixture(autouse=True)
    def _yolo_mode(self):
        from banana.security import get_security, SecurityMode
        get_security().mode = SecurityMode.YOLO

    @pytest.mark.asyncio
    async def test_simple_echo(self):
        t = BashTool()
        result = await t.execute(command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_missing_command(self):
        t = BashTool()
        result = await t.execute(command="nonexistent_command_xyz")
        assert "FAILED" in result or "127" in result

    @pytest.mark.asyncio
    async def test_timeout(self):
        t = BashTool()
        result = await t.execute(command="sleep 10", timeout=1)
        assert "timed out" in result.lower()


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read(self, temp_dir):
        f = temp_dir / "test.txt"
        f.write_text("line1\nline2\n")
        t = ReadFileTool()
        result = await t.execute(file_path=str(f))
        assert "line1" in result
        assert "line2" in result

    @pytest.mark.asyncio
    async def test_not_found(self, temp_dir):
        t = ReadFileTool()
        result = await t.execute(file_path=str(temp_dir / "nonexistent.txt"))
        assert "FAILED" in result


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write(self, temp_dir):
        f = temp_dir / "out.txt"
        t = WriteFileTool()
        result = await t.execute(file_path=str(f), content="hello world")
        assert "[OK]" in result
        assert f.read_text() == "hello world"


class TestEdit:
    @pytest.mark.asyncio
    async def test_edit_single_match(self, temp_dir):
        f = temp_dir / "code.py"
        f.write_text("x = 1\n")
        t = EditTool()
        result = await t.execute(file_path=str(f), old_string="x = 1", new_string="x = 2")
        assert "[OK]" in result
        assert f.read_text() == "x = 2\n"

    @pytest.mark.asyncio
    async def test_edit_multiple_matches(self, temp_dir):
        f = temp_dir / "code.py"
        f.write_text("x = 1\nx = 1\n")
        t = EditTool()
        result = await t.execute(file_path=str(f), old_string="x = 1", new_string="x = 2")
        assert "appears 2 times" in result

    @pytest.mark.asyncio
    async def test_edit_not_found(self, temp_dir):
        f = temp_dir / "code.py"
        f.write_text("hello\n")
        t = EditTool()
        result = await t.execute(file_path=str(f), old_string="not there", new_string="x")
        assert "not found" in result.lower() or "FAILED" in result


class TestGlob:
    @pytest.mark.asyncio
    async def test_find_py_files(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        (temp_dir / "c.txt").write_text("")
        t = GlobTool()
        # Change dir for the test
        import os
        old = os.getcwd()
        os.chdir(temp_dir)
        try:
            result = await t.execute(pattern="*.py")
            assert "a.py" in result
            assert "b.py" in result
            assert "c.txt" not in result
        finally:
            os.chdir(old)


class TestGrep:
    @pytest.mark.asyncio
    async def test_find_pattern(self, temp_dir):
        (temp_dir / "code.py").write_text("def foo():\n    pass\ndef bar():\n    pass\n")
        t = GrepTool()
        result = await t.execute(pattern="def foo", path=str(temp_dir / "code.py"))
        assert "def foo" in result

    @pytest.mark.asyncio
    async def test_no_match(self, temp_dir):
        (temp_dir / "code.py").write_text("hello\n")
        t = GrepTool()
        result = await t.execute(pattern="nonexistent", path=str(temp_dir / "code.py"))
        assert "FAILED" in result


class TestTodoWrite:
    @pytest.mark.asyncio
    async def test_simple(self):
        t = TodoWriteTool()
        result = await t.execute(todos=[{"content": "Do X", "status": "pending"}])
        assert "Do X" in result

    @pytest.mark.asyncio
    async def test_empty(self):
        t = TodoWriteTool()
        result = await t.execute(todos=[])
        assert "cleared" in result.lower() or "todo" in result.lower()


class TestAgentTool:
    def test_agent_tool_no_manager(self):
        t = AgentTool()
        assert t.name == "agent"
        assert t._manager is None

    @pytest.mark.asyncio
    async def test_concurrency_safe(self):
        t = AgentTool()
        assert t.concurrency_safe is True

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Multiple agent calls should run in parallel, not serial."""
        import asyncio
        from banana.agent.subagent import SubagentManager

        class MockProvider:
            async def chat_stream_with_retry(self, **kw):
                await asyncio.sleep(0.2)
                from banana.providers.base import LLMResponse
                return LLMResponse(content="mock result")

        class MockTools:
            def get(self, name):
                return None
            def __len__(self):
                return 0
            def get_definitions(self):
                return None
            def has_tools(self):
                return False
            @property
            def tool_names(self):
                return []

        mgr = SubagentManager(MockProvider(), MockTools())
        t = AgentTool(mgr)

        start = asyncio.get_event_loop().time()
        results = await asyncio.gather(
            t.execute(prompt="task 1", subagent_type="general-purpose"),
            t.execute(prompt="task 2", subagent_type="general-purpose"),
            t.execute(prompt="task 3", subagent_type="general-purpose"),
        )
        elapsed = asyncio.get_event_loop().time() - start

        # If serial, would take ~0.6s (3 × 0.2s). Parallel should be ~0.2s.
        assert elapsed < 0.5, f"Parallel execution took {elapsed:.2f}s, expected <0.5s"
        assert len(results) == 3
        for r in results:
            assert "Sub-agent completed" in r


