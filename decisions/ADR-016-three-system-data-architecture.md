# ADR-016: Three-system data architecture

**Date:** 2025
**Status:** Accepted

## Context

Sophia has three categories of persistent data, each with different access patterns, retention policies, and scaling characteristics:

1. **Domain configuration:** constraints, stakeholders, evaluator weights, prompt fragments, tool definitions. Read at hat equip time, rarely changes, human-authored, should be version-controlled.

2. **Experiential knowledge:** conversation summaries, entity records, relationship graphs, semantic embeddings. Written after every conversation, queried at the start of every interaction, grows continuously, requires structured lookup + vector search + graph traversal.

3. **Decision records:** pipeline traces, evaluator results, risk classifications, execution outcomes, human feedback. Append-only, queried for audit and analysis, relational in nature, may have compliance and retention requirements.

An early design considered using SQLite for configuration and runtime settings alongside SurrealDB. However, every item that would go into a settings database (current hat, authority limits, directives) is already owned by the Hat system through flat files loaded at equip time. Duplicating this into a database creates two sources of truth with no clear benefit.

## Decision

Data is split across three systems, each owning one category:

**Hat files on disk** own domain configuration. `hat.json`, `constraints.json`, `stakeholders.json`, `evaluator_config.json`, and `prompts/` are the canonical source for everything about how the agent behaves in a given role. These files are loaded into memory when a Hat is equipped. They are human-editable, version-controllable via git, and require no database.

**SurrealDB** owns experiential knowledge (the memory system, ADR-012 through ADR-015). Conversation episodes, entities, relationships, and embeddings live here. This is the only system that handles vector search and graph traversal. Accessed through the `MemoryProvider` interface.

**Audit database** owns decision records (ADR-011). Pipeline traces, evaluator results, outcome tracking, and feedback are stored here. This workload is append-only and relational, making it a natural fit for PostgreSQL in production or SQLite during development. Accessed through the audit subsystem (Phase 5). The existing `DATABASE_URL` configuration variable points to this database.

No system stores data that belongs to another. The Hat system does not write to SurrealDB. The memory system does not read Hat config files. The audit system does not store entity relationships.

## Consequences

**Positive:**
- Each system is optimized for its access pattern (file read, multi-model query, append-only write)
- No single database becomes a bottleneck for unrelated workloads
- Hat configuration stays in git where it can be reviewed, diffed, and rolled back
- The memory database can scale independently from the audit database
- Clear ownership means no ambiguity about where a piece of data lives or which system is authoritative

**Negative:**
- Three data systems means three things to operate, monitor, and back up in production
- Cross-system queries are not possible (e.g., "show me the consequence tree for the last conversation with Abbie" requires querying both audit and memory)
- Developers must understand which system owns which data, adding onboarding complexity
- Local development requires running SurrealDB as a separate process (or in embedded/in-memory mode)
- Data consistency across systems is eventual at best; there is no cross-system transaction
