"""Tests for framework communication tool registration in HatRegistry."""

from sophia.hats.registry import HatRegistry
from sophia.tools.registry import ToolRegistry
from tests.conftest import HATS_DIR


async def test_framework_communication_tools_registered():
    """Framework communication tools are registered when named in hat's tools list."""
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    await registry.equip("customer-service")
    defs = tool_reg.get_definitions()
    tool_names = {d["name"] for d in defs}

    assert "escalate_to_human" in tool_names
    assert "notify_manager" in tool_names
    assert "request_approval" in tool_names


async def test_framework_tools_not_registered_when_absent():
    """Framework communication tools are NOT registered when absent from tools list."""
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    await registry.equip("customer-service")
    defs = tool_reg.get_definitions()
    tool_names = {d["name"] for d in defs}

    # "notify_team" is not in customer-service tools list, so should not appear
    assert "notify_team" not in tool_names


async def test_framework_tools_cleared_on_unequip():
    """After unequip(), framework communication tools are cleared."""
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    await registry.equip("customer-service")
    assert len(tool_reg.get_definitions()) > 0

    await registry.unequip()
    assert len(tool_reg.get_definitions()) == 0
