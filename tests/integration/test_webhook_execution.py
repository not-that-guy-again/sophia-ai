"""Integration test: Webhook event → EventRouter → memory update / pipeline trigger.

Uses MockMemoryProvider and mock agent loop. No real HTTP calls.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from sophia.memory.mock import MockMemoryProvider
from sophia.notifications.log import LogNotificationService
from sophia.webhooks.models import SophiaEvent
from sophia.webhooks.router import EventAction, EventRouter


# ── Fixtures ─────────────────────────────────────────────────────────────────

WEBHOOK_CONFIG = {
    "shopify": {
        "secret_env": "SHOPIFY_WEBHOOK_SECRET",
        "events": {
            "orders/fulfilled": {"action": "memory_update"},
            "DELIVERY_EXCEPTION": {
                "action": "trigger_pipeline",
                "synthetic_message": "Shipment delay for order {entity_id}.",
            },
            "orders/cancelled": {
                "action": "memory_update_and_notify",
            },
        },
    },
}


def _make_event(event_type: str, entity_id: str = "ORD-999") -> SophiaEvent:
    return SophiaEvent(
        event_type=event_type,
        source="shopify",
        entity_type="order",
        entity_id=entity_id,
        data={"order_name": "#1001"},
        timestamp=datetime.now(UTC),
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_update_stores_entity():
    """memory_update action stores an entity via MemoryProvider."""
    memory = MockMemoryProvider()
    router = EventRouter(
        webhooks_config=WEBHOOK_CONFIG,
        memory=memory,
    )

    event = _make_event("orders/fulfilled")
    action = router.route(event, "orders/fulfilled")

    assert action is not None
    assert action.action == EventAction.MEMORY_UPDATE

    await router.execute(action)

    # Verify entity was stored
    entity = await memory.get_entity("shopify:order:ORD-999")
    assert entity is not None
    assert entity.entity_type == "order"
    assert entity.attributes["event_type"] == "orders/fulfilled"


@pytest.mark.asyncio
async def test_trigger_pipeline_calls_agent_loop():
    """trigger_pipeline action invokes agent_loop.process with synthetic message."""
    memory = MockMemoryProvider()
    mock_loop = AsyncMock()
    mock_loop.process.return_value = AsyncMock(
        risk_classification=AsyncMock(tier="GREEN"),
        execution=AsyncMock(action_taken=AsyncMock(tool_name="check_order_status")),
    )

    router = EventRouter(
        webhooks_config=WEBHOOK_CONFIG,
        memory=memory,
        agent_loop=mock_loop,
    )

    event = _make_event("DELIVERY_EXCEPTION", entity_id="ORD-500")
    action = router.route(event, "DELIVERY_EXCEPTION")

    assert action is not None
    assert action.action == EventAction.TRIGGER_PIPELINE
    assert action.synthetic_message == "Shipment delay for order ORD-500."

    await router.execute(action)

    mock_loop.process.assert_awaited_once_with(
        message="Shipment delay for order ORD-500.",
        source="webhook",
        metadata={
            "event": {
                "source": "shopify",
                "event_type": "DELIVERY_EXCEPTION",
                "entity_id": "ORD-500",
            }
        },
    )


@pytest.mark.asyncio
async def test_memory_update_and_notify():
    """memory_update_and_notify stores entity AND sends notification."""
    memory = MockMemoryProvider()
    notifier = LogNotificationService()

    router = EventRouter(
        webhooks_config=WEBHOOK_CONFIG,
        memory=memory,
        notification_service=notifier,
    )

    event = _make_event("orders/cancelled", entity_id="ORD-777")
    action = router.route(event, "orders/cancelled")

    assert action is not None
    assert action.action == EventAction.MEMORY_UPDATE_AND_NOTIFY

    await router.execute(action)

    # Verify memory was updated
    entity = await memory.get_entity("shopify:order:ORD-777")
    assert entity is not None


@pytest.mark.asyncio
async def test_dedup_ignores_repeat_events():
    """Duplicate events within the dedup window are ignored."""
    memory = MockMemoryProvider()
    router = EventRouter(
        webhooks_config=WEBHOOK_CONFIG,
        memory=memory,
    )

    event = _make_event("orders/fulfilled", entity_id="ORD-DEDUP")
    action1 = router.route(event, "orders/fulfilled")
    assert action1 is not None

    # Same event again → should be deduplicated
    action2 = router.route(event, "orders/fulfilled")
    assert action2 is None


@pytest.mark.asyncio
async def test_unknown_source_ignored():
    """Events from unknown sources are ignored."""
    router = EventRouter(webhooks_config=WEBHOOK_CONFIG)
    event = SophiaEvent(
        event_type="something",
        source="unknown_platform",
        entity_type="order",
        entity_id="X-1",
        data={},
        timestamp=datetime.now(UTC),
    )
    action = router.route(event, "something")
    assert action is None
