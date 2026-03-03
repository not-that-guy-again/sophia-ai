import pytest

from sophia.hats.registry import HatRegistry
from sophia.tools.registry import ToolRegistry
from tests.conftest import HATS_DIR


@pytest.mark.asyncio
async def test_only_hat_tools_available():
    """When a hat is equipped, only its tools should be registered."""
    tool_reg = ToolRegistry()
    hat_reg = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    hat_reg.equip("customer-service")

    # All CS tools available
    names = {d["name"] for d in tool_reg.get_definitions()}
    assert "look_up_order" in names
    assert "offer_full_refund" in names

    # Execute a registered tool
    result = await tool_reg.execute("look_up_order", {"order_id": "ORD-12345"})
    assert result.success

    # Unregistered tool should fail
    result = await tool_reg.execute("some_other_tool", {})
    assert not result.success


@pytest.mark.asyncio
async def test_tools_cleared_on_unequip():
    """Unequipping a hat should remove all its tools."""
    tool_reg = ToolRegistry()
    hat_reg = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    hat_reg.equip("customer-service")
    assert len(tool_reg.get_definitions()) == 10

    hat_reg.unequip()
    assert len(tool_reg.get_definitions()) == 0

    # Previously registered tool should now fail
    result = await tool_reg.execute("look_up_order", {"order_id": "ORD-12345"})
    assert not result.success
