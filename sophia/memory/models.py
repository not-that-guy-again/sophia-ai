from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Episode:
    """A structured summary of a single conversation (Tier 2 memory)."""

    id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    conversation_id: str = ""
    participants: list[str] = field(default_factory=list)
    summary: str = ""
    actions_taken: list[str] = field(default_factory=list)
    outcome: str = ""
    entities_referenced: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    hat_name: str = ""


@dataclass
class Entity:
    """A known entity extracted from conversations (Tier 3 memory)."""

    id: str = ""
    entity_type: str = ""  # "person", "product", "order", "issue"
    name: str = ""
    attributes: dict = field(default_factory=dict)
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    embedding: list[float] = field(default_factory=list)


@dataclass
class Relationship:
    """A typed edge between two entities in the knowledge graph."""

    id: str = ""
    from_entity: str = ""
    relation: str = ""  # "owns", "purchased", "reported_issue", "contains"
    to_entity: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
