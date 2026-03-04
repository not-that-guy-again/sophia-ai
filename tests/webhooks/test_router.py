"""Tests for event router."""

from datetime import datetime, timezone

from sophia.webhooks.models import SophiaEvent
from sophia.webhooks.router import EventAction, EventRouter


def _make_event(
    event_type="order.created",
    source="shopify",
    entity_id="123",
    timestamp=None,
) -> SophiaEvent:
    return SophiaEvent(
        event_type=event_type,
        source=source,
        entity_type="order",
        entity_id=entity_id,
        data={},
        timestamp=timestamp or datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_route_known_event():
    config = {
        "shopify": {
            "secret_env": "SECRET",
            "events": {
                "orders/cancelled": {"action": "memory_update"},
            },
        }
    }
    router = EventRouter(config)
    event = _make_event(event_type="order.cancelled")
    action = router.route(event, "orders/cancelled")
    assert action is not None
    assert action.action == EventAction.MEMORY_UPDATE
    assert action.event is event


def test_route_trigger_pipeline_with_synthetic_message():
    config = {
        "shipstation": {
            "events": {
                "DELIVERY_EXCEPTION": {
                    "action": "trigger_pipeline",
                    "synthetic_message": "Delay for order {entity_id}.",
                }
            }
        }
    }
    router = EventRouter(config)
    event = _make_event(source="shipstation", entity_id="ORD-555")
    action = router.route(event, "DELIVERY_EXCEPTION")
    assert action is not None
    assert action.action == EventAction.TRIGGER_PIPELINE
    assert action.synthetic_message == "Delay for order ORD-555."


def test_route_unknown_topic_defaults_to_memory_update():
    """Known source but unknown topic defaults to memory_update."""
    config = {"shopify": {"events": {}}}
    router = EventRouter(config)
    event = _make_event()
    action = router.route(event, "orders/some_new_topic")
    assert action is not None
    assert action.action == EventAction.MEMORY_UPDATE


def test_route_unknown_source_returns_none():
    router = EventRouter({})
    event = _make_event(source="unknown_platform")
    action = router.route(event, "some_topic")
    assert action is None


def test_deduplication():
    config = {"shopify": {"events": {"orders/create": {"action": "memory_update"}}}}
    router = EventRouter(config)
    ts = datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    event1 = _make_event(timestamp=ts)
    event2 = _make_event(timestamp=ts)  # Same everything

    action1 = router.route(event1, "orders/create")
    assert action1 is not None

    action2 = router.route(event2, "orders/create")
    assert action2 is None  # Duplicate


def test_different_events_not_deduplicated():
    config = {"shopify": {"events": {"orders/create": {"action": "memory_update"}}}}
    router = EventRouter(config)
    event1 = _make_event(entity_id="111")
    event2 = _make_event(entity_id="222")

    assert router.route(event1, "orders/create") is not None
    assert router.route(event2, "orders/create") is not None
