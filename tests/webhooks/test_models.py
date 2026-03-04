"""Tests for webhook models."""

from datetime import datetime, timezone

from sophia.webhooks.models import SophiaEvent


def test_sophia_event_creation():
    event = SophiaEvent(
        event_type="order.created",
        source="shopify",
        entity_type="order",
        entity_id="12345",
        data={"total": 99.99},
        timestamp=datetime(2025, 3, 1, tzinfo=timezone.utc),
    )
    assert event.event_type == "order.created"
    assert event.source == "shopify"
    assert event.entity_type == "order"
    assert event.entity_id == "12345"
    assert event.data == {"total": 99.99}
    assert event.raw_payload == {}


def test_sophia_event_with_raw_payload():
    raw = {"id": 123, "email": "test@example.com"}
    event = SophiaEvent(
        event_type="order.cancelled",
        source="shopify",
        entity_type="order",
        entity_id="123",
        data={},
        timestamp=datetime.now(tz=timezone.utc),
        raw_payload=raw,
    )
    assert event.raw_payload == raw
