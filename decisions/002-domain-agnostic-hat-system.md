# ADR-002: Domain-agnostic Hat system

**Date:** 2025  
**Status:** Accepted

## Context

Sophia's consequence engine, evaluation panel, and risk classifier are general-purpose mechanisms. They work by asking "what could happen?" and "is that acceptable?" regardless of the domain. However, the definition of "acceptable" varies enormously by domain. A customer service agent and a financial advisor operate under completely different rules, serve different stakeholders, and carry different risk profiles.

The framework needs to support multiple domains without hardcoding any domain-specific logic into the core. At the same time, domain-specific behavior (tools, constraints, stakeholders, evaluator tuning) must be deeply integrated into the pipeline, not bolted on as an afterthought.

Alternatives considered:
- Hardcoding domain logic into the core (rejected: not extensible)
- Configuration files only, no code (rejected: tools require executable logic)
- A full plugin system with hooks at every pipeline stage (rejected: too complex for the current stage)

## Decision

Domain expertise is provided through Hats, which are self-contained pluggable modules. A Hat is a directory containing a manifest (`hat.json`), tool implementations, constraints, stakeholder definitions, evaluator configuration overrides, and prompt fragments for each pipeline stage.

When a Hat is equipped, the framework loads its components and injects them into the pipeline. The core framework never assumes what domain it is operating in. All domain-specific behavior comes from the Hat.

A Hat contains:
- `hat.json`: manifest with name, tools list, default evaluator weights, risk thresholds
- `tools/`: Python tool implementations
- `constraints.json`: domain rules and policies (free-form structure)
- `stakeholders.json`: parties affected by actions, with harm sensitivity and weight
- `evaluator_config.json`: weight overrides, custom flags, threshold overrides
- `prompts/`: text fragments appended to core prompts at each pipeline stage

In v1, Sophia wears one Hat at a time. The Hat is loaded at startup or switched via API.

## Consequences

**Positive:**
- The core framework stays domain-agnostic and testable without domain dependencies
- New domains can be added by creating a Hat directory without modifying core code
- Each Hat is self-contained and can be versioned, tested, and distributed independently
- Evaluator weights and risk thresholds can be tuned per domain without affecting other domains
- Prompt fragments allow deep customization of LLM behavior at every pipeline stage

**Negative:**
- Hat creators must understand the full pipeline to write effective prompt fragments and evaluator configs
- The Hat directory structure has many files, which can be intimidating for new contributors
- One-hat-at-a-time limits use cases that span multiple domains
- The free-form `constraints.json` structure means there is no schema enforcement on domain rules
