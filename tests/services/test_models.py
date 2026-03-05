from dataclasses import asdict
from datetime import datetime

from sophia.services.models import (
    Address,
    AddressUpdateResult,
    CancellationResult,
    CouponParams,
    CouponResult,
    Customer,
    CustomerHistory,
    DiscountResult,
    FreeShippingResult,
    Order,
    OrderChanges,
    OrderItem,
    OrderStatus,
    ProductDetails,
    ProductStock,
    RefundResult,
    ReturnInitiationResult,
    ReturnItem,
    ReturnLabel,
    ReturnStatus,
    ShipmentTracking,
    ShippingOption,
    TrackingEvent,
    WarrantyStatus,
)


NOW = datetime(2025, 3, 1, 12, 0, 0)


def test_order_item():
    item = OrderItem("PROD-001", "Widget", 2, 10.0, 20.0)
    d = asdict(item)
    assert d["product_id"] == "PROD-001"
    assert d["total_price"] == 20.0


def test_order():
    item = OrderItem("PROD-001", "Widget", 1, 10.0, 10.0)
    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        status="pending",
        items=[item],
        total=10.0,
        currency="USD",
        created_at=NOW,
        updated_at=NOW,
    )
    d = asdict(order)
    assert d["order_id"] == "ORD-001"
    assert d["metadata"] == {}
    assert d["shipping_address"] is None
    assert len(d["items"]) == 1


def test_order_status():
    status = OrderStatus("ORD-001", "shipped", NOW, estimated_delivery=NOW)
    d = asdict(status)
    assert d["status"] == "shipped"
    assert d["tracking_number"] is None


def test_customer():
    c = Customer("CUST-001", "test@example.com", "Jane Smith")
    d = asdict(c)
    assert d["tags"] == []
    assert d["total_orders"] == 0


def test_address():
    addr = Address("123 Main St", "Springfield", "IL", "62701")
    d = asdict(addr)
    assert d["country"] == "US"
    assert d["line2"] is None


def test_shipment_tracking():
    event = TrackingEvent(NOW, "Chicago, IL", "In transit", "in_transit")
    tracking = ShipmentTracking("ORD-001", "UPS", "1Z999", "in_transit", NOW, events=[event])
    d = asdict(tracking)
    assert len(d["events"]) == 1
    assert d["carrier"] == "UPS"


def test_product_stock():
    stock = ProductStock("PROD-001", "Widget", 100, 9.99)
    d = asdict(stock)
    assert d["in_stock"] is True


def test_product_details():
    pd = ProductDetails("PROD-001", "Widget", "A nice widget", 9.99, "electronics")
    d = asdict(pd)
    assert d["warranty_months"] == 12
    assert d["specs"] == {}


def test_warranty_status():
    ws = WarrantyStatus("ORD-001", "PROD-001", NOW, NOW, True, "standard")
    d = asdict(ws)
    assert d["is_active"] is True


def test_refund_result():
    r = RefundResult("REF-001", "ORD-001", 50.0, "processed", "original_payment")
    d = asdict(r)
    assert d["amount"] == 50.0


def test_discount_result():
    dr = DiscountResult("DISC-001", 15, NOW, "CUST-001")
    d = asdict(dr)
    assert d["percent"] == 15


def test_coupon_params_and_result():
    params = CouponParams("percent", 10.0)
    d = asdict(params)
    assert d["single_use"] is True
    assert d["expiry_days"] == 30

    result = CouponResult("COUP-001", "percent", 10.0, NOW, "CUST-001")
    d = asdict(result)
    assert d["coupon_code"] == "COUP-001"


def test_return_item():
    ri = ReturnItem("PROD-001", 1, "defective")
    d = asdict(ri)
    assert d["reason"] == "defective"


def test_return_initiation_result():
    rir = ReturnInitiationResult("RET-001", "ORD-001", None, "initiated", "Ship it back")
    d = asdict(rir)
    assert d["return_label_url"] is None


def test_return_status():
    rs = ReturnStatus(
        "RET-001",
        "ORD-001",
        "initiated",
        [ReturnItem("PROD-001", 1, "defective")],
        NOW,
    )
    d = asdict(rs)
    assert d["refund_amount"] is None
    assert len(d["items"]) == 1


def test_customer_history():
    customer = Customer("CUST-001", "test@example.com", "Jane")
    ch = CustomerHistory(customer, orders=[], returns=[])
    d = asdict(ch)
    assert d["total_refunded"] == 0.0
    assert d["total_discounts_given"] == 0


def test_return_label():
    rl = ReturnLabel("https://example.com/label", "UPS", "1Z999", NOW)
    d = asdict(rl)
    assert d["carrier"] == "UPS"


def test_cancellation_result():
    cr = CancellationResult("ORD-001", True, refund_amount=50.0)
    d = asdict(cr)
    assert d["success"] is True


def test_order_changes():
    oc = OrderChanges(items_to_remove=["PROD-001"])
    d = asdict(oc)
    assert d["shipping_address"] is None
    assert d["items_to_remove"] == ["PROD-001"]


def test_address_update_result():
    aur = AddressUpdateResult("ORD-001", True, Address("456 Oak", "Chicago", "IL", "60601"))
    d = asdict(aur)
    assert d["success"] is True


def test_shipping_option():
    so = ShippingOption("UPS", "Ground", 5, 9.99)
    d = asdict(so)
    assert d["estimated_days"] == 5


def test_free_shipping_result():
    fsr = FreeShippingResult(True, "CUST-001", 9.99)
    d = asdict(fsr)
    assert d["applied"] is True
