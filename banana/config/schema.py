"""Pydantic config models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None
    region: str | None = None
    profile: str | None = None


class ModelPresetConfig(BaseModel):
    model: str
    provider: str
    max_tokens: int = 4096
    temperature: float = 0.7
    reasoning_effort: str | None = None
    context_window_tokens: int = 128000

    def to_generation_settings(self) -> "GenerationSettings":
        from banana.providers.base import GenerationSettings
        return GenerationSettings(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
        )


class MCPServerConfig(BaseModel):
    type: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    url: str = ""
    headers: dict[str, str] | None = None
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])
    tool_timeout: int = 30


class AgentConfig(BaseModel):
    max_tool_rounds: int = 50
    max_tool_result_chars: int = 80000


class ToolsConfig(BaseModel):
    disabled: list[str] = Field(default_factory=list)
    tavily_api_key: str = ""


class Config(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_presets: dict[str, ModelPresetConfig] = Field(default_factory=dict)
    fallback_models: list[str] = Field(default_factory=list)
    fallback_providers: dict[str, str] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    def resolve_preset(self, name: str | None) -> ModelPresetConfig:
        return self.model_presets[name or "default"]

    def get_provider_name(self, model: str, *, preset: ModelPresetConfig) -> str:
        return preset.provider

    def get_provider(self, model: str, *, preset: ModelPresetConfig) -> ProviderConfig:
        name = self.get_provider_name(model, preset=preset)
        return self.providers.get(name, ProviderConfig())

    def get_api_key(self, model: str, *, preset: ModelPresetConfig) -> str:
        p = self.get_provider(model, preset=preset)
        return p.api_key

    def get_api_base(self, model: str, *, preset: ModelPresetConfig) -> str | None:
        p = self.get_provider(model, preset=preset)
        return p.api_base
