from banana.tools.mcp import _sanitize_name, _normalize_schema_for_openai


class TestSanitizeName:
    def test_simple(self):
        assert _sanitize_name("hello_world") == "hello_world"

    def test_dots(self):
        assert _sanitize_name("my.tool.name") == "my_tool_name"

    def test_special_chars(self):
        assert _sanitize_name("tool@#$name") == "tool_name"


class TestSchemaNormalize:
    def test_nullable_type(self):
        result = _normalize_schema_for_openai({"type": ["string", "null"]})
        assert result["type"] == "string"
        assert result["nullable"] is True

    def test_nested_properties(self):
        result = _normalize_schema_for_openai({
            "type": "object",
            "properties": {"x": {"type": ["integer", "null"]}},
        })
        assert result["properties"]["x"]["type"] == "integer"
        assert result["properties"]["x"]["nullable"] is True

    def test_default_object(self):
        result = _normalize_schema_for_openai("not a dict")
        assert result == {"type": "object", "properties": {}}
