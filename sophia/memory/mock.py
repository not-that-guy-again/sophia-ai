import uuid
from datetime import datetime

from sophia.memory.models import Entity, Episode, Relationship
from sophia.memory.provider import MemoryProvider


class MockMemoryProvider(MemoryProvider):
    """In-memory dict-based memory provider for testing.

    Zero external dependencies. Mirrors the MockLLMProvider pattern.
    """

    def __init__(self):
        self.episodes: dict[str, Episode] = {}
        self.entities: dict[str, Entity] = {}
        self.relationships: dict[str, Relationship] = {}

    # --- Tier 2: Episodic memory ---

    async def store_episode(self, episode: Episode) -> str:
        if not episode.id:
            episode.id = f"ep_{uuid.uuid4().hex[:8]}"
        self.episodes[episode.id] = episode
        return episode.id

    async def recall_by_entity(
        self, entity_type: str, entity_id: str, limit: int = 10
    ) -> list[Episode]:
        results = [ep for ep in self.episodes.values() if entity_id in ep.entities_referenced]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def recall_similar(self, query_embedding: list[float], limit: int = 5) -> list[Episode]:
        # Mock: return most recent episodes (no real vector search)
        results = sorted(self.episodes.values(), key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def recall_by_timerange(
        self, start: datetime, end: datetime, limit: int = 20
    ) -> list[Episode]:
        results = [ep for ep in self.episodes.values() if start <= ep.timestamp <= end]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    # --- Tier 3: Entity knowledge graph ---

    async def store_entity(self, entity: Entity) -> str:
        if not entity.id:
            entity.id = f"ent_{uuid.uuid4().hex[:8]}"
        self.entities[entity.id] = entity
        return entity.id

    async def store_relationship(self, relationship: Relationship) -> str:
        if not relationship.id:
            relationship.id = f"rel_{uuid.uuid4().hex[:8]}"
        self.relationships[relationship.id] = relationship
        return relationship.id

    async def get_entity(self, entity_id: str) -> Entity | None:
        return self.entities.get(entity_id)

    async def get_relationships(
        self, entity_id: str, relation_type: str | None = None
    ) -> list[Relationship]:
        results = [
            rel
            for rel in self.relationships.values()
            if rel.from_entity == entity_id or rel.to_entity == entity_id
        ]
        if relation_type:
            results = [r for r in results if r.relation == relation_type]
        return results

    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        query_lower = query.lower()
        results = [
            ent
            for ent in self.entities.values()
            if query_lower in ent.name.lower()
            or any(query_lower in str(v).lower() for v in ent.attributes.values())
        ]
        return results[:limit]
