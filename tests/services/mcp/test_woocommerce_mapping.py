import json

from sophia.services.mcp.models import MCPToolResult
from sophia.services.mcp.woocommerce_mapping import (
    _extract_wc_tracking,
    _map_wc_status,
    _parse_wc_customer,
    _parse_wc_order,
    _parse_wc_order_status,
    _parse_wc_product,
    _parse_wc_refund,
    _parse_wc_stock,
)


def _wrap(data: dict) -> MCPToolResult:
    return MCPToolResult(content=[{"type": "text", "text": json.dumps(data)}])


class TestMapWcStatus:
    def test_known_statuses(self):
        assert _map_wc_status("pending") == "pending"
        assert _map_wc_status("processing") == "processing"
        assert _map_wc_status("on-hold") == "pending"
        assert _map_wc_status("completed") == "delivered"
        assert _map_wc_status("cancelled") == "cancelled"
        assert _map_wc_status("refunded") == "cancelled"
        assert _map_wc_status("failed") == "cancelled"
        assert _map_wc_status("checkout-draft") == "pending"

    def test_unknown_defaults_to_pending(self):
        assert _map_wc_status("something_new") == "pending"

    def test_none_defaults_to_pending(self):
        assert _map_wc_status(None) == "pending"


class TestExtractWcTracking:
    def test_found(self):
        meta = [
            {"key": "other", "value": "x"},
            {"key": "_tracking_number", "value": "TRACK123"},
        ]
        assert _extract_wc_tracking(meta) == "TRACK123"

    def test_not_found(self):
        meta = [{"key": "other", "value": "x"}]
        assert _extract_wc_tracking(meta) is None

    def test_empty_list(self):
        assert _extract_wc_tracking([]) is None

    def test_none(self):
        assert _extract_wc_tracking(None) is None


class TestParseWcOrder:
    def test_full_order(self):
        data = {
            "id": 1234,
            "status": "processing",
            "currency": "USD",
            "total": "59.97",
            "customer_id": 42,
            "line_items": [
                {
                    "product_id": 99,
                    "name": "Blue Widget",
                    "quantity": 3,
                    "price": "19.99",
                    "total": "59.97",
                }
            ],
            "shipping": {
                "address_1": "123 Main St",
                "address_2": "",
                "city": "Springfield",
                "state": "IL",
                "postcode": "62701",
                "country": "US",
            },
            "meta_data": [{"key": "_tracking_number", "value": "TRACK123"}],
            "date_created": "2025-01-15T10:00:00",
            "date_modified": "2025-01-16T12:00:00",
        }
        order = _parse_wc_order(_wrap(data))

        assert order.order_id == "1234"
        assert order.customer_id == "42"
        assert order.status == "processing"
        assert order.total == 59.97
        assert len(order.items) == 1
        assert order.items[0].name == "Blue Widget"
        assert order.items[0].quantity == 3
        assert order.items[0].unit_price == 19.99
        assert order.items[0].total_price == 59.97
        assert order.shipping_address is not None
        assert order.shipping_address.line1 == "123 Main St"
        assert order.shipping_address.city == "Springfield"
        assert order.tracking_number == "TRACK123"

    def test_minimal_order(self):
        data = {"id": 1, "customer_id": 1, "total": "0"}
        order = _parse_wc_order(_wrap(data))

        assert order.order_id == "1"
        assert order.status == "pending"
        assert order.items == []
        assert order.shipping_address is None
        assert order.tracking_number is None


class TestParseWcOrderStatus:
    def test_order_status(self):
        data = {
            "id": 1234,
            "status": "completed",
            "date_modified": "2025-01-16T12:00:00",
            "meta_data": [{"key": "_tracking_number", "value": "TRACK456"}],
        }
        status = _parse_wc_order_status(_wrap(data))

        assert status.order_id == "1234"
        assert status.status == "delivered"
        assert status.tracking_number == "TRACK456"


class TestParseWcCustomer:
    def test_full_customer(self):
        data = {
            "id": 42,
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "username": "alice_s",
            "date_created": "2024-06-01T00:00:00",
            "orders_count": 5,
            "total_spent": "250.00",
        }
        customer = _parse_wc_customer(_wrap(data))

        assert customer.customer_id == "42"
        assert customer.email == "alice@example.com"
        assert customer.name == "Alice Smith"
        assert customer.total_orders == 5
        assert customer.total_spent == 250.0

    def test_minimal_customer(self):
        data = {"id": 1, "email": "bob@test.com"}
        customer = _parse_wc_customer(_wrap(data))

        assert customer.customer_id == "1"
        assert customer.email == "bob@test.com"
        assert customer.name == ""


class TestParseWcProduct:
    def test_full_product(self):
        data = {
            "id": 99,
            "name": "Blue Widget",
            "description": "A high-quality widget",
            "price": "19.99",
            "stock_status": "instock",
            "stock_quantity": 42,
            "categories": [{"name": "Widgets"}],
        }
        product = _parse_wc_product(_wrap(data))

        assert product.product_id == "99"
        assert product.name == "Blue Widget"
        assert product.description == "A high-quality widget"
        assert product.price == 19.99
        assert product.category == "Widgets"


class TestParseWcStock:
    def test_stock_list(self):
        data = {
            "products": [
                {
                    "id": 99,
                    "name": "Blue Widget",
                    "price": "19.99",
                    "stock_status": "instock",
                    "stock_quantity": 42,
                },
                {
                    "id": 100,
                    "name": "Red Widget",
                    "price": "24.99",
                    "stock_status": "outofstock",
                    "stock_quantity": 0,
                },
            ]
        }
        stocks = _parse_wc_stock(_wrap(data))

        assert len(stocks) == 2
        assert stocks[0].product_id == "99"
        assert stocks[0].in_stock is True
        assert stocks[0].quantity_available == 42
        assert stocks[1].in_stock is False
        assert stocks[1].quantity_available == 0


class TestParseWcRefund:
    def test_refund(self):
        data = {
            "id": 789,
            "order_id": 1234,
            "amount": "-25.00",
            "reason": "Defective product",
        }
        result = _parse_wc_refund(_wrap(data))

        assert result.refund_id == "789"
        assert result.order_id == "1234"
        assert result.amount == 25.0
        assert result.status == "processed"
        assert result.method == "original_payment"
