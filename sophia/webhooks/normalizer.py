"""Event normalizer ABC and Shopify implementation."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sophia.webhooks.models import SophiaEvent

# Maps Shopify webhook topics to (event_type, entity_type) tuples.
_SHOPIFY_TOPIC_MAP: dict[str, tuple[str, str]] = {
    "orders/create": ("order.created", "order"),
    "orders/cancelled": ("order.cancelled", "order"),
    "orders/fulfilled": ("order.fulfilled", "order"),
    "orders/paid": ("order.paid", "order"),
    "orders/updated": ("order.updated", "order"),
    "refunds/create": ("refund.created", "order"),
}


class EventNormalizer(ABC):
    """Maps platform-specific payloads into SophiaEvent dataclass."""

    @abstractmethod
    def normalize(self, topic: str, payload: dict) -> SophiaEvent:
        """Convert a platform-specific webhook payload to a SophiaEvent.

        Args:
            topic: The event topic/type as reported by the source platform.
            payload: The parsed JSON payload from the webhook.

        Returns:
            A normalized SophiaEvent.
        """
        ...


class ShopifyNormalizer(EventNormalizer):
    """Normalizer for Shopify webhook payloads."""

    def normalize(self, topic: str, payload: dict) -> SophiaEvent:
        mapped = _SHOPIFY_TOPIC_MAP.get(topic)
        if mapped:
            event_type, entity_type = mapped
        else:
            # Derive from topic: "orders/cancelled" -> ("orders.cancelled", "order")
            parts = topic.split("/")
            entity_type = parts[0].rstrip("s") if parts else "unknown"
            event_type = topic.replace("/", ".")

        # Shopify payloads always have an "id" at the top level.
        entity_id = str(payload.get("id", ""))

        # Try to parse a timestamp from the payload.
        ts_raw = payload.get("updated_at") or payload.get("created_at")
        if ts_raw:
            try:
                timestamp = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(tz=timezone.utc)
        else:
            timestamp = datetime.now(tz=timezone.utc)

        return SophiaEvent(
            event_type=event_type,
            source="shopify",
            entity_type=entity_type,
            entity_id=entity_id,
            data={
                "order_number": payload.get("order_number"),
                "email": payload.get("email"),
                "total_price": payload.get("total_price"),
                "financial_status": payload.get("financial_status"),
                "fulfillment_status": payload.get("fulfillment_status"),
            },
            timestamp=timestamp,
            raw_payload=payload,
        )


# Registry of normalizers keyed by source name.
NORMALIZER_REGISTRY: dict[str, type[EventNormalizer]] = {
    "shopify": ShopifyNormalizer,
}
