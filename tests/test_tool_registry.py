import pytest
from banana.tools.base import Tool
from banana.tools.registry import ToolRegistry


class FakeReadTool(Tool):
    name = "read_file"
    description = "Read a file"
    parameters = {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
    }
    read_only = True

    async def execute(self, file_path: str) -> str:
        return f"contents of {file_path}"


class FakeWriteTool(Tool):
    name = "write_file"
    description = "Write a file"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> str:
        return f"wrote {file_path}"


class TestToolRegistry:
    def test_register_and_get(self):
        r = ToolRegistry()
        t = FakeReadTool()
        r.register(t)
        assert r.get("read_file") is t
        assert r.has("read_file")

    def test_get_definitions(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        r.register(FakeWriteTool())
        defs = r.get_definitions()
        assert len(defs) == 2
        names = [d["function"]["name"] for d in defs]
        assert names == ["read_file", "write_file"]

    @pytest.mark.asyncio
    async def test_execute_success(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        result = await r.execute("read_file", {"file_path": "/tmp/test.txt"})
        assert "contents of" in str(result)

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        r = ToolRegistry()
        result = await r.execute("nonexistent", {})
        assert "not found" in str(result)

    @pytest.mark.asyncio
    async def test_execute_missing_required(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        result = await r.execute("read_file", {})
        assert "missing" in str(result).lower()

    def test_unregister(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        r.unregister("read_file")
        assert not r.has("read_file")

    def test_len(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        r.register(FakeWriteTool())
        assert len(r) == 2

    def test_definitions_cached(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        defs1 = r.get_definitions()
        defs2 = r.get_definitions()
        assert defs1 is defs2  # Same cached list

    def test_mcp_sorting(self):
        r = ToolRegistry()
        r.register(FakeReadTool())
        # Fake an MCP tool
        class MCPTool(Tool):
            name = "mcp_test_server_read"
            description = "MCP tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            async def execute(self, **kw): return "ok"
        r.register(MCPTool())
        defs = r.get_definitions()
        names = [d["function"]["name"] for d in defs]
        # builtins sorted first, then MCP
        assert names[0] == "read_file"
        assert names[1] == "mcp_test_server_read"
