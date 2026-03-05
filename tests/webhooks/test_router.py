"""Tests for event router."""

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

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


# ── Execute Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_memory_update():
    mock_memory = AsyncMock()
    mock_memory.store_entity.return_value = "entity-id"

    router = EventRouter({"shopify": {"events": {}}}, memory=mock_memory)
    event = _make_event(entity_id="ORD-123")
    action = EventAction(EventAction.MEMORY_UPDATE, event)

    await router.execute(action)

    mock_memory.store_entity.assert_called_once()
    stored_entity = mock_memory.store_entity.call_args[0][0]
    assert stored_entity.id == "shopify:order:ORD-123"
    assert stored_entity.entity_type == "order"
    assert stored_entity.name == "ORD-123"


@pytest.mark.asyncio
async def test_execute_trigger_pipeline():
    mock_loop = AsyncMock()
    mock_loop.process.return_value = AsyncMock(
        risk_classification=AsyncMock(tier="GREEN"),
        execution=AsyncMock(action_taken=AsyncMock(tool_name="look_up_order")),
    )

    router = EventRouter({"shopify": {"events": {}}}, agent_loop=mock_loop)
    event = _make_event(entity_id="ORD-123")
    action = EventAction(
        EventAction.TRIGGER_PIPELINE, event, synthetic_message="Check order ORD-123"
    )

    await router.execute(action)

    mock_loop.process.assert_called_once()
    call_kwargs = mock_loop.process.call_args[1]
    assert call_kwargs["message"] == "Check order ORD-123"
    assert call_kwargs["source"] == "webhook"


@pytest.mark.asyncio
async def test_execute_no_memory_logs_warning(caplog):
    router = EventRouter({"shopify": {"events": {}}})
    event = _make_event()
    action = EventAction(EventAction.MEMORY_UPDATE, event)

    with caplog.at_level(logging.WARNING):
        await router.execute(action)

    assert "Memory provider not configured" in caplog.text


@pytest.mark.asyncio
async def test_execute_no_agent_loop_logs_warning(caplog):
    router = EventRouter({"shopify": {"events": {}}})
    event = _make_event()
    action = EventAction(EventAction.TRIGGER_PIPELINE, event, synthetic_message="test")

    with caplog.at_level(logging.WARNING):
        await router.execute(action)

    assert "Agent loop not configured" in caplog.text


# ── Notification Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_notify_sends_notification():
    mock_notif = AsyncMock()
    mock_notif.send_notification.return_value = AsyncMock(success=True, channel="log")

    router = EventRouter(
        {"shopify": {"events": {}}},
        notification_service=mock_notif,
    )
    event = _make_event(entity_id="CUST-1")
    action = EventAction(EventAction.MEMORY_UPDATE_AND_NOTIFY, event)

    await router.execute(action)

    mock_notif.send_notification.assert_called_once()


@pytest.mark.asyncio
async def test_execute_notify_without_service_skips(caplog):
    router = EventRouter({"shopify": {"events": {}}})
    event = _make_event()
    action = EventAction(EventAction.MEMORY_UPDATE_AND_NOTIFY, event)

    with caplog.at_level(logging.INFO):
        await router.execute(action)

    assert "No notification service configured" in caplog.text


@pytest.mark.asyncio
async def test_execute_notify_gate_blocks():
    mock_notif = AsyncMock()

    router = EventRouter(
        {
            "shopify": {
                "events": {},
                "notification_limits": {"max_daily_per_customer": 1},
            }
        },
        notification_service=mock_notif,
    )
    event = _make_event(entity_id="CUST-1")
    action = EventAction(EventAction.MEMORY_UPDATE_AND_NOTIFY, event)

    # First should go through
    await router.execute(action)
    assert mock_notif.send_notification.call_count == 1

    # Second should be blocked by gate
    action2 = EventAction(EventAction.MEMORY_UPDATE_AND_NOTIFY, event)
    await router.execute(action2)
    # Still 1 — blocked by rate limit
    assert mock_notif.send_notification.call_count == 1
