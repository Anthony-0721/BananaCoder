import pytest
from unittest.mock import AsyncMock, MagicMock
from banana.providers.openai_compat import OpenAICompatProvider


class TestOpenAICompatProvider:
    def test_get_default_model(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="deepseek-chat")
        assert p.get_default_model() == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_chat_text_response(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="test-model")
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 5
        p._client.chat.completions.create = AsyncMock(return_value=mock_completion)

        resp = await p.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "Hello!"
        assert resp.finish_reason == "stop"
        assert not resp.has_tool_calls

    @pytest.mark.asyncio
    async def test_chat_tool_call_response(self):
        p = OpenAICompatProvider(api_key="sk-xxx", default_model="test-model")
        mock_tc = MagicMock()
        mock_tc.id = "call_1"
        mock_tc.function.name = "bash"
        mock_tc.function.arguments = '{"command": "ls"}'
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = [mock_tc]
        mock_choice.finish_reason = "tool_calls"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 5
        p._client.chat.completions.create = AsyncMock(return_value=mock_completion)

        resp = await p.chat(messages=[{"role": "user", "content": "list files"}])
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "bash"
        assert resp.tool_calls[0].arguments == {"command": "ls"}
