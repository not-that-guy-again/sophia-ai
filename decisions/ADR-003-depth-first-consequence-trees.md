# ADR-003: Depth-first consequence trees

**Date:** 2025  
**Status:** Accepted

## Context

The propose-then-evaluate pipeline (ADR-001) requires a mechanism for simulating what could happen if a proposed action is executed. Without this simulation step, the evaluators would be scoring the action in a vacuum, assessing only whether it "sounds bad" rather than tracing through its actual consequences.

Human decision-making naturally involves imagining outcomes: "If I do X, then Y might happen, which could lead to Z." This chain-of-consequence reasoning is particularly important for actions that seem harmless on the surface but have harmful downstream effects (e.g., giving away a free product sets a precedent that leads to widespread abuse).

Alternatives considered:
- Flat list of pros and cons (rejected: misses cascading effects and second-order consequences)
- Breadth-first consequence exploration (rejected: generates many shallow branches without exploring deep causal chains)
- Monte Carlo simulation with random sampling (rejected: requires a formalized world model that does not exist)

## Decision

For each candidate action, the consequence engine generates a depth-first tree of consequences using an LLM call. Each node in the tree represents a possible outcome and contains:

- `description`: what happens
- `stakeholders_affected`: which parties from the Hat's stakeholder registry are impacted
- `probability`: likelihood of this outcome (0.0 to 1.0)
- `tangibility`: how concretely this is felt by affected parties (0.0 abstract to 1.0 directly felt)
- `harm_benefit`: severity on a scale from -1.0 (catastrophic harm) to 1.0 (major benefit)
- `children`: further consequences that follow from this outcome

The tree is generated to a configurable depth (default 3, configurable via `TREE_MAX_DEPTH`). The engine requires at least two root consequences: one optimistic path and one risk path. Terminal nodes (leaves) are marked explicitly.

The tree is analyzed with pure functions (no LLM): worst path, expected harm, catastrophic branch detection, and per-stakeholder impact aggregation.

## Consequences

**Positive:**
- Captures cascading and second-order effects that flat analysis misses
- The `tangibility` dimension distinguishes theoretical from felt harm, reducing false positives on abstract risks
- Stakeholder tagging on each node enables per-stakeholder impact analysis
- Pure analysis functions are deterministic and testable without LLM calls
- Tree depth is configurable per deployment and could be made dynamic based on financial impact

**Negative:**
- Tree quality depends entirely on the LLM's ability to imagine consequences accurately
- Deeper trees require more tokens and increase latency
- The LLM may generate plausible-sounding but unrealistic consequence chains
- Probability and tangibility scores from the LLM are subjective estimates, not calibrated probabilities
- The requirement for "one optimistic, one risk" root may lead to superficial risk paths (see ROADMAP: Red Team Node)
