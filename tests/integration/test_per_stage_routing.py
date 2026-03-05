"""Integration tests for per-stage LLM model routing (ADR-032).

Verifies that each pipeline stage uses the model it was configured with.
Uses the AgentLoop.__new__() + direct injection pattern established in
existing integration tests.
"""

import pytest

from sophia.config import Settings
from sophia.core.loop import AgentLoop
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


class TrackingMockProvider(MockLLMProvider):
    """MockLLMProvider subclass that records which model it was constructed with."""

    def __init__(self, model_name: str, responses: list | None = None):
        super().__init__(responses)
        self.model_name = model_name


def _make_loop_with_tracking_providers(
    overrides: dict[str, str | None],
    responses: list[str],
) -> tuple[AgentLoop, dict[str, TrackingMockProvider]]:
    """Build an AgentLoop with TrackingMockProviders wired to each stage.

    Returns the loop and a dict mapping stage names to their providers.
    """
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="sonnet-fallback",
        **{f"llm_model_{k}": v for k, v in overrides.items()},
    )

    # Create a fallback provider
    fallback = TrackingMockProvider("sonnet-fallback", list(responses))

    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )

    return loop, fallback


# ── Wiring tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_input_gate_uses_configured_model():
    """When llm_model_input_gate is set, the input gate gets a new provider."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        llm_model_input_gate="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    # Input gate should NOT use the fallback — it should have its own provider
    assert loop.input_gate.llm is not fallback
    assert loop.input_gate.llm.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_proposer_uses_configured_model():
    """When llm_model_proposer is set, the proposer gets a new provider."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        llm_model_proposer="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    assert loop.proposer.llm is not fallback
    assert loop.proposer.llm.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_evaluators_use_configured_model():
    """When llm_model_evaluators is set, all four evaluators share the same model."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        llm_model_evaluators="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    assert len(loop.evaluators) == 4
    for evaluator in loop.evaluators:
        assert evaluator.llm is not fallback
        assert evaluator.llm.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_response_generator_uses_configured_model():
    """When llm_model_response_gen is set, the response generator uses it."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        llm_model_response_gen="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    assert loop.response_generator.llm is not fallback
    assert loop.response_generator.llm.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_memory_extractor_uses_configured_model():
    """When llm_model_memory is set, the memory extractor uses it."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        llm_model_memory="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    assert loop.memory_extractor.llm is not fallback
    assert loop.memory_extractor.llm.model == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_unconfigured_stage_uses_fallback_model():
    """When a stage override is None, it uses self.llm (the fallback instance)."""
    from pathlib import Path
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        default_hat="customer-service",
        memory_provider="mock",
        llm_model="claude-sonnet-4-6",
        # Only set evaluators — everything else should use fallback
        llm_model_evaluators="claude-haiku-4-5-20251001",
    )

    fallback = TrackingMockProvider("claude-sonnet-4-6")
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = fallback
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    # Unconfigured stages should be the exact same object as fallback
    assert loop.input_gate.llm is fallback
    assert loop.proposer.llm is fallback
    assert loop.consequence_engine.llm is fallback
    assert loop.response_generator.llm is fallback
    assert loop.memory_extractor.llm is fallback

    # Configured stage should NOT be the fallback
    for evaluator in loop.evaluators:
        assert evaluator.llm is not fallback
