import logging
import uuid
from datetime import UTC, datetime

from sophia.memory.models import Entity, Episode, Relationship
from sophia.memory.provider import MemoryProvider

logger = logging.getLogger(__name__)


class SurrealMemoryProvider(MemoryProvider):
    """Production memory provider backed by SurrealDB.

    Uses native document storage, RELATE syntax for graph edges,
    and vector search for semantic similarity.
    """

    def __init__(self, config):
        self.url = getattr(config, "surrealdb_url", "ws://localhost:8529")
        self.user = getattr(config, "surrealdb_user", "root")
        self.password = getattr(config, "surrealdb_pass", "root")
        self.namespace = getattr(config, "surrealdb_namespace", "sophia")
        self.database = getattr(config, "surrealdb_database", "memory")
        self._db = None

    async def _connect(self):
        """Lazily connect to SurrealDB."""
        if self._db is not None:
            return

        from surrealdb import Surreal

        self._db = Surreal(self.url)
        await self._db.connect()
        await self._db.signin({"user": self.user, "pass": self.password})
        await self._db.use(self.namespace, self.database)
        logger.info("Connected to SurrealDB at %s", self.url)

    # --- Tier 2: Episodic memory ---

    async def store_episode(self, episode: Episode) -> str:
        await self._connect()
        if not episode.id:
            episode.id = f"ep_{uuid.uuid4().hex[:8]}"

        data = {
            "timestamp": episode.timestamp.isoformat(),
            "conversation_id": episode.conversation_id,
            "participants": episode.participants,
            "summary": episode.summary,
            "actions_taken": episode.actions_taken,
            "outcome": episode.outcome,
            "entities_referenced": episode.entities_referenced,
            "embedding": episode.embedding,
            "hat_name": episode.hat_name,
        }
        await self._db.create(f"episode:{episode.id}", data)
        return episode.id

    async def recall_by_entity(
        self, entity_type: str, entity_id: str, limit: int = 10
    ) -> list[Episode]:
        await self._connect()
        query = """
            SELECT * FROM episode
            WHERE $entity_id IN entities_referenced
            ORDER BY timestamp DESC
            LIMIT $limit
        """
        result = await self._db.query(query, {"entity_id": entity_id, "limit": limit})
        return [self._parse_episode(r) for r in self._extract_records(result)]

    async def recall_similar(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[Episode]:
        await self._connect()
        # Vector similarity search using SurrealDB's native vector functions
        query = """
            SELECT *, vector::similarity::cosine(embedding, $embedding) AS score
            FROM episode
            WHERE embedding != []
            ORDER BY score DESC
            LIMIT $limit
        """
        result = await self._db.query(
            query, {"embedding": query_embedding, "limit": limit}
        )
        return [self._parse_episode(r) for r in self._extract_records(result)]

    async def recall_by_timerange(
        self, start: datetime, end: datetime, limit: int = 20
    ) -> list[Episode]:
        await self._connect()
        query = """
            SELECT * FROM episode
            WHERE timestamp >= $start AND timestamp <= $end
            ORDER BY timestamp DESC
            LIMIT $limit
        """
        result = await self._db.query(
            query, {"start": start.isoformat(), "end": end.isoformat(), "limit": limit}
        )
        return [self._parse_episode(r) for r in self._extract_records(result)]

    # --- Tier 3: Entity knowledge graph ---

    async def store_entity(self, entity: Entity) -> str:
        await self._connect()
        if not entity.id:
            entity.id = f"ent_{uuid.uuid4().hex[:8]}"

        data = {
            "entity_type": entity.entity_type,
            "name": entity.name,
            "attributes": entity.attributes,
            "first_seen": entity.first_seen.isoformat(),
            "last_seen": entity.last_seen.isoformat(),
            "embedding": entity.embedding,
        }
        await self._db.create(f"entity:{entity.id}", data)
        return entity.id

    async def store_relationship(self, relationship: Relationship) -> str:
        await self._connect()
        if not relationship.id:
            relationship.id = f"rel_{uuid.uuid4().hex[:8]}"

        # Use SurrealDB's native RELATE syntax for graph edges
        query = """
            RELATE $from->$relation->$to SET
                metadata = $metadata,
                created_at = $created_at,
                rel_id = $rel_id
        """
        await self._db.query(query, {
            "from": f"entity:{relationship.from_entity}",
            "relation": relationship.relation,
            "to": f"entity:{relationship.to_entity}",
            "metadata": relationship.metadata,
            "created_at": relationship.created_at.isoformat(),
            "rel_id": relationship.id,
        })
        return relationship.id

    async def get_entity(self, entity_id: str) -> Entity | None:
        await self._connect()
        result = await self._db.select(f"entity:{entity_id}")
        if not result:
            return None
        data = result if isinstance(result, dict) else result[0]
        return self._parse_entity(data)

    async def get_relationships(
        self, entity_id: str, relation_type: str | None = None
    ) -> list[Relationship]:
        await self._connect()
        if relation_type:
            query = """
                SELECT * FROM $relation
                WHERE in = $entity OR out = $entity
            """
            result = await self._db.query(query, {
                "relation": relation_type,
                "entity": f"entity:{entity_id}",
            })
        else:
            # Query all relationship tables
            query = """
                SELECT *, meta::tb(id) AS relation_type FROM relation
                WHERE in = $entity OR out = $entity
            """
            result = await self._db.query(query, {"entity": f"entity:{entity_id}"})

        return [self._parse_relationship(r) for r in self._extract_records(result)]

    async def search_entities(self, query: str, limit: int = 10) -> list[Entity]:
        await self._connect()
        surql = """
            SELECT * FROM entity
            WHERE string::lowercase(name) CONTAINS string::lowercase($query)
            LIMIT $limit
        """
        result = await self._db.query(surql, {"query": query, "limit": limit})
        return [self._parse_entity(r) for r in self._extract_records(result)]

    # --- Helpers ---

    @staticmethod
    def _extract_records(result) -> list[dict]:
        """Extract records from SurrealDB query result format."""
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "result" in first:
                return first["result"] or []
            return result
        return []

    @staticmethod
    def _parse_episode(data: dict) -> Episode:
        return Episode(
            id=str(data.get("id", "")).replace("episode:", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now(UTC)),
            conversation_id=data.get("conversation_id", ""),
            participants=data.get("participants", []),
            summary=data.get("summary", ""),
            actions_taken=data.get("actions_taken", []),
            outcome=data.get("outcome", ""),
            entities_referenced=data.get("entities_referenced", []),
            embedding=data.get("embedding", []),
            hat_name=data.get("hat_name", ""),
        )

    @staticmethod
    def _parse_entity(data: dict) -> Entity:
        return Entity(
            id=str(data.get("id", "")).replace("entity:", ""),
            entity_type=data.get("entity_type", ""),
            name=data.get("name", ""),
            attributes=data.get("attributes", {}),
            first_seen=datetime.fromisoformat(data["first_seen"]) if isinstance(data.get("first_seen"), str) else data.get("first_seen", datetime.now(UTC)),
            last_seen=datetime.fromisoformat(data["last_seen"]) if isinstance(data.get("last_seen"), str) else data.get("last_seen", datetime.now(UTC)),
            embedding=data.get("embedding", []),
        )

    @staticmethod
    def _parse_relationship(data: dict) -> Relationship:
        return Relationship(
            id=data.get("rel_id", str(data.get("id", ""))),
            from_entity=str(data.get("in", "")).replace("entity:", ""),
            relation=data.get("relation_type", data.get("relation", "")),
            to_entity=str(data.get("out", "")).replace("entity:", ""),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now(UTC)),
        )
