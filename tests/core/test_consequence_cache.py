"""Tests for consequence tree caching (ADR-033)."""

import json

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig
from sophia.tools.base import Tool, ToolResult
from sophia.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider

BENIGN_TREE_JSON = json.dumps(
    {
        "consequences": [
            {
                "description": "Customer receives refund",
                "stakeholders_affected": ["customer", "business"],
                "probability": 0.95,
                "tangibility": 0.9,
                "harm_benefit": 0.6,
                "affected_party": "customer",
                "is_terminal": True,
                "children": [],
            }
        ]
    }
)


def _candidate(
    tool_name: str = "check_order_status",
    order_id: str = "ORD-123",
    **extra_params,
) -> CandidateAction:
    params = {"order_id": order_id, **extra_params}
    return CandidateAction(
        tool_name=tool_name,
        parameters=params,
        reasoning="test",
        expected_outcome="test",
    )


class StubTool(Tool):
    name = "check_order_status"
    description = "stub"
    parameters = {}
    authority_level = "agent"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class ShortTTLTool(Tool):
    name = "short_ttl_tool"
    description = "stub"
    parameters = {}
    authority_level = "agent"
    consequence_cache_ttl = 0

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class CustomTTLTool(Tool):
    name = "custom_ttl_tool"
    description = "stub"
    parameters = {}
    authority_level = "agent"
    consequence_cache_ttl = 120

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


@pytest.mark.asyncio
async def test_cache_miss_generates_tree(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """First call generates a tree, populates the cache, and returns the tree."""
    mock_llm.set_responses([BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)
    tree = await engine.analyze(_candidate())

    assert tree.total_nodes == 1
    assert tree.candidate_action.tool_name == "check_order_status"
    assert len(mock_llm.calls) == 1
    assert engine.cache_stats["entries"] == 1


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_tree_without_llm_call(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Two calls with same tool/parameter shape produce exactly one LLM call."""
    mock_llm.set_responses([BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    tree1 = await engine.analyze(_candidate(order_id="ORD-111"))
    tree2 = await engine.analyze(_candidate(order_id="ORD-222"))

    # Exactly one LLM call — second was a cache hit
    assert len(mock_llm.calls) == 1
    # Both return valid trees
    assert tree1.total_nodes == 1
    assert tree2.total_nodes == 1
    # Cache hit returns tree bound to the second candidate
    assert tree2.candidate_action.parameters["order_id"] == "ORD-222"


@pytest.mark.asyncio
async def test_cache_key_ignores_parameter_values(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Same tool, same param keys, different values → same cache key."""
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    key1 = engine._cache_key(_candidate(order_id="ORD-111"))
    key2 = engine._cache_key(_candidate(order_id="ORD-999"))
    assert key1 == key2


@pytest.mark.asyncio
async def test_cache_key_varies_by_tool_name(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Different tools → different cache keys."""
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    key1 = engine._cache_key(_candidate(tool_name="check_order_status"))
    key2 = engine._cache_key(_candidate(tool_name="offer_full_refund"))
    assert key1 != key2


@pytest.mark.asyncio
async def test_cache_key_varies_by_parameter_shape(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Same tool, different parameter keys → different cache keys."""
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    key1 = engine._cache_key(_candidate(tool_name="tool_a", order_id="x"))
    key2 = engine._cache_key(
        CandidateAction(
            tool_name="tool_a",
            parameters={"customer_id": "x"},
            reasoning="test",
            expected_outcome="test",
        )
    )
    assert key1 != key2


@pytest.mark.asyncio
async def test_cache_key_varies_by_hat_name(mock_llm: MockLLMProvider):
    """Same tool in different hats → different cache keys."""
    from sophia.hats.schema import HatConfig, HatManifest, StakeholderRegistry

    hat_a = HatConfig(
        manifest=HatManifest(name="hat-a", version="1.0", description="A", tool_modules=[]),
        hat_path="/tmp/hat-a",
        stakeholders=StakeholderRegistry(stakeholders=[]),
        constraints={},
    )
    hat_b = HatConfig(
        manifest=HatManifest(name="hat-b", version="1.0", description="B", tool_modules=[]),
        hat_path="/tmp/hat-b",
        stakeholders=StakeholderRegistry(stakeholders=[]),
        constraints={},
    )

    engine_a = ConsequenceEngine(llm=mock_llm, hat_config=hat_a)
    engine_b = ConsequenceEngine(llm=mock_llm, hat_config=hat_b)

    key_a = engine_a._cache_key(_candidate())
    key_b = engine_b._cache_key(_candidate())
    assert key_a != key_b


@pytest.mark.asyncio
async def test_expired_entry_regenerates(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Expired cache entry triggers regeneration."""
    mock_llm.set_responses([BENIGN_TREE_JSON, BENIGN_TREE_JSON])
    # TTL of 0 means entry expires immediately
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, cache_ttl_seconds=0)

    await engine.analyze(_candidate(order_id="ORD-111"))
    await engine.analyze(_candidate(order_id="ORD-222"))

    # Both calls should have hit the LLM (no caching with TTL=0)
    assert len(mock_llm.calls) == 2


@pytest.mark.asyncio
async def test_rebind_candidate_updates_candidate_action(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Cache hit returns tree with the current candidate, not the original."""
    mock_llm.set_responses([BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    original = _candidate(order_id="ORD-ORIGINAL")
    rebound = _candidate(order_id="ORD-REBOUND")

    await engine.analyze(original)
    tree2 = await engine.analyze(rebound)

    assert tree2.candidate_action is rebound
    assert tree2.candidate_action.parameters["order_id"] == "ORD-REBOUND"


@pytest.mark.asyncio
async def test_clear_cache_empties_dict(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """clear_cache() empties the internal cache dict."""
    mock_llm.set_responses([BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)
    await engine.analyze(_candidate())
    assert engine.cache_stats["entries"] == 1

    engine.clear_cache()
    assert engine.cache_stats["entries"] == 0


@pytest.mark.asyncio
async def test_per_tool_ttl_overrides_engine_default(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Tool with consequence_cache_ttl=0 always misses even with 3600s engine default."""
    mock_llm.set_responses([BENIGN_TREE_JSON, BENIGN_TREE_JSON])

    registry = ToolRegistry()
    registry.register(ShortTTLTool())

    engine = ConsequenceEngine(
        llm=mock_llm,
        hat_config=cs_hat_config,
        cache_ttl_seconds=3600,
        tool_registry=registry,
    )

    await engine.analyze(_candidate(tool_name="short_ttl_tool", order_id="ORD-1"))
    await engine.analyze(_candidate(tool_name="short_ttl_tool", order_id="ORD-2"))

    # Both calls should generate (TTL=0 means never cache)
    assert len(mock_llm.calls) == 2


@pytest.mark.asyncio
async def test_per_tool_ttl_none_uses_engine_default(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Tool with consequence_cache_ttl=None uses the engine's default TTL."""
    mock_llm.set_responses([BENIGN_TREE_JSON])

    registry = ToolRegistry()
    registry.register(StubTool())

    engine = ConsequenceEngine(
        llm=mock_llm,
        hat_config=cs_hat_config,
        cache_ttl_seconds=3600,
        tool_registry=registry,
    )

    await engine.analyze(_candidate(order_id="ORD-1"))
    await engine.analyze(_candidate(order_id="ORD-2"))

    # Only one LLM call — second used cache with engine default TTL
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_cache_hit_count_increments(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Cache hit increments the hit_count on the cached entry."""
    mock_llm.set_responses([BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    await engine.analyze(_candidate(order_id="ORD-1"))
    await engine.analyze(_candidate(order_id="ORD-2"))
    await engine.analyze(_candidate(order_id="ORD-3"))

    assert engine.cache_stats["total_hits"] == 2


@pytest.mark.asyncio
async def test_cache_stats_returns_correct_counts(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """cache_stats reports correct entries and total_hits."""
    mock_llm.set_responses([BENIGN_TREE_JSON, BENIGN_TREE_JSON])
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config)

    # Two different tools → two cache entries
    await engine.analyze(_candidate(tool_name="tool_a"))
    await engine.analyze(_candidate(tool_name="tool_b"))

    # Hit tool_a once more
    await engine.analyze(
        CandidateAction(
            tool_name="tool_a",
            parameters={"order_id": "ORD-X"},
            reasoning="test",
            expected_outcome="test",
        )
    )

    stats = engine.cache_stats
    assert stats["entries"] == 2
    assert stats["total_hits"] == 1
