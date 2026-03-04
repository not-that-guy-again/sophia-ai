# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Sophia project. Each ADR documents a significant architectural decision, including the context that led to it, the decision itself, and its consequences.

## Format

Each ADR follows a consistent structure:

- **Title:** Short name for the decision
- **Date:** When the decision was made or recorded
- **Status:** Accepted, Superseded, or Deprecated
- **Context:** The situation and forces that led to this decision
- **Decision:** What was decided
- **Consequences:** What follows from this decision, both positive and negative

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](ADR-001-propose-then-evaluate-pipeline.md) | Propose-then-evaluate pipeline | Accepted |
| [002](ADR-002-domain-agnostic-hat-system.md) | Domain-agnostic Hat system | Accepted |
| [003](ADR-003-depth-first-consequence-trees.md) | Depth-first consequence trees | Accepted |
| [004](ADR-004-four-independent-evaluators.md) | Four independent evaluators | Accepted |
| [005](ADR-005-tribal-veto-power.md) | Tribal evaluator veto power | Accepted |
| [006](ADR-006-deterministic-risk-classification.md) | Deterministic risk classification | Accepted |
| [007](ADR-007-four-tier-autonomy.md) | Four-tier autonomy model | Accepted |
| [008](ADR-008-uncertainty-bumps-up.md) | Uncertainty bumps up, never down | Accepted |
| [009](ADR-009-llm-provider-abstraction.md) | LLM provider abstraction | Accepted |
| [010](ADR-010-tool-scoping-per-hat.md) | Tool scoping per hat | Accepted |
| [011](ADR-011-audit-trail.md) | Immutable audit trail | Accepted |
| [012](ADR-012-memory-independent-from-hats.md) | Memory system independent from Hats | Accepted |
| [013](ADR-013-three-tier-memory-model.md) | Three-tier memory model | Accepted |
| [014](ADR-014-surrealdb-memory-database.md) | SurrealDB as the memory database | Accepted |
| [015](ADR-015-memory-provider-abstraction.md) | MemoryProvider abstraction interface | Accepted |
| [016](ADR-016-three-system-data-architecture.md) | Three-system data architecture | Accepted |
| [017](ADR-017-conversational-bypass.md) | Conversational bypass in the proposer | Accepted |
| [018](ADR-018-response-generation.md) | LLM-based response generation | Accepted |
| [019](ADR-019-constitution-based-identity.md) | Constitution-based identity and voice | Accepted |
| [020](ADR-020-preflight-parameter-gate.md) | Pre-flight parameter gate | Accepted |
| [021](ADR-021-preflight-acknowledgment.md) | Pre-flight acknowledgment | Accepted |
| [022](ADR-022-service-provider-abstraction.md) | Service provider abstraction layer | Accepted |
| [023](ADR-023-hat-scoped-backend-configuration.md) | Hat-scoped backend configuration | Accepted |
| [024](ADR-024-generic-rest-graphql-adapters.md) | Generic REST and GraphQL service adapters | Accepted |
| [025](ADR-025-webhook-event-ingestion.md) | Webhook event ingestion for proactive behavior | Accepted |