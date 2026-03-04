"""Event router — decides what to do with normalized events."""

import logging
from datetime import datetime, timezone

from sophia.webhooks.models import SophiaEvent

logger = logging.getLogger(__name__)


class EventAction:
    """Describes the action(s) to take for an event."""

    MEMORY_UPDATE = "memory_update"
    MEMORY_UPDATE_AND_NOTIFY = "memory_update_and_notify"
    TRIGGER_PIPELINE = "trigger_pipeline"

    def __init__(
        self,
        action: str,
        event: SophiaEvent,
        synthetic_message: str | None = None,
    ):
        self.action = action
        self.event = event
        self.synthetic_message = synthetic_message


class EventRouter:
    """Routes normalized events to the appropriate actions based on hat config.

    The webhook config from hat.json looks like:
    {
        "shopify": {
            "secret_env": "SHOPIFY_WEBHOOK_SECRET",
            "events": {
                "orders/cancelled": { "action": "memory_update" },
                "orders/fulfilled": { "action": "memory_update" },
                "DELIVERY_EXCEPTION": {
                    "action": "trigger_pipeline",
                    "synthetic_message": "Shipment delay for order {entity_id}."
                }
            }
        }
    }
    """

    def __init__(self, webhooks_config: dict | None = None):
        self.webhooks_config = webhooks_config or {}
        self._seen: dict[tuple, datetime] = {}
        self._dedup_window_seconds = 300  # 5 minutes

    def route(self, event: SophiaEvent, topic: str) -> EventAction | None:
        """Determine the action for a normalized event.

        Returns None if the event should be ignored (unknown topic or duplicate).
        """
        # Deduplication
        dedup_key = (event.source, event.event_type, event.entity_id, event.timestamp)
        now = datetime.now(tz=timezone.utc)
        if dedup_key in self._seen:
            prev = self._seen[dedup_key]
            if (now - prev).total_seconds() < self._dedup_window_seconds:
                logger.debug("Duplicate event ignored: %s", dedup_key)
                return None
        self._seen[dedup_key] = now

        # Clean old entries
        self._seen = {
            k: v
            for k, v in self._seen.items()
            if (now - v).total_seconds() < self._dedup_window_seconds
        }

        source_config = self.webhooks_config.get(event.source, {})
        events_config = source_config.get("events", {})

        event_cfg = events_config.get(topic)
        if event_cfg is None:
            # Default to memory_update for known sources, ignore for unknown
            if event.source in self.webhooks_config:
                return EventAction(
                    action=EventAction.MEMORY_UPDATE,
                    event=event,
                )
            return None

        action = event_cfg.get("action", EventAction.MEMORY_UPDATE)
        synthetic_message = event_cfg.get("synthetic_message")

        # Interpolate entity_id into synthetic message
        if synthetic_message and "{entity_id}" in synthetic_message:
            synthetic_message = synthetic_message.replace("{entity_id}", event.entity_id)

        return EventAction(
            action=action,
            event=event,
            synthetic_message=synthetic_message,
        )
