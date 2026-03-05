"""Unit tests for sophia.core.risk_floor — get_proposal_floor()."""

from sophia.core.proposer import CandidateAction
from sophia.core.risk_floor import get_proposal_floor
from sophia.tools.base import Tool, ToolResult
from sophia.tools.registry import ToolRegistry


# --- Minimal tool fixtures ---


class GreenTool(Tool):
    name = "green_tool"
    description = "A tool with no floor"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"
    risk_floor = None

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class YellowTool(Tool):
    name = "yellow_tool"
    description = "A tool with YELLOW floor"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"
    risk_floor = "YELLOW"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class RedTool(Tool):
    name = "red_tool"
    description = "A tool with RED floor"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"
    risk_floor = "RED"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


def _candidate(tool_name: str) -> CandidateAction:
    return CandidateAction(
        tool_name=tool_name,
        parameters={},
        reasoning="test",
        expected_outcome="test",
    )


def _registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


# --- Tests ---


def test_get_proposal_floor_returns_none_when_no_floors_set():
    """All candidates have risk_floor=None → returns None."""
    reg = _registry(GreenTool())
    candidates = [_candidate("green_tool")]
    assert get_proposal_floor(candidates, reg) is None


def test_get_proposal_floor_returns_highest_floor_across_candidates():
    """When candidates have YELLOW and RED floors, RED is returned."""
    reg = _registry(YellowTool(), RedTool())
    candidates = [_candidate("yellow_tool"), _candidate("red_tool")]
    assert get_proposal_floor(candidates, reg) == "RED"


def test_get_proposal_floor_skips_converse_candidate():
    """'converse' is not in the registry and should be skipped."""
    reg = _registry(GreenTool())
    candidates = [_candidate("converse"), _candidate("green_tool")]
    assert get_proposal_floor(candidates, reg) is None


def test_get_proposal_floor_skips_unknown_tools():
    """Unknown tools (not in registry) are skipped without error."""
    reg = _registry(GreenTool())
    candidates = [_candidate("nonexistent_tool"), _candidate("green_tool")]
    assert get_proposal_floor(candidates, reg) is None


def test_get_proposal_floor_red_dominates_yellow():
    """RED floor dominates even if YELLOW appears first."""
    reg = _registry(YellowTool(), RedTool())
    candidates = [_candidate("yellow_tool"), _candidate("red_tool")]
    assert get_proposal_floor(candidates, reg) == "RED"

    # Reverse order — still RED
    candidates_reversed = [_candidate("red_tool"), _candidate("yellow_tool")]
    assert get_proposal_floor(candidates_reversed, reg) == "RED"


def test_get_proposal_floor_single_yellow():
    """Single YELLOW-floored candidate returns YELLOW."""
    reg = _registry(YellowTool())
    candidates = [_candidate("yellow_tool")]
    assert get_proposal_floor(candidates, reg) == "YELLOW"


def test_get_proposal_floor_empty_candidates():
    """Empty candidate list returns None."""
    reg = _registry(GreenTool())
    assert get_proposal_floor([], reg) is None
