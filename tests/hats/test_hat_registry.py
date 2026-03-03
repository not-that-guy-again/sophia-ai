import pytest

from sophia.hats.registry import HatRegistry
from sophia.tools.registry import ToolRegistry
from tests.conftest import HATS_DIR


def test_hat_registry_discovers_hats():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    available = registry.list_available()
    assert len(available) >= 1
    assert any(m.name == "customer-service" for m in available)


def test_equip_hat():
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    hat = registry.equip("customer-service")

    assert hat.name == "customer-service"
    assert registry.get_active() is not None
    assert registry.get_active().name == "customer-service"

    # Tools should be registered
    defs = tool_reg.get_definitions()
    assert len(defs) == 10


def test_unequip_hat():
    tool_reg = ToolRegistry()
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=tool_reg)

    registry.equip("customer-service")
    assert len(tool_reg.get_definitions()) == 10

    registry.unequip()
    assert registry.get_active() is None
    assert len(tool_reg.get_definitions()) == 0


def test_equip_unknown_hat():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    with pytest.raises(ValueError, match="not found"):
        registry.equip("nonexistent-hat")


def test_get_active_or_raise_no_hat():
    registry = HatRegistry(hats_dir=HATS_DIR, tool_registry=ToolRegistry())
    with pytest.raises(RuntimeError, match="No hat"):
        registry.get_active_or_raise()
