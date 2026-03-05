"""Risk floor check for the propose-then-evaluate pipeline (ADR-031).

Runs after the parameter gate and before the consequence engine.
Returns the highest risk_floor declared across all candidates, or None
if no candidate's tool declares a floor.
"""

from __future__ import annotations

from sophia.core.proposer import CandidateAction
from sophia.tools.registry import ToolRegistry

TIER_ORDER = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}


def get_proposal_floor(
    candidates: list[CandidateAction],
    tool_registry: ToolRegistry,
) -> str | None:
    """Return the highest risk_floor among all candidates' tools, or None.

    Candidates whose tool is not found in the registry (e.g., 'converse',
    'escalate_to_human') are skipped — synthetic candidates have no floor.
    """
    highest: str | None = None

    for candidate in candidates:
        tool = tool_registry.get(candidate.tool_name)
        if tool is None:
            continue  # converse, escalate_to_human, synthesized candidates

        floor = getattr(tool, "risk_floor", None)
        if floor is None:
            continue

        if highest is None or TIER_ORDER[floor] > TIER_ORDER[highest]:
            highest = floor

    return highest
