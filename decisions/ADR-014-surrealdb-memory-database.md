# ADR-014: SurrealDB as the memory database

**Date:** 2025
**Status:** Accepted

## Context

The three-tier memory model (ADR-013) requires three distinct query patterns against the same data: structured lookups ("find all conversations with Abbie"), semantic similarity searches ("find situations similar to this one"), and relationship traversal ("Abbie owns Waldo, Abbie purchased a Litter Robot, three other customers reported the same motor issue").

A relational database like PostgreSQL can handle structured lookups natively and semantic search via the pgvector extension, but relationship traversal requires join tables and recursive CTEs that become unwieldy as the graph grows. More importantly, pgvector is a bolt-on. The query planner is optimized for relational workloads, and vector similarity search at scale competes with those optimizations rather than complementing them. For a large deployment, this creates a real risk of long-running queries as the extensions fight the core engine's assumptions.

A pure vector database (ChromaDB, Qdrant) handles semantic search well but forces structured lookups and relationship traversal through workarounds. A pure graph database (Neo4j) handles relationships natively but bolts on vector search.

Sophia's memory system needs all three patterns as first-class operations, not one native pattern with two bolt-ons.

Alternatives considered:
- PostgreSQL + pgvector (rejected: bolt-on vector search, no native graph traversal, performance risk at scale)
- PostgreSQL + pgvector + Apache AGE (rejected: two extensions on one engine, compounding bolt-on risks)
- MongoDB + ChromaDB hybrid (rejected: two databases to operate, no native graph support in either)
- Neo4j (rejected: strong graph, weak vector search, overkill for structured lookups)

## Decision

SurrealDB is the database for Sophia's memory system. It is a multi-model database that supports document storage, graph relationships (with native `RELATE` syntax), and vector search in a single engine. All three query patterns required by the memory model are native operations, not extensions.

SurrealDB configuration is managed through environment variables:

- `SURREALDB_URL`: connection endpoint (default `ws://localhost:8529`)
- `SURREALDB_USER`: authentication user
- `SURREALDB_PASS`: authentication password
- `SURREALDB_NAMESPACE`: logical namespace (default `sophia`)
- `SURREALDB_DATABASE`: database name (default `memory`)

For local development, SurrealDB runs in-memory mode (`surreal start memory`) with no persistence, or file-backed mode (`surreal start file:sophia.db`) for persistence across restarts. For production, SurrealDB runs as a separate service (Docker or standalone binary).

SurrealDB is used exclusively for the memory system. The audit log (ADR-011) uses a separate database appropriate for its append-only relational workload.

## Consequences

**Positive:**
- All three query patterns (structured, vector, graph) are native operations, not extensions
- Single database to operate, back up, and monitor for the memory system
- SurrealQL is expressive enough to combine structured filters with graph traversal in a single query
- Native `RELATE` syntax models entity relationships directly rather than through join tables
- In-memory mode provides zero-setup local development
- Embedded mode available for self-contained integration tests without external processes

**Negative:**
- SurrealDB is young (1.0 shipped September 2023, 2.0 in late 2024) with less battle-testing than mature alternatives
- The Python SDK is less mature than the Rust core or JavaScript SDK; some SurrealQL features may not be fully exposed
- Adds a new service to the deployment topology (Sophia was previously a single Python process)
- The team and community are smaller than PostgreSQL or MongoDB, meaning fewer Stack Overflow answers and third-party tools
- If SurrealDB introduces breaking changes in a future major version, migration effort falls on the Sophia project
- Operational tooling (monitoring, backup, replication) is less established than for mature databases
