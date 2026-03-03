# ADR-006: Deterministic risk classification

**Date:** 2025  
**Status:** Accepted

## Context

The evaluation panel (ADR-004) produces four independent scores, each with flags and confidence levels. These need to be aggregated into a single risk tier that determines what the executor does. This aggregation step could itself be an LLM call ("look at these four scores and decide what tier this is"), but that introduces another source of nondeterminism and makes the system harder to reason about and audit.

The risk classifier is the last gate before execution. It must be predictable, explainable, and testable. Given the same four evaluator results, it should always produce the same tier.

## Decision

The risk classifier is implemented as deterministic code with no LLM calls. It takes four `EvaluatorResult` objects and the Hat's evaluator configuration, then applies the following logic:

1. Compute a weighted score from individual evaluator scores using weights from the Hat (defaults: tribal 0.40, domain 0.25, self-interest 0.20, authority 0.15).

2. Apply override rules (core safety, not Hat-configurable):
   - Any `catastrophic_harm` flag in any evaluator's flags triggers automatic RED
   - Three or more evaluators scoring below -0.5 triggers automatic RED
   - Two or more evaluators disagreeing by more than 0.8 bumps the tier up one level

3. Map the weighted score to a tier using thresholds from the Hat config (defaults: above -0.1 is GREEN, -0.1 to -0.4 is YELLOW, -0.4 to -0.7 is ORANGE, below -0.7 is RED).

4. Apply the disagreement bump if triggered (bumps up, never down).

5. Select the recommended action based on the final tier.

## Consequences

**Positive:**
- Given identical inputs, the classifier always produces the same output
- Override rules enforce core safety invariants that Hats cannot weaken
- The classifier can be exhaustively tested with known score combinations
- Decision reasoning is fully traceable without interpreting LLM output
- No additional LLM cost or latency at the classification step

**Negative:**
- The weighted-average approach can mask extreme signals if the weight is low (e.g., authority at 0.15 means a score of -1.0 only contributes -0.15 to the weighted total)
- Threshold boundaries are sharp cutoffs; a score of -0.39 is GREEN while -0.41 is YELLOW, with no gradual transition
- The override rules are hardcoded and may not suit all future domains
- Confidence values from evaluators are available but currently unused in tier calculation
