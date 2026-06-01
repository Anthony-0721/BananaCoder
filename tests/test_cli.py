import pytest
from pathlib import Path


class TestBuildTools:
    def test_all_tools_registered(self, temp_home):
        from banana.cli.app import build_tools
        from banana.config.schema import Config, ProviderConfig, ModelPresetConfig
        from banana.skills.loader import SkillsLoader

        config = Config(
            providers={"test": ProviderConfig(api_key="sk-xxx")},
            model_presets={"default": ModelPresetConfig(model="t", provider="test")},
        )
        loader = SkillsLoader(temp_home)
        registry = build_tools(config, loader)
        tool_names = registry.tool_names
        assert "bash" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names
        assert "web_fetch" in tool_names
        assert "agent" in tool_names
        assert "ask_user" in tool_names
        assert "todo_write" in tool_names
        assert "load_skill" in tool_names


class TestFullIntegration:
    """End-to-end test with fake provider."""
    @pytest.mark.asyncio
    async def test_full_flow(self, temp_home, monkeypatch):
        monkeypatch.chdir(temp_home)

        from banana.config.schema import Config, ProviderConfig, ModelPresetConfig
        from banana.tools.bash import BashTool
        from banana.tools.registry import ToolRegistry
        from banana.session.manager import SessionManager
        from banana.skills.loader import SkillsLoader
        from banana.agent.loop import Agent

        config = Config(
            providers={"test": ProviderConfig(api_key="sk-test")},
            model_presets={"default": ModelPresetConfig(model="test", provider="test")},
        )

        class FakeProvider:
            async def chat_stream_with_retry(self, messages, tools, on_content_delta=None, **kw):
                if on_content_delta:
                    await on_content_delta("Hello from test!")
                from banana.providers.base import LLMResponse
                return LLMResponse(content="Hello from test!")

        provider = FakeProvider()
        registry = ToolRegistry()
        registry.register(BashTool())
        loader = SkillsLoader(temp_home)
        session_mgr = SessionManager(temp_home / ".bananacoder", temp_home)

        agent = Agent(provider, registry, session_mgr, loader)
        result = await agent.chat("say hi")
        assert "Hello from test!" in result
