import pytest

from sophia.hats.registry import HatRegistry
from sophia.tools.registry import ToolRegistry
from tests.conftest import HATS_DIR


def test_hat_registry_discovers_hats():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    available = registry.list_available()
    assert len(available) >= 1
    assert any(m.name == "customer-service" for m in available)


async def test_equip_hat():
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    hat = await registry.equip("customer-service")

    assert hat.name == "customer-service"
    assert registry.get_active() is not None
    assert registry.get_active().name == "customer-service"

    # Tools: 19 hat tools + 3 framework comm tools + converse
    defs = tool_reg.get_definitions()
    assert len(defs) == 23


async def test_unequip_hat():
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    await registry.equip("customer-service")
    assert len(tool_reg.get_definitions()) == 23

    await registry.unequip()
    assert registry.get_active() is None
    assert len(tool_reg.get_definitions()) == 0


async def test_equip_unknown_hat():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    with pytest.raises(ValueError, match="not found"):
        await registry.equip("nonexistent-hat")


async def test_converse_in_tool_definitions():
    """After equipping a hat, 'converse' appears as a structured tool definition."""
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    await registry.equip("customer-service")
    defs = tool_reg.get_definitions()
    converse_defs = [d for d in defs if d["name"] == "converse"]
    assert len(converse_defs) == 1
    assert "conversational" in converse_defs[0]["description"].lower()


async def test_converse_persists_after_hat_switch():
    """Converse tool is re-registered when switching hats."""
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    # Equip, verify converse
    await registry.equip("customer-service")
    assert any(d["name"] == "converse" for d in tool_reg.get_definitions())

    # Unequip and re-equip (simulates hat switch)
    await registry.unequip()
    await registry.equip("customer-service")
    defs = tool_reg.get_definitions()
    assert any(d["name"] == "converse" for d in defs)
    assert len(defs) == 23


def test_get_active_or_raise_no_hat():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    with pytest.raises(RuntimeError, match="No hat"):
        registry.get_active_or_raise()
