# ADR-011: Immutable audit trail

**Date:** 2025
**Status:** Accepted

## Context

Sophia's pipeline produces intermediate artifacts for every decision: parsed intent, proposed candidates, consequence trees, evaluator results, risk classification, and execution result. If this data is not captured, there is no way to understand why the agent made a particular decision after the fact.

## Decision

Every pipeline run produces an immutable audit record containing the full decision trail. Records are append-only and cannot be modified or deleted through the API.

The audit schema includes: decisions (top-level record per run), decision_proposals (candidate actions), decision_trees (serialized consequence trees), decision_evaluations (per-evaluator results), decision_outcomes (reported actual outcomes), feedback (human corrections), and hat_configs (versioned snapshots at decision time).

The API exposes read-only query endpoints with filtering by hat, tier, date range, and tool. PipelineResult.to_dict() already serializes the full trail. Hat configuration is snapshotted so audit records remain interpretable even if the Hat is later modified.

## Consequences

Positive:
- Full decision trail enables post-hoc analysis of agent behavior
- Append-only design prevents tampering with historical records
- Outcome tracking enables empirical evaluator tuning over time
- Human overrides on YELLOW/ORANGE tiers create a feedback dataset
- Hat config snapshots ensure records remain interpretable across versions

Negative:
- Storage grows with every pipeline run and needs a retention policy at scale
- Serialized trees and reasoning are verbose and may require compression
- Immutability means incorrect records cannot be corrected, only annotated
- Audit records contain user messages and may need data retention policies
