from abc import ABC, abstractmethod
from datetime import datetime

from sophia.memory.models import Entity, Episode, Relationship


class MemoryProvider(ABC):
    """Abstract base class for memory backends.

    Mirrors the LLMProvider pattern (ADR-015). Pipeline code calls these
    methods without knowing which backend is in use.
    """

    # --- Tier 2: Episodic memory ---

    @abstractmethod
    async def store_episode(self, episode: Episode) -> str:
        """Persist a conversation summary. Returns the episode ID."""

    @abstractmethod
    async def recall_by_entity(
        self, entity_type: str, entity_id: str, limit: int = 10
    ) -> list[Episode]:
        """Find episodes that reference a specific entity."""

    @abstractmethod
    async def recall_similar(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[Episode]:
        """Semantic similarity search over episodes."""

    @abstractmethod
    async def recall_by_timerange(
        self, start: datetime, end: datetime, limit: int = 20
    ) -> list[Episode]:
        """Retrieve episodes within a time window."""

    # --- Tier 3: Entity knowledge graph ---

    @abstractmethod
    async def store_entity(self, entity: Entity) -> str:
        """Persist an entity record. Returns the entity ID."""

    @abstractmethod
    async def store_relationship(self, relationship: Relationship) -> str:
        """Create a graph edge between two entities. Returns the relationship ID."""

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Entity | None:
        """Retrieve a known entity by ID."""

    @abstractmethod
    async def get_relationships(
        self, entity_id: str, relation_type: str | None = None
    ) -> list[Relationship]:
        """Get relationships for an entity, optionally filtered by type."""

    @abstractmethod
    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        """Search entities by name or attribute text."""


def get_memory_provider(config) -> MemoryProvider:
    """Factory function to create the appropriate memory provider."""
    provider = getattr(config, "memory_provider", "mock")

    if provider == "surrealdb":
        from sophia.memory.surrealdb import SurrealMemoryProvider

        return SurrealMemoryProvider(config)
    elif provider == "mock":
        from sophia.memory.mock import MockMemoryProvider

        return MockMemoryProvider()
    else:
        raise ValueError(f"Unknown memory provider: {provider}")
