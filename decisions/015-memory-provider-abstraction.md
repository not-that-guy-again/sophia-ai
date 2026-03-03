# ADR-015: MemoryProvider abstraction interface

**Date:** 2025
**Status:** Accepted

## Context

Sophia already established the pattern of abstracting external dependencies behind interfaces with the LLM layer (ADR-009). `LLMProvider` defines `async complete()` and two implementations (Anthropic, Ollama) sit behind it. Pipeline code never knows which LLM backend is in use.

The memory system (ADR-012, ADR-013, ADR-014) introduces a second external dependency: SurrealDB. While the current decision is to use SurrealDB, the memory system should follow the same abstraction pattern for two reasons.

First, testability. The existing test suite runs with zero external dependencies using `MockLLMProvider`. Coupling tests directly to a running SurrealDB instance would break this property.

Second, interface clarity. Pipeline components need to ask "do I know this person?" and "what happened last time?", not construct database queries.

## Decision

The memory system is accessed through a `MemoryProvider` abstract interface. The interface defines the operations the pipeline needs:

- `store_episode(episode) -> str`: persist a conversation summary
- `recall_by_entity(entity_type, entity_id, limit) -> list[Episode]`: find episodes involving an entity
- `recall_similar(query_embedding, limit) -> list[Episode]`: semantic similarity search
- `recall_by_timerange(start, end, limit) -> list[Episode]`: temporal recall
- `store_entity(entity) -> str`: persist an entity record
- `store_relationship(from_entity, relation, to_entity, metadata) -> str`: create a graph edge
- `get_entity(entity_id) -> Entity | None`: retrieve a known entity
- `get_relationships(entity_id, relation_type) -> list[Relationship]`: traverse the graph
- `search_entities(query, limit) -> list[Entity]`: search entities by text or embedding

Three implementations:

- `SurrealMemoryProvider`: production implementation using SurrealDB
- `MockMemoryProvider`: in-memory dict-based implementation for unit tests
- Future implementations possible without pipeline changes

Pipeline components receive a `MemoryProvider` instance and call its methods. Data is exchanged using framework-owned dataclasses (`Episode`, `Entity`, `Relationship`), not database-specific models. A factory function `get_memory_provider(settings)` returns the appropriate implementation based on configuration.

## Consequences

**Positive:**
- Test suite retains its zero-external-dependency property via `MockMemoryProvider`
- Pipeline code is decoupled from SurrealDB specifics
- If SurrealDB proves unsuitable, the backend can be swapped by writing a new provider
- The interface documents exactly what the pipeline needs from memory, serving as a contract
- Consistent abstraction pattern with the LLM layer

**Negative:**
- The interface is a lowest-common-denominator contract; SurrealDB-specific features cannot be used without extending it
- An extra layer of indirection between the pipeline and the database
- `MockMemoryProvider` must be kept in sync with the real implementation's behavior
- Some powerful SurrealQL patterns (combining graph traversal with vector search in one query) may be awkward to express through generic methods
