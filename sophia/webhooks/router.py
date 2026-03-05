"""Event router — decides what to do with normalized events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING

from sophia.memory.models import Entity
from sophia.webhooks.models import SophiaEvent

if TYPE_CHECKING:
    from sophia.memory.provider import MemoryProvider

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

    def __init__(
        self,
        webhooks_config: dict | None = None,
        memory: MemoryProvider | None = None,
        agent_loop: object | None = None,
        notification_service: object | None = None,
    ):
        self.webhooks_config = webhooks_config or {}
        self._seen: dict[tuple, datetime] = {}
        self._dedup_window_seconds = 300  # 5 minutes
        self.memory = memory
        self.agent_loop = agent_loop
        self.notification_service = notification_service
        self._notification_gate_instance = None

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

    async def execute(self, action: EventAction) -> None:
        """Execute the routed action."""
        if action.action == EventAction.MEMORY_UPDATE:
            await self._handle_memory_update(action)
        elif action.action == EventAction.TRIGGER_PIPELINE:
            await self._handle_trigger_pipeline(action)
        elif action.action == EventAction.MEMORY_UPDATE_AND_NOTIFY:
            await self._handle_memory_update(action)
            await self._handle_notify(action)

    async def _handle_memory_update(self, action: EventAction) -> None:
        """Convert event to Entity and store in memory."""
        if self.memory is None:
            logger.warning(
                "Memory provider not configured — skipping memory update for %s",
                action.event.entity_id,
            )
            return

        entity_id = f"{action.event.source}:{action.event.entity_type}:{action.event.entity_id}"
        entity = Entity(
            id=entity_id,
            entity_type=action.event.entity_type,
            name=action.event.entity_id,
            attributes={
                "source": action.event.source,
                "event_type": action.event.event_type,
                "data": action.event.data,
            },
            last_seen=datetime.now(UTC),
        )
        try:
            await self.memory.store_entity(entity)
            logger.info("Stored entity %s from webhook event", entity_id)
        except Exception:
            logger.exception("Failed to store entity %s (non-fatal)", entity_id)

    async def _handle_trigger_pipeline(self, action: EventAction) -> None:
        """Trigger the agent pipeline with a synthetic message."""
        if self.agent_loop is None:
            logger.warning(
                "Agent loop not configured — skipping pipeline trigger for %s",
                action.event.entity_id,
            )
            return

        message = (
            action.synthetic_message
            or f"Webhook event: {action.event.event_type} for {action.event.entity_id}"
        )
        try:
            result = await self.agent_loop.process(
                message=message,
                source="webhook",
                metadata={
                    "event": {
                        "source": action.event.source,
                        "event_type": action.event.event_type,
                        "entity_id": action.event.entity_id,
                    }
                },
            )
            logger.info(
                "Pipeline triggered from webhook: tier=%s action=%s",
                result.risk_classification.tier,
                result.execution.action_taken.tool_name,
            )
        except Exception:
            logger.exception("Pipeline trigger from webhook failed (non-fatal)")

    async def _handle_notify(self, action: EventAction) -> None:
        """Send notification for the event."""
        if self.notification_service is None:
            logger.info(
                "No notification service configured — skipping notify for %s:%s",
                action.event.entity_type,
                action.event.entity_id,
            )
            return

        from sophia.notifications.gate import NotificationGate
        from sophia.services.notification import NotificationMessage, NotificationRecipient

        # Look up customer info from memory if available
        email = None
        if self.memory:
            try:
                entity = await self.memory.get_entity(
                    f"{action.event.source}:customer:{action.event.entity_id}"
                )
                if entity:
                    email = entity.attributes.get("email")
            except Exception:
                logger.debug("Could not look up customer for notification")

        recipient = NotificationRecipient(
            customer_id=action.event.entity_id,
            email=email,
        )
        message = NotificationMessage(
            body=f"Update for your {action.event.entity_type}: {action.event.event_type}",
            subject=f"{action.event.entity_type.title()} Update",
            source_event=action.event.event_type,
        )

        # Check gate (persistent per router instance)
        if self._notification_gate_instance is None:
            self._notification_gate_instance = NotificationGate()
        allowed, reason = self._notification_gate_instance.check(
            action.event.entity_id,
            self._notification_limits,
        )
        if not allowed:
            logger.info("Notification blocked by gate: %s", reason)
            return

        try:
            result = await self.notification_service.send_notification(recipient, message)
            logger.info(
                "Notification sent: success=%s channel=%s",
                result.success,
                result.channel,
            )
        except Exception:
            logger.exception("Notification send failed (non-fatal)")

    @property
    def _notification_limits(self) -> dict:
        """Get notification limits from webhooks config."""
        for source_cfg in self.webhooks_config.values():
            if "notification_limits" in source_cfg:
                return source_cfg["notification_limits"]
        return {}
