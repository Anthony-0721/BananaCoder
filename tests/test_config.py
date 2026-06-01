import json
import pytest
from banana.config.loader import load_config, resolve_env_vars
from banana.config.schema import (
    ProviderConfig,
    ModelPresetConfig,
    MCPServerConfig,
    AgentConfig,
    Config,
)


class TestProviderConfig:
    def test_minimal_provider(self):
        p = ProviderConfig(api_key="sk-xxx")
        assert p.api_key == "sk-xxx"
        assert p.api_base is None

    def test_full_provider(self):
        p = ProviderConfig(
            api_key="sk-xxx",
            api_base="https://api.deepseek.com/v1",
            extra_headers={"X-Custom": "value"},
            extra_body={"stream": True},
        )
        assert p.api_base == "https://api.deepseek.com/v1"
        assert p.extra_headers == {"X-Custom": "value"}


class TestModelPresetConfig:
    def test_defaults(self):
        m = ModelPresetConfig(model="deepseek-chat", provider="deepseek")
        assert m.max_tokens == 4096
        assert m.temperature == 0.7
        assert m.context_window_tokens == 128000

    def test_to_generation_settings(self):
        m = ModelPresetConfig(
            model="deepseek-chat",
            provider="deepseek",
            temperature=0.3,
            max_tokens=8192,
            reasoning_effort="high",
        )
        gs = m.to_generation_settings()
        assert gs.temperature == 0.3
        assert gs.max_tokens == 8192
        assert gs.reasoning_effort == "high"


class TestMCPServerConfig:
    def test_stdio_server(self):
        cfg = MCPServerConfig(
            type="stdio",
            command="npx",
            args=["-y", "mcp-server"],
            enabled_tools=["*"],
        )
        assert cfg.type == "stdio"
        assert cfg.command == "npx"

    def test_http_server(self):
        cfg = MCPServerConfig(
            type="streamableHttp",
            url="http://localhost:3000/mcp",
            headers={"Authorization": "Bearer xxx"},
            enabled_tools=["query"],
        )
        assert cfg.url == "http://localhost:3000/mcp"
        assert cfg.enabled_tools == ["query"]


class TestConfig:
    def test_minimal_config(self):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek")
            },
        )
        assert cfg.model_presets["default"].model == "deepseek-chat"

    def test_resolve_preset(self, temp_dir):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
                "fast": ModelPresetConfig(model="deepseek-chat", provider="deepseek", max_tokens=1024),
            },
        )
        resolved = cfg.resolve_preset("fast")
        assert resolved.max_tokens == 1024

    def test_get_provider_name(self):
        cfg = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
            },
        )
        preset = cfg.model_presets["default"]
        assert cfg.get_provider_name("deepseek-chat", preset=preset) == "deepseek"

    def test_fallback_models(self):
        cfg = Config(
            providers={
                "deepseek": ProviderConfig(api_key="sk-xxx"),
                "qwen": ProviderConfig(api_key="sk-yyy", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"),
            },
            model_presets={
                "default": ModelPresetConfig(model="deepseek-chat", provider="deepseek"),
            },
            fallback_models=["qwen-plus"],
            fallback_providers={"qwen-plus": "qwen"},
        )
        assert cfg.fallback_models == ["qwen-plus"]


class TestConfigLoader:
    def test_load_from_path(self, temp_home):
        config_dir = temp_home / ".bananacoder"
        config_dir.mkdir(parents=True)
        cfg = {
            "providers": {"deepseek": {"api_key": "sk-xxx"}},
            "model_presets": {"default": {"model": "deepseek-chat", "provider": "deepseek"}},
        }
        (config_dir / "config.json").write_text(json.dumps(cfg))

        result = load_config(config_dir / "config.json")
        assert result.providers["deepseek"].api_key == "sk-xxx"

    def test_load_defaults(self):
        result = load_config(None)
        assert isinstance(result, Config)

    def test_resolve_env_vars(self):
        import os
        os.environ["TEST_KEY"] = "env-value"
        cfg = Config(
            providers={"test": ProviderConfig(api_key="$TEST_KEY")},
            model_presets={"default": ModelPresetConfig(model="m", provider="test")},
        )
        resolved = resolve_env_vars(cfg)
        assert resolved.providers["test"].api_key == "env-value"
