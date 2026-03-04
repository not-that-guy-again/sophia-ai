"""Tests for event normalizers."""

from sophia.webhooks.normalizer import NORMALIZER_REGISTRY, ShopifyNormalizer


def test_shopify_normalizer_order_created():
    normalizer = ShopifyNormalizer()
    payload = {
        "id": 820982911946154500,
        "order_number": 1001,
        "email": "bob@example.com",
        "total_price": "149.99",
        "financial_status": "paid",
        "fulfillment_status": None,
        "created_at": "2025-03-01T12:00:00-05:00",
        "updated_at": "2025-03-01T12:05:00-05:00",
    }
    event = normalizer.normalize("orders/create", payload)
    assert event.event_type == "order.created"
    assert event.source == "shopify"
    assert event.entity_type == "order"
    assert event.entity_id == "820982911946154500"
    assert event.data["order_number"] == 1001
    assert event.data["email"] == "bob@example.com"
    assert event.data["total_price"] == "149.99"
    assert event.raw_payload is payload


def test_shopify_normalizer_order_cancelled():
    normalizer = ShopifyNormalizer()
    payload = {
        "id": 555,
        "email": "cancel@example.com",
        "total_price": "29.99",
        "financial_status": "refunded",
        "fulfillment_status": None,
        "updated_at": "2025-06-15T08:00:00Z",
    }
    event = normalizer.normalize("orders/cancelled", payload)
    assert event.event_type == "order.cancelled"
    assert event.entity_type == "order"
    assert event.entity_id == "555"


def test_shopify_normalizer_refund_created():
    normalizer = ShopifyNormalizer()
    payload = {
        "id": 999,
        "created_at": "2025-04-10T10:00:00Z",
    }
    event = normalizer.normalize("refunds/create", payload)
    assert event.event_type == "refund.created"
    assert event.entity_type == "order"


def test_shopify_normalizer_unknown_topic():
    """Unknown topics should derive event_type from the topic string."""
    normalizer = ShopifyNormalizer()
    payload = {"id": 111, "created_at": "2025-01-01T00:00:00Z"}
    event = normalizer.normalize("carts/create", payload)
    assert event.event_type == "carts.create"
    assert event.entity_type == "cart"


def test_shopify_normalizer_missing_timestamp():
    """Should default to now if no timestamp fields present."""
    normalizer = ShopifyNormalizer()
    payload = {"id": 222}
    event = normalizer.normalize("orders/create", payload)
    assert event.timestamp is not None


def test_normalizer_registry():
    assert "shopify" in NORMALIZER_REGISTRY
    assert NORMALIZER_REGISTRY["shopify"] is ShopifyNormalizer
