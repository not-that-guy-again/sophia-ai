"""Tests for mock backend service implementations."""

import pytest

from sophia.services.mock import (
    MockCompensationService,
    MockCustomerService,
    MockDataStore,
    MockInventoryService,
    MockOrderService,
    MockShippingService,
)
from sophia.services.models import Address, OrderItem, ReturnItem


# --- Data consistency ---


def test_order_customer_ids_match_real_customers():
    for order in MockDataStore.orders.values():
        assert order.customer_id in MockDataStore.customers, (
            f"Order {order.order_id} references unknown customer {order.customer_id}"
        )


def test_shipment_order_ids_match_real_orders():
    for order_id in MockDataStore.shipments:
        assert order_id in MockDataStore.orders, (
            f"Shipment for unknown order {order_id}"
        )


def test_return_order_ids_match_real_orders():
    for ret in MockDataStore.returns.values():
        assert ret.order_id in MockDataStore.orders


# --- OrderService ---


async def test_get_order_found():
    svc = MockOrderService()
    order = await svc.get_order("ORD-12345")
    assert order is not None
    assert order.customer_id == "CUST-001"
    assert order.status == "delivered"


async def test_get_order_not_found():
    svc = MockOrderService()
    assert await svc.get_order("ORD-NOPE") is None


async def test_get_order_status():
    svc = MockOrderService()
    status = await svc.get_order_status("ORD-12345")
    assert status is not None
    assert status.status == "delivered"
    assert status.tracking_number is not None


async def test_get_order_status_not_found():
    svc = MockOrderService()
    assert await svc.get_order_status("ORD-NOPE") is None


async def test_search_orders_by_customer():
    svc = MockOrderService()
    orders = await svc.search_orders_by_customer("CUST-001")
    assert len(orders) >= 2
    assert all(o.customer_id == "CUST-001" for o in orders)


async def test_cancel_order_success():
    svc = MockOrderService()
    # ORD-44444 is "confirmed"
    result = await svc.cancel_order("ORD-44444", "changed mind")
    assert result.success is True
    assert result.refund_amount == 129.99
    # Restore state for other tests
    MockDataStore.orders["ORD-44444"].status = "confirmed"


async def test_cancel_order_already_shipped():
    svc = MockOrderService()
    result = await svc.cancel_order("ORD-11111", "changed mind")
    assert result.success is False
    assert "shipped" in result.reason


async def test_cancel_order_not_found():
    svc = MockOrderService()
    result = await svc.cancel_order("ORD-NOPE", "test")
    assert result.success is False


async def test_place_order():
    svc = MockOrderService()
    items = [OrderItem("PROD-001", "Headphones", 1, 79.99, 79.99)]
    order = await svc.place_order("CUST-001", items)
    assert order.order_id.startswith("ORD-")
    assert order.status == "pending"
    assert order.total == 79.99
    # Clean up
    del MockDataStore.orders[order.order_id]


# --- CustomerService ---


async def test_get_customer():
    svc = MockCustomerService()
    customer = await svc.get_customer("CUST-001")
    assert customer is not None
    assert customer.name == "Jane Smith"


async def test_get_customer_not_found():
    svc = MockCustomerService()
    assert await svc.get_customer("CUST-NOPE") is None


async def test_search_customers_by_name():
    svc = MockCustomerService()
    results = await svc.search_customers("jane")
    assert len(results) == 1
    assert results[0].customer_id == "CUST-001"


async def test_search_customers_by_email():
    svc = MockCustomerService()
    results = await svc.search_customers("john.doe")
    assert len(results) == 1


async def test_search_customers_no_match():
    svc = MockCustomerService()
    results = await svc.search_customers("zzzznotexist")
    assert len(results) == 0


async def test_get_customer_history():
    svc = MockCustomerService()
    history = await svc.get_customer_history("CUST-001")
    assert history.customer.customer_id == "CUST-001"
    assert len(history.orders) >= 2


async def test_get_customer_history_not_found():
    svc = MockCustomerService()
    with pytest.raises(ValueError, match="not found"):
        await svc.get_customer_history("CUST-NOPE")


# --- ShippingService ---


async def test_track_shipment():
    svc = MockShippingService()
    tracking = await svc.track_shipment("ORD-12345")
    assert tracking is not None
    assert tracking.carrier == "UPS"
    assert len(tracking.events) >= 1


async def test_track_shipment_not_found():
    svc = MockShippingService()
    assert await svc.track_shipment("ORD-NOPE") is None


async def test_get_shipping_options():
    svc = MockShippingService()
    options = await svc.get_shipping_options("ORD-12345")
    assert len(options) == 3


async def test_update_shipping_address_success():
    svc = MockShippingService()
    addr = Address("999 New St", "Boston", "MA", "02101")
    result = await svc.update_shipping_address("ORD-67890", addr)
    assert result.success is True
    # Restore
    MockDataStore.orders["ORD-67890"].shipping_address = None


async def test_update_shipping_address_shipped():
    svc = MockShippingService()
    addr = Address("999 New St", "Boston", "MA", "02101")
    result = await svc.update_shipping_address("ORD-11111", addr)
    assert result.success is False


# --- InventoryService ---


async def test_check_stock_all():
    svc = MockInventoryService()
    stock = await svc.check_stock()
    assert len(stock) == 5


async def test_check_stock_single():
    svc = MockInventoryService()
    stock = await svc.check_stock("PROD-001")
    assert len(stock) == 1
    assert stock[0].name == "Wireless Headphones"


async def test_check_stock_not_found():
    svc = MockInventoryService()
    stock = await svc.check_stock("PROD-NOPE")
    assert len(stock) == 0


async def test_get_product_details():
    svc = MockInventoryService()
    details = await svc.get_product_details("PROD-001")
    assert details is not None
    assert details.category == "Audio"


async def test_check_warranty_status():
    svc = MockInventoryService()
    ws = await svc.check_warranty_status("ORD-12345", "PROD-001")
    assert ws.coverage_type == "standard"


async def test_check_warranty_product_not_in_order():
    svc = MockInventoryService()
    with pytest.raises(ValueError, match="not found in order"):
        await svc.check_warranty_status("ORD-12345", "PROD-003")


# --- CompensationService ---


async def test_apply_discount():
    svc = MockCompensationService()
    result = await svc.apply_discount("CUST-001", 15, "loyalty")
    assert result.percent == 15
    assert result.discount_code.startswith("DISC-")


async def test_apply_discount_unknown_customer():
    svc = MockCompensationService()
    with pytest.raises(ValueError, match="not found"):
        await svc.apply_discount("CUST-NOPE", 10, "test")


async def test_process_partial_refund():
    svc = MockCompensationService()
    result = await svc.process_partial_refund("ORD-12345", 30.0, "damaged")
    assert result.amount == 30.0
    assert result.status == "processed"


async def test_process_full_refund():
    svc = MockCompensationService()
    result = await svc.process_full_refund("ORD-12345", "wrong item")
    assert result.amount == 105.97


async def test_apply_free_shipping():
    svc = MockCompensationService()
    result = await svc.apply_free_shipping("CUST-001", None, "apology")
    assert result.applied is True


async def test_initiate_return_success():
    svc = MockCompensationService()
    items = [ReturnItem("PROD-001", 1, "defective")]
    result = await svc.initiate_return("ORD-12345", items, "defective product")
    assert result.status == "initiated"
    assert result.return_label_url is not None  # free for defective
    # Clean up
    del MockDataStore.returns[result.return_id]


async def test_initiate_return_not_delivered():
    svc = MockCompensationService()
    items = [ReturnItem("PROD-003", 1, "changed_mind")]
    with pytest.raises(ValueError, match="processing"):
        await svc.initiate_return("ORD-67890", items, "changed mind")


async def test_check_return_status():
    svc = MockCompensationService()
    ret = await svc.check_return_status("RET-001")
    assert ret is not None
    assert ret.status == "processed"


async def test_check_return_status_not_found():
    svc = MockCompensationService()
    assert await svc.check_return_status("RET-NOPE") is None
