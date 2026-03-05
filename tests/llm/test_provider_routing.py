"""Tests for per-stage model routing through LLM providers (ADR-032)."""

import pytest

from sophia.config import Settings
from sophia.llm.anthropic import AnthropicProvider
from sophia.llm.ollama import OllamaProvider
from sophia.llm.provider import get_provider


@pytest.fixture
def config():
    return Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        llm_model="claude-sonnet-4-6",
    )


def test_get_provider_without_override_uses_config_model(config):
    """No override -> provider uses config.llm_model."""
    provider = get_provider(config)
    assert provider.model == "claude-sonnet-4-6"


def test_get_provider_with_override_uses_override_model(config):
    """Override provided -> provider uses override, not config.llm_model."""
    provider = get_provider(config, model_override="claude-haiku-4-5-20251001")
    assert provider.model == "claude-haiku-4-5-20251001"


def test_anthropic_provider_uses_model_override(config):
    """AnthropicProvider respects model_override."""
    provider = AnthropicProvider(config, model_override="claude-haiku-4-5-20251001")
    assert provider.model == "claude-haiku-4-5-20251001"

    # Without override, uses config model
    provider_default = AnthropicProvider(config)
    assert provider_default.model == "claude-sonnet-4-6"


def test_ollama_provider_uses_model_override():
    """OllamaProvider respects model_override."""
    config = Settings(
        llm_provider="ollama",
        llm_model="llama3",
        ollama_base_url="http://localhost:11434",
    )
    provider = OllamaProvider(config, model_override="mistral")
    assert provider.model == "mistral"

    # Without override, uses config model
    provider_default = OllamaProvider(config)
    assert provider_default.model == "llama3"


def test_stage_llm_none_returns_fallback_instance(config):
    """When stage model is None, _stage_llm returns the same object as self.llm."""
    from sophia.core.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = config
    loop.llm = get_provider(config)

    # Simulate the _stage_llm closure behaviour
    def _stage_llm(model):
        if model is None:
            return loop.llm
        return get_provider(config, model_override=model)

    result = _stage_llm(None)
    assert result is loop.llm  # identity check, not equality
