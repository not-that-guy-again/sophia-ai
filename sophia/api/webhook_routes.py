"""Webhook ingestion API routes."""

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response

from sophia.webhooks.models import SophiaEvent
from sophia.webhooks.normalizer import NORMALIZER_REGISTRY
from sophia.webhooks.router import EventAction, EventRouter
from sophia.webhooks.validators import (
    NoopValidator,
    ShopifySignatureValidator,
    SignatureValidator,
)

logger = logging.getLogger(__name__)

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Module-level state — configured when a hat is equipped.
_event_router: EventRouter | None = None
_validators: dict[str, SignatureValidator] = {}


def configure_webhooks(webhooks_config: dict) -> None:
    """Initialize webhook routing from a hat's webhooks config block.

    Called during hat equip.  Sets up validators and the event router.
    """
    global _event_router, _validators

    _event_router = EventRouter(webhooks_config)
    _validators = {}

    for source, source_cfg in webhooks_config.items():
        secret_env = source_cfg.get("secret_env")
        secret = os.environ.get(secret_env, "") if secret_env else ""

        if source == "shopify" and secret:
            _validators[source] = ShopifySignatureValidator(secret)
        else:
            # In dev / test or when no secret is configured, use noop.
            _validators[source] = NoopValidator()

    logger.info(
        "Webhooks configured: sources=%s",
        list(webhooks_config.keys()),
    )


def teardown_webhooks() -> None:
    """Reset webhook state when a hat is unequipped."""
    global _event_router, _validators
    _event_router = None
    _validators = {}


# Processed events log (in-memory, for audit/inspection).
_processed_events: list[dict] = []

MAX_EVENT_LOG = 100


@webhook_router.post("/{source}")
async def receive_webhook(source: str, request: Request) -> Response:
    """Receive a webhook from an external system.

    Returns 200 immediately after validation to avoid webhook timeouts.
    Processing happens synchronously for now; async queueing can be
    added later without changing the external contract.
    """
    if _event_router is None:
        raise HTTPException(status_code=503, detail="No hat equipped — webhooks not configured")

    # Check that the source is recognized.
    if source not in _event_router.webhooks_config:
        raise HTTPException(status_code=404, detail=f"Unknown webhook source: {source}")

    # Read raw body for signature validation.
    body = await request.body()

    # Validate signature.
    validator = _validators.get(source)
    if validator and not validator.validate(body, dict(request.headers)):
        logger.warning("Webhook signature validation failed for source=%s", source)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload.
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Determine topic from headers or payload.
    topic = _extract_topic(source, request, payload)

    # Normalize.
    normalizer_cls = NORMALIZER_REGISTRY.get(source)
    if normalizer_cls is None:
        logger.warning("No normalizer registered for source=%s", source)
        raise HTTPException(status_code=400, detail=f"No normalizer for source: {source}")

    normalizer = normalizer_cls()
    event: SophiaEvent = normalizer.normalize(topic, payload)

    # Route.
    action = _event_router.route(event, topic)
    if action is None:
        return Response(status_code=200, content="Event acknowledged (duplicate or unrouted)")

    # Record for audit.
    _record_event(event, action)

    logger.info(
        "Webhook processed: source=%s topic=%s action=%s entity=%s",
        source,
        topic,
        action.action,
        event.entity_id,
    )

    return Response(status_code=200, content="OK")


def _extract_topic(source: str, request: Request, payload: dict) -> str:
    """Extract the event topic from headers or payload depending on source."""
    if source == "shopify":
        return request.headers.get("x-shopify-topic", "")
    # Generic fallback: look for a "topic" or "event" key in payload.
    return str(payload.get("resource_type", payload.get("topic", payload.get("event", ""))))


def _record_event(event: SophiaEvent, action: EventAction) -> None:
    """Append event to in-memory log for inspection."""
    _processed_events.append(
        {
            "event_type": event.event_type,
            "source": event.source,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "action": action.action,
            "timestamp": event.timestamp.isoformat(),
        }
    )
    # Keep bounded.
    while len(_processed_events) > MAX_EVENT_LOG:
        _processed_events.pop(0)


@webhook_router.get("/events")
async def list_processed_events():
    """Return recently processed webhook events (for debugging/audit)."""
    return _processed_events
