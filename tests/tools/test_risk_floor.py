"""Unit tests for Tool.risk_floor validation and serialization."""

import pytest

from sophia.tools.base import Tool, ToolResult


class ValidRedTool(Tool):
    name = "valid_red"
    description = "A tool with risk_floor RED"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"
    risk_floor = "RED"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class ValidNoneTool(Tool):
    name = "valid_none"
    description = "A tool with risk_floor None"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"
    risk_floor = None

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


class ImplicitNoneTool(Tool):
    name = "implicit_none"
    description = "A tool without explicit risk_floor (inherits None)"
    parameters = {"type": "object", "properties": {}}
    authority_level = "agent"

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


def test_tool_with_valid_risk_floor_accepted():
    """Tool with risk_floor = 'RED' instantiates without error."""
    tool = ValidRedTool()
    assert tool.risk_floor == "RED"


def test_tool_with_invalid_risk_floor_raises():
    """Tool with risk_floor = 'CRIMSON' raises ValueError at class definition time."""
    with pytest.raises(ValueError, match="invalid risk_floor"):

        class BadTool(Tool):
            name = "bad_tool"
            description = "Invalid floor"
            parameters = {"type": "object", "properties": {}}
            authority_level = "agent"
            risk_floor = "CRIMSON"

            async def execute(self, params: dict) -> ToolResult:
                return ToolResult(success=True, data=None, message="ok")


def test_tool_with_none_risk_floor_accepted():
    """risk_floor = None is valid."""
    tool = ValidNoneTool()
    assert tool.risk_floor is None


def test_tool_with_implicit_none_risk_floor_accepted():
    """A tool without explicit risk_floor inherits None from the ABC."""
    tool = ImplicitNoneTool()
    assert tool.risk_floor is None


def test_to_definition_includes_risk_floor():
    """to_definition() output includes 'risk_floor' key."""
    tool = ValidRedTool()
    defn = tool.to_definition()
    assert "risk_floor" in defn
    assert defn["risk_floor"] == "RED"


def test_to_definition_includes_none_risk_floor():
    """to_definition() includes risk_floor=None for tools without a floor."""
    tool = ValidNoneTool()
    defn = tool.to_definition()
    assert "risk_floor" in defn
    assert defn["risk_floor"] is None
