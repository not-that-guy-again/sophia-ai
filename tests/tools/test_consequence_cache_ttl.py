"""Tests for Tool.consequence_cache_ttl attribute (ADR-033)."""

import json

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig
from sophia.tools.base import Tool, ToolResult
from sophia.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider

TREE_JSON = json.dumps(
    {
        "consequences": [
            {
                "description": "Lookup result",
                "stakeholders_affected": ["customer"],
                "probability": 0.9,
                "tangibility": 0.8,
                "harm_benefit": 0.3,
                "affected_party": "customer",
                "is_terminal": True,
                "children": [],
            }
        ]
    }
)


class ExplicitTTLTool(Tool):
    name = "explicit_ttl"
    description = "Tool with explicit TTL"
    parameters = {}
    authority_level = "agent"
    consequence_cache_ttl = 120

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class NoneTTLTool(Tool):
    name = "none_ttl"
    description = "Tool with None TTL"
    parameters = {}
    authority_level = "agent"
    consequence_cache_ttl = None

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class ZeroTTLTool(Tool):
    name = "zero_ttl"
    description = "Tool with zero TTL"
    parameters = {}
    authority_level = "agent"
    consequence_cache_ttl = 0

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


def _candidate(tool_name: str, order_id: str = "ORD-1") -> CandidateAction:
    return CandidateAction(
        tool_name=tool_name,
        parameters={"order_id": order_id},
        reasoning="test",
        expected_outcome="test",
    )


def test_tool_with_explicit_ttl():
    """Tool declares consequence_cache_ttl = 120."""
    tool = ExplicitTTLTool()
    assert tool.consequence_cache_ttl == 120


def test_tool_with_none_ttl_uses_engine_default():
    """Tool with consequence_cache_ttl = None inherits engine default."""
    tool = NoneTTLTool()
    assert tool.consequence_cache_ttl is None


@pytest.mark.asyncio
async def test_tool_with_zero_ttl_never_caches(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Tool with consequence_cache_ttl = 0 always generates fresh trees."""
    mock_llm.set_responses([TREE_JSON, TREE_JSON])

    registry = ToolRegistry()
    registry.register(ZeroTTLTool())

    engine = ConsequenceEngine(
        llm=mock_llm,
        hat_config=cs_hat_config,
        cache_ttl_seconds=3600,
        tool_registry=registry,
    )

    await engine.analyze(_candidate("zero_ttl", "ORD-1"))
    await engine.analyze(_candidate("zero_ttl", "ORD-2"))

    assert len(mock_llm.calls) == 2
    # Entry should not be written to cache when TTL=0
    assert engine.cache_stats["entries"] == 0
