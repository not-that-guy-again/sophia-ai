"""Tests for the 9 new tools (8 new + cancel_order)."""

import importlib.util
import sys
from pathlib import Path

import pytest

from sophia.services.mock import MockDataStore
from sophia.services.registry import ServiceRegistry

TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "hats" / "customer-service" / "tools"


def _load_module(filename: str):
    """Load a tool module from the hat's tools directory."""
    module_name = f"_test_cs_{filename}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    filepath = TOOLS_DIR / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def service_registry():
    reg = ServiceRegistry()
    await reg.initialize({})
    yield reg
    await reg.teardown()


def _make_tool(cls, services):
    tool = cls()
    tool.inject_services(services)
    return tool


# --- LookUpCustomerTool ---


async def test_look_up_customer_by_email(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.LookUpCustomerTool, service_registry)
    result = await tool.execute({"email": "jane.smith@example.com"})
    assert result.success
    assert len(result.data["customers"]) == 1
    assert result.data["customers"][0]["name"] == "Jane Smith"


async def test_look_up_customer_by_name(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.LookUpCustomerTool, service_registry)
    result = await tool.execute({"name": "john"})
    assert result.success
    assert any(c["name"] == "John Doe" for c in result.data["customers"])


async def test_look_up_customer_no_params(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.LookUpCustomerTool, service_registry)
    result = await tool.execute({})
    assert not result.success
    assert "At least one" in result.message


async def test_look_up_customer_not_found(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.LookUpCustomerTool, service_registry)
    result = await tool.execute({"email": "nobody@nowhere.com"})
    assert not result.success


# --- GetCustomerOrderHistoryTool ---


async def test_get_customer_order_history(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.GetCustomerOrderHistoryTool, service_registry)
    result = await tool.execute({"customer_id": "CUST-001"})
    assert result.success
    assert len(result.data["orders"]) >= 2


async def test_get_customer_order_history_not_found(service_registry):
    mod = _load_module("customers")
    tool = _make_tool(mod.GetCustomerOrderHistoryTool, service_registry)
    result = await tool.execute({"customer_id": "CUST-NOPE"})
    assert not result.success


# --- TrackShipmentTool ---


async def test_track_shipment(service_registry):
    mod = _load_module("shipping")
    tool = _make_tool(mod.TrackShipmentTool, service_registry)
    result = await tool.execute({"order_id": "ORD-12345"})
    assert result.success
    assert result.data["carrier"] == "UPS"
    assert len(result.data["events"]) >= 1


async def test_track_shipment_not_found(service_registry):
    mod = _load_module("shipping")
    tool = _make_tool(mod.TrackShipmentTool, service_registry)
    result = await tool.execute({"order_id": "ORD-NOPE"})
    assert not result.success


# --- UpdateShippingAddressTool ---


async def test_update_shipping_address_success(service_registry):
    mod = _load_module("shipping")
    tool = _make_tool(mod.UpdateShippingAddressTool, service_registry)
    result = await tool.execute({
        "order_id": "ORD-67890",
        "line1": "999 New St",
        "city": "Boston",
        "state": "MA",
        "postal_code": "02101",
    })
    assert result.success
    # Restore
    MockDataStore.orders["ORD-67890"].shipping_address = None


async def test_update_shipping_address_shipped(service_registry):
    mod = _load_module("shipping")
    tool = _make_tool(mod.UpdateShippingAddressTool, service_registry)
    result = await tool.execute({
        "order_id": "ORD-11111",
        "line1": "999 New St",
        "city": "Boston",
        "state": "MA",
        "postal_code": "02101",
    })
    assert not result.success


# --- LookUpProductTool ---


async def test_look_up_product(service_registry):
    mod = _load_module("products")
    tool = _make_tool(mod.LookUpProductTool, service_registry)
    result = await tool.execute({"product_id": "PROD-001"})
    assert result.success
    assert result.data["name"] == "Wireless Headphones"
    assert result.data["category"] == "Audio"


async def test_look_up_product_not_found(service_registry):
    mod = _load_module("products")
    tool = _make_tool(mod.LookUpProductTool, service_registry)
    result = await tool.execute({"product_id": "PROD-NOPE"})
    assert not result.success


# --- CheckWarrantyStatusTool ---


async def test_check_warranty_status(service_registry):
    mod = _load_module("products")
    tool = _make_tool(mod.CheckWarrantyStatusTool, service_registry)
    result = await tool.execute({"order_id": "ORD-12345", "product_id": "PROD-001"})
    assert result.success
    assert result.data["coverage_type"] == "standard"


async def test_check_warranty_product_not_in_order(service_registry):
    mod = _load_module("products")
    tool = _make_tool(mod.CheckWarrantyStatusTool, service_registry)
    result = await tool.execute({"order_id": "ORD-12345", "product_id": "PROD-003"})
    assert not result.success
    assert "not found in order" in result.message


# --- InitiateReturnTool ---


async def test_initiate_return_success(service_registry):
    mod = _load_module("returns")
    tool = _make_tool(mod.InitiateReturnTool, service_registry)
    result = await tool.execute({
        "order_id": "ORD-12345",
        "items": [{"product_id": "PROD-001", "quantity": 1, "reason": "defective"}],
        "reason": "Product is defective",
    })
    assert result.success
    assert result.data["return_label_url"] is not None  # free for defective
    # Clean up
    del MockDataStore.returns[result.data["return_id"]]


async def test_initiate_return_not_delivered(service_registry):
    mod = _load_module("returns")
    tool = _make_tool(mod.InitiateReturnTool, service_registry)
    result = await tool.execute({
        "order_id": "ORD-67890",
        "items": [{"product_id": "PROD-003", "quantity": 1, "reason": "changed_mind"}],
        "reason": "Changed my mind",
    })
    assert not result.success
    assert "processing" in result.message


# --- CheckReturnStatusTool ---


async def test_check_return_status(service_registry):
    mod = _load_module("returns")
    tool = _make_tool(mod.CheckReturnStatusTool, service_registry)
    result = await tool.execute({"return_id": "RET-001"})
    assert result.success
    assert result.data["status"] == "processed"


async def test_check_return_status_not_found(service_registry):
    mod = _load_module("returns")
    tool = _make_tool(mod.CheckReturnStatusTool, service_registry)
    result = await tool.execute({"return_id": "RET-NOPE"})
    assert not result.success


# --- CancelOrderTool ---


async def test_cancel_order_success(service_registry):
    mod = _load_module("orders")
    tool = _make_tool(mod.CancelOrderTool, service_registry)
    result = await tool.execute({"order_id": "ORD-44444", "reason": "changed mind"})
    assert result.success
    assert result.data["refund_amount"] == 129.99
    # Restore
    MockDataStore.orders["ORD-44444"].status = "confirmed"


async def test_cancel_order_already_shipped(service_registry):
    mod = _load_module("orders")
    tool = _make_tool(mod.CancelOrderTool, service_registry)
    result = await tool.execute({"order_id": "ORD-11111", "reason": "changed mind"})
    assert not result.success
    assert "shipped" in result.message


async def test_cancel_order_not_found(service_registry):
    mod = _load_module("orders")
    tool = _make_tool(mod.CancelOrderTool, service_registry)
    result = await tool.execute({"order_id": "ORD-NOPE", "reason": "test"})
    assert not result.success
