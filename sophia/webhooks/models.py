"""Webhook event models."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SophiaEvent:
    """Normalized event from an external webhook source."""

    event_type: str  # "shipment.delayed", "payment.failed", "return.received"
    source: str  # "shopify", "shipstation", "stripe"
    entity_type: str  # "order", "customer", "shipment"
    entity_id: str  # The relevant ID
    data: dict  # Normalized payload
    timestamp: datetime
    raw_payload: dict = field(default_factory=dict)  # Original payload for audit
