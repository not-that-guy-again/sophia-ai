import json

import pytest

from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult
from sophia.services.mcp.shopify_mapping import (
    _extract_json,
    _map_shopify_status,
    _parse_shopify_cancellation,
    _parse_shopify_customer,
    _parse_shopify_order,
    _parse_shopify_product,
    _parse_shopify_refund,
)


def _wrap(data: dict) -> MCPToolResult:
    return MCPToolResult(content=[{"type": "text", "text": json.dumps(data)}])


class TestParseShopifyOrder:
    def test_full_order(self):
        data = {
            "id": 12345,
            "customer": {"id": 6789},
            "fulfillment_status": "fulfilled",
            "line_items": [
                {
                    "product_id": 111,
                    "title": "Widget",
                    "quantity": 2,
                    "price": "9.99",
                }
            ],
            "total_price": "19.98",
            "currency": "USD",
            "created_at": "2025-01-15T10:00:00Z",
            "updated_at": "2025-01-16T12:00:00Z",
            "shipping_address": {
                "address1": "123 Main St",
                "address2": "Apt 4",
                "city": "Springfield",
                "province": "IL",
                "zip": "62701",
                "country_code": "US",
            },
            "fulfillments": [{"tracking_number": "TRACK123"}],
        }
        order = _parse_shopify_order(_wrap(data))

        assert order.order_id == "12345"
        assert order.customer_id == "6789"
        assert order.status == "shipped"
        assert len(order.items) == 1
        assert order.items[0].name == "Widget"
        assert order.items[0].quantity == 2
        assert order.items[0].unit_price == 9.99
        assert order.items[0].total_price == 19.98
        assert order.total == 19.98
        assert order.currency == "USD"
        assert order.shipping_address is not None
        assert order.shipping_address.line1 == "123 Main St"
        assert order.shipping_address.line2 == "Apt 4"
        assert order.shipping_address.city == "Springfield"
        assert order.tracking_number == "TRACK123"

    def test_minimal_order(self):
        data = {
            "id": 99,
            "customer": {"id": 1},
            "total_price": "0",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        order = _parse_shopify_order(_wrap(data))

        assert order.order_id == "99"
        assert order.status == "pending"
        assert order.items == []
        assert order.shipping_address is None
        assert order.tracking_number is None

    def test_cancelled_order(self):
        data = {
            "id": 100,
            "customer": {"id": 1},
            "total_price": "50.00",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "cancelled_at": "2025-01-02T00:00:00Z",
            "fulfillment_status": "unfulfilled",
        }
        order = _parse_shopify_order(_wrap(data))
        assert order.status == "cancelled"


class TestParseShopifyCustomer:
    def test_full_customer(self):
        data = {
            "id": 42,
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "Smith",
            "phone": "+1234567890",
            "created_at": "2024-06-01T00:00:00Z",
            "orders_count": 5,
            "total_spent": "250.00",
            "tags": "vip, preferred",
        }
        customer = _parse_shopify_customer(_wrap(data))

        assert customer.customer_id == "42"
        assert customer.email == "alice@example.com"
        assert customer.name == "Alice Smith"
        assert customer.phone == "+1234567890"
        assert customer.total_orders == 5
        assert customer.total_spent == 250.0
        assert customer.tags == ["vip", "preferred"]

    def test_minimal_customer(self):
        data = {"id": 1, "email": "bob@test.com"}
        customer = _parse_shopify_customer(_wrap(data))

        assert customer.customer_id == "1"
        assert customer.email == "bob@test.com"
        assert customer.name == ""
        assert customer.phone is None


class TestMapShopifyStatus:
    def test_unfulfilled(self):
        assert _map_shopify_status("unfulfilled") == "pending"

    def test_fulfilled(self):
        assert _map_shopify_status("fulfilled") == "shipped"

    def test_partial(self):
        assert _map_shopify_status("partial") == "confirmed"

    def test_restocked(self):
        assert _map_shopify_status("restocked") == "cancelled"

    def test_none(self):
        assert _map_shopify_status(None) == "pending"

    def test_empty_string(self):
        assert _map_shopify_status("") == "pending"

    def test_unknown(self):
        assert _map_shopify_status("something_new") == "pending"


class TestExtractJson:
    def test_valid_text_block(self):
        result = MCPToolResult(content=[{"type": "text", "text": '{"key": "value"}'}])
        data = _extract_json(result)
        assert data == {"key": "value"}

    def test_no_content(self):
        result = MCPToolResult(content=[])
        with pytest.raises(MCPParseError, match="no content"):
            _extract_json(result)

    def test_no_text_block(self):
        result = MCPToolResult(content=[{"type": "image", "data": "..."}])
        with pytest.raises(MCPParseError, match="No text content"):
            _extract_json(result)

    def test_invalid_json(self):
        result = MCPToolResult(content=[{"type": "text", "text": "not json {{{"}])
        with pytest.raises(MCPParseError, match="Failed to parse"):
            _extract_json(result)


class TestParseShopifyProduct:
    def test_product_with_variants(self):
        data = {
            "id": 777,
            "title": "Super Gadget",
            "body_html": "A great gadget",
            "product_type": "Electronics",
            "variants": [{"price": "29.99"}],
        }
        product = _parse_shopify_product(_wrap(data))

        assert product.product_id == "777"
        assert product.name == "Super Gadget"
        assert product.price == 29.99
        assert product.category == "Electronics"


class TestParseShopifyCancellation:
    def test_successful_cancellation(self):
        data = {
            "id": 123,
            "cancelled_at": "2025-01-15T00:00:00Z",
            "total_price": "45.00",
        }
        result = _parse_shopify_cancellation(_wrap(data))

        assert result.order_id == "123"
        assert result.success is True
        assert result.refund_amount == 45.0

    def test_failed_cancellation(self):
        data = {"id": 123, "cancelled_at": None, "total_price": "45.00"}
        result = _parse_shopify_cancellation(_wrap(data))

        assert result.success is False


class TestParseShopifyRefund:
    def test_refund(self):
        data = {
            "id": 456,
            "order_id": 123,
            "transactions": [{"amount": "25.00"}],
        }
        result = _parse_shopify_refund(_wrap(data))

        assert result.refund_id == "456"
        assert result.order_id == "123"
        assert result.amount == 25.0
        assert result.status == "processed"
        assert result.method == "original_payment"
