import pytest
from banana.providers.base import LLMResponse, ToolCallRequest
from banana.agent.runner import AgentRunner
from banana.tools.registry import ToolRegistry
from banana.tools.base import Tool


class FakeProvider:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self._idx = 0

    async def chat_stream_with_retry(self, messages, tools, on_content_delta=None, **kwargs):
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            if on_content_delta and resp.content:
                await on_content_delta(resp.content)
            return resp
        return LLMResponse(content="done")


class EchoTool(Tool):
    name = "echo"
    description = "Echo back"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    concurrency_safe = True

    async def execute(self, text: str) -> str:
        return f"echo: {text}"


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        p = FakeProvider([LLMResponse(content="Hello!")])
        r = ToolRegistry()
        runner = AgentRunner(p, r)
        messages = [{"role": "user", "content": "hi"}]
        result = await runner.run(messages)
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_loop(self):
        p = FakeProvider([
            LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(id="c1", name="echo", arguments={"text": "hi"})],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="Got your echo!"),
        ])
        r = ToolRegistry()
        r.register(EchoTool())
        runner = AgentRunner(p, r)
        messages = [{"role": "user", "content": "echo hi"}]
        result = await runner.run(messages)
        assert result == "Got your echo!"
        assert any(m["role"] == "tool" and "echo: hi" in str(m["content"]) for m in messages)

    @pytest.mark.asyncio
    async def test_max_rounds(self):
        tc = ToolCallRequest(id="c0", name="echo", arguments={"text": "x"})
        responses = [
            LLMResponse(content=None, tool_calls=[tc], finish_reason="tool_calls")
        ] * 100
        p = FakeProvider(responses)
        r = ToolRegistry()
        r.register(EchoTool())
        runner = AgentRunner(p, r, max_rounds=3)
        messages = [{"role": "user", "content": "loop"}]
        result = await runner.run(messages)
        assert "maximum" in result

    @pytest.mark.asyncio
    async def test_error_response(self):
        p = FakeProvider([LLMResponse(content="Server error", finish_reason="error")])
        r = ToolRegistry()
        runner = AgentRunner(p, r)
        messages = [{"role": "user", "content": "hi"}]
        result = await runner.run(messages)
        assert "error" in result.lower()
