"""Tests for webhook API routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from sophia.api.webhook_routes import (
    _processed_events,
    configure_webhooks,
    teardown_webhooks,
)
from sophia.main import app


@pytest.fixture(autouse=True)
def _configure_webhooks():
    """Set up webhook config for tests, clean up after."""
    configure_webhooks(
        {
            "shopify": {
                "events": {
                    "orders/create": {"action": "memory_update"},
                    "orders/cancelled": {"action": "memory_update"},
                },
            },
        }
    )
    _processed_events.clear()
    yield
    teardown_webhooks()
    _processed_events.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_webhook_shopify_order_created(client):
    resp = await client.post(
        "/webhooks/shopify",
        json={
            "id": 12345,
            "order_number": 1001,
            "email": "test@example.com",
            "total_price": "99.99",
            "created_at": "2025-03-01T12:00:00Z",
        },
        headers={"x-shopify-topic": "orders/create"},
    )
    assert resp.status_code == 200
    assert len(_processed_events) == 1
    assert _processed_events[0]["event_type"] == "order.created"
    assert _processed_events[0]["entity_id"] == "12345"


async def test_webhook_unknown_source(client):
    resp = await client.post(
        "/webhooks/unknown_platform",
        json={"id": 1},
    )
    assert resp.status_code == 404


async def test_webhook_invalid_json(client):
    resp = await client.post(
        "/webhooks/shopify",
        content=b"not valid json",
        headers={"content-type": "application/json", "x-shopify-topic": "orders/create"},
    )
    assert resp.status_code == 400


async def test_webhook_events_endpoint(client):
    # Post an event first
    await client.post(
        "/webhooks/shopify",
        json={"id": 999, "created_at": "2025-01-01T00:00:00Z"},
        headers={"x-shopify-topic": "orders/cancelled"},
    )
    resp = await client.get("/webhooks/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1
    assert events[-1]["event_type"] == "order.cancelled"


async def test_webhook_no_hat_equipped():
    """When no hat is equipped, webhooks should return 503."""
    teardown_webhooks()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/webhooks/shopify",
            json={"id": 1},
            headers={"x-shopify-topic": "orders/create"},
        )
    assert resp.status_code == 503


async def test_webhook_duplicate_ignored(client):
    """Duplicate events should be acknowledged but not reprocessed."""
    payload = {"id": 777, "created_at": "2025-06-01T10:00:00Z"}
    headers = {"x-shopify-topic": "orders/create"}

    await client.post("/webhooks/shopify", json=payload, headers=headers)
    await client.post("/webhooks/shopify", json=payload, headers=headers)

    assert len(_processed_events) == 1
