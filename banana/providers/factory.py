"""Create providers from config."""
from __future__ import annotations

from banana.config.schema import Config
from banana.providers.base import LLMProvider
from banana.providers.openai_compat import OpenAICompatProvider
from banana.providers.anthropic import AnthropicProvider
from banana.providers.fallback import FallbackProvider


def _make_single_provider(config: Config, model: str, provider_name: str | None = None) -> LLMProvider:
    """Create a single provider for a model."""
    preset = config.model_presets.get("default")
    if not preset:
        raise ValueError("No default model preset configured")
    name = provider_name or config.get_provider_name(model, preset=preset)
    p = config.providers.get(name)
    api_key = p.api_key if p else ""
    api_base = p.api_base if p else None

    if name == "anthropic":
        return AnthropicProvider(
            api_key=api_key, api_base=api_base, default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        return OpenAICompatProvider(
            api_key=api_key, api_base=api_base, default_model=model,
            extra_headers=p.extra_headers if p else None,
            extra_body=p.extra_body if p else None,
        )


def make_provider(config: Config) -> LLMProvider:
    """Create the full provider chain from config."""
    default_preset = config.model_presets.get("default")
    if not default_preset:
        raise ValueError("No default model preset in config")

    primary = _make_single_provider(config, default_preset.model)
    primary.generation = default_preset.to_generation_settings()

    fallback_providers = []
    for fb_model in config.fallback_models:
        fb_name = config.fallback_providers.get(fb_model, "openai_compat")
        fb = _make_single_provider(config, fb_model, provider_name=fb_name)
        fallback_providers.append(fb)

    if fallback_providers:
        return FallbackProvider([primary] + fallback_providers)
    return primary
