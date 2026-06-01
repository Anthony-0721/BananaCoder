import pytest
from banana.providers.base import LLMResponse, LLMProvider
from banana.providers.fallback import FallbackProvider
from banana.providers.factory import make_provider
from banana.config.schema import Config, ProviderConfig, ModelPresetConfig


class FakeProvider(LLMProvider):
    def __init__(self, name: str, responses: list[LLMResponse]):
        super().__init__()
        self.name = name
        self._responses = responses
        self._call_count = 0

    def get_default_model(self) -> str:
        return self.name

    async def chat(self, **kwargs):
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return LLMResponse(content=f"OK from {self.name}")

    async def chat_stream(self, **kwargs):
        return await self.chat(**kwargs)


class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_first_succeeds(self):
        p1 = FakeProvider("p1", [LLMResponse(content="hello from p1")])
        fb = FallbackProvider([p1])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "hello from p1"

    @pytest.mark.asyncio
    async def test_fallback_on_transient(self):
        p1 = FakeProvider("p1", [LLMResponse(content="rate limit", finish_reason="error",
                                              error_status_code=429, error_type="rate_limit_exceeded")])
        p2 = FakeProvider("p2", [LLMResponse(content="hello from fallback")])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.content == "hello from fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_on_quota(self):
        p1 = FakeProvider("p1", [LLMResponse(content="quota exceeded", finish_reason="error",
                                              error_status_code=429, error_type="insufficient_quota")])
        p2 = FakeProvider("p2", [])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_all_fail(self):
        p1 = FakeProvider("p1", [LLMResponse(content="e1", finish_reason="error", error_status_code=500)])
        p2 = FakeProvider("p2", [LLMResponse(content="e2", finish_reason="error", error_status_code=500)])
        fb = FallbackProvider([p1, p2])
        resp = await fb.chat(messages=[{"role": "user", "content": "hi"}])
        assert resp.finish_reason == "error"


class TestFactory:
    def test_make_provider_single(self):
        config = Config(
            providers={"deepseek": ProviderConfig(api_key="sk-xxx")},
            model_presets={"default": ModelPresetConfig(model="deepseek-chat", provider="deepseek")},
        )
        provider = make_provider(config)
        assert provider.get_default_model() == "deepseek-chat"

    def test_make_provider_with_fallback(self):
        config = Config(
            providers={
                "deepseek": ProviderConfig(api_key="sk-xxx"),
                "qwen": ProviderConfig(api_key="sk-yyy", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"),
            },
            model_presets={"default": ModelPresetConfig(model="deepseek-chat", provider="deepseek")},
            fallback_models=["qwen-plus"],
            fallback_providers={"qwen-plus": "qwen"},
        )
        provider = make_provider(config)
        from banana.providers.fallback import FallbackProvider
        assert isinstance(provider, FallbackProvider)
