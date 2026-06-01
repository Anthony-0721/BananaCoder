from banana.providers.base import LLMResponse, ToolCallRequest, GenerationSettings, LLMProvider


class TestToolCallRequest:
    def test_create(self):
        tc = ToolCallRequest(id="call_1", name="bash", arguments={"command": "ls"})
        assert tc.id == "call_1"
        assert tc.name == "bash"
        assert tc.arguments == {"command": "ls"}


class TestLLMResponse:
    def test_text_only(self):
        r = LLMResponse(content="Hello")
        assert r.has_tool_calls is False

    def test_with_tool_calls(self):
        r = LLMResponse(
            content=None,
            tool_calls=[ToolCallRequest(id="1", name="bash", arguments={"command": "ls"})],
            finish_reason="tool_calls",
        )
        assert r.has_tool_calls is True

    def test_error_response(self):
        r = LLMResponse(content="Rate limit exceeded", finish_reason="error",
                        error_status_code=429, error_type="rate_limit_exceeded")
        assert r.finish_reason == "error"
        assert r.error_status_code == 429


class TestGenerationSettings:
    def test_defaults(self):
        gs = GenerationSettings()
        assert gs.temperature == 0.7
        assert gs.max_tokens == 4096


class TestTransientDetection:
    def test_rate_limit_is_transient(self):
        r = LLMResponse(content="rate limit exceeded", finish_reason="error",
                        error_status_code=429, error_type="rate_limit_exceeded")
        assert LLMProvider._is_transient_response(r) is True

    def test_quota_not_transient(self):
        r = LLMResponse(content="insufficient_quota", finish_reason="error",
                        error_status_code=429, error_type="insufficient_quota")
        assert LLMProvider._is_transient_response(r) is False

    def test_500_is_transient(self):
        r = LLMResponse(content="server error", finish_reason="error", error_status_code=500)
        assert LLMProvider._is_transient_response(r) is True

    def test_400_not_transient(self):
        r = LLMResponse(content="bad request", finish_reason="error", error_status_code=400)
        assert LLMProvider._is_transient_response(r) is False


class TestSanitizeMessages:
    def test_empty_content_fix(self):
        msgs = [{"role": "assistant", "content": ""}]
        result = LLMProvider._sanitize_empty_content(msgs)
        assert result[0]["content"] == "(empty)"

    def test_role_alternation_merges_same_role(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "there"},
        ]
        result = LLMProvider._enforce_role_alternation(msgs)
        assert len(result) == 1
        assert "hi" in result[0]["content"]
        assert "there" in result[0]["content"]
