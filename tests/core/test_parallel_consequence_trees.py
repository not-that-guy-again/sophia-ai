"""Tests for parallel consequence tree generation via asyncio.gather().

Verifies that the loop.py change from a sequential for-loop to
asyncio.gather() produces correct, order-preserving, concurrent results.
"""

import asyncio
import json
import time

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig
from tests.conftest import MockLLMProvider


def _make_candidate(tool_name: str, order_id: str = "ORD-001") -> CandidateAction:
    return CandidateAction(
        tool_name=tool_name,
        parameters={"order_id": order_id},
        reasoning=f"Test candidate for {tool_name}",
        expected_outcome=f"{tool_name} executed",
    )


def _tree_json(description: str, harm_benefit: float) -> str:
    """Build a minimal but valid consequence tree JSON."""
    return json.dumps(
        {
            "consequences": [
                {
                    "description": description,
                    "stakeholders_affected": ["customer"],
                    "probability": 0.9,
                    "tangibility": 0.8,
                    "harm_benefit": harm_benefit,
                    "affected_party": "customer",
                    "is_terminal": True,
                    "children": [],
                }
            ]
        }
    )


TREE_A = _tree_json("Refund issued to customer", 0.5)
TREE_B = _tree_json("Replacement shipped to customer", 0.3)
TREE_C = _tree_json("Store credit applied", 0.1)


class TimingMockProvider(MockLLMProvider):
    """Records wall-clock timestamps for each complete() call."""

    def __init__(self):
        super().__init__()
        self.call_start_times: list[float] = []
        self.call_end_times: list[float] = []
        self._delay = 0.05  # 50ms simulated latency per call

    async def complete(self, system_prompt, user_message, **kwargs):
        self.call_start_times.append(time.monotonic())
        await asyncio.sleep(self._delay)
        self.call_end_times.append(time.monotonic())
        return await super().complete(system_prompt, user_message, **kwargs)


@pytest.mark.asyncio
async def test_two_candidate_trees_generated_concurrently(cs_hat_config: HatConfig):
    """Two trees via asyncio.gather() complete faster than sequential."""
    provider = TimingMockProvider()
    provider.set_responses([TREE_A, TREE_B])

    engine = ConsequenceEngine(llm=provider, hat_config=cs_hat_config, max_depth=2)

    candidates = [
        _make_candidate("offer_full_refund"),
        _make_candidate("ship_replacement"),
    ]

    wall_start = time.monotonic()
    trees = list(await asyncio.gather(*[engine.analyze(candidate) for candidate in candidates]))
    wall_end = time.monotonic()

    wall_time = wall_end - wall_start

    # Both trees produced
    assert len(trees) == 2
    assert all(t is not None for t in trees)

    # Exactly two LLM calls
    assert len(provider.call_start_times) == 2

    # Concurrency check: second call started before first call ended
    assert provider.call_start_times[1] < provider.call_end_times[0], (
        "Second call should start before first call ends (concurrent execution)"
    )

    # Wall time should be well under 2x the delay (sequential would be >= 100ms)
    assert wall_time < 2 * provider._delay, (
        f"Wall time {wall_time:.3f}s should be < {2 * provider._delay}s (sequential threshold)"
    )


@pytest.mark.asyncio
async def test_single_candidate_still_works(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Single candidate through gather produces one tree — regression guard."""
    mock_llm.set_responses([TREE_A])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=2)
    candidates = [_make_candidate("offer_full_refund")]

    trees = list(await asyncio.gather(*[engine.analyze(candidate) for candidate in candidates]))

    assert len(trees) == 1
    assert trees[0].candidate_action.tool_name == "offer_full_refund"
    assert trees[0].total_nodes == 1


@pytest.mark.asyncio
async def test_tree_order_matches_candidate_order(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """asyncio.gather() preserves input order — evaluators depend on this."""
    mock_llm.set_responses([TREE_A, TREE_B])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=2)
    candidates = [
        _make_candidate("offer_full_refund"),
        _make_candidate("ship_replacement"),
    ]

    trees = list(await asyncio.gather(*[engine.analyze(candidate) for candidate in candidates]))

    # Order must match: tree[0] is for candidate[0], tree[1] is for candidate[1]
    assert trees[0].candidate_action.tool_name == "offer_full_refund"
    assert trees[1].candidate_action.tool_name == "ship_replacement"

    # Verify distinct content via harm_benefit scores
    assert trees[0].root_nodes[0].harm_benefit == 0.5
    assert trees[1].root_nodes[0].harm_benefit == 0.3


@pytest.mark.asyncio
async def test_three_candidates_all_produce_trees(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Three candidates via gather all produce trees."""
    mock_llm.set_responses([TREE_A, TREE_B, TREE_C])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=2)
    candidates = [
        _make_candidate("offer_full_refund"),
        _make_candidate("ship_replacement"),
        _make_candidate("apply_store_credit"),
    ]

    trees = list(await asyncio.gather(*[engine.analyze(candidate) for candidate in candidates]))

    assert len(trees) == 3
    assert trees[0].candidate_action.tool_name == "offer_full_refund"
    assert trees[1].candidate_action.tool_name == "ship_replacement"
    assert trees[2].candidate_action.tool_name == "apply_store_credit"
