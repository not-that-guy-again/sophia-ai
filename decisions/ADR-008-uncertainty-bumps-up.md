# ADR-008: Uncertainty bumps up, never down

**Date:** 2025
**Status:** Accepted

## Context

The four evaluators (ADR-004) are independent and may produce conflicting scores. When evaluators disagree significantly, this could mean either that the situation is genuinely ambiguous or that one evaluator is seeing something the others missed. In either case, the system faces uncertainty about the true risk level.

The question is how to handle this uncertainty. A naive approach would be to trust the weighted average and let disagreement cancel out. A more conservative approach treats disagreement as a signal that the situation deserves more scrutiny.

In safety-critical systems, the standard practice is to fail safe: when uncertain, assume the worse case. An agent that occasionally asks for confirmation on safe actions (false positive) is far less harmful than one that occasionally executes dangerous actions (false negative).

## Decision

When two or more evaluators disagree by more than 0.8 (e.g., one scores +0.5 and another scores -0.4), the risk tier is bumped up one level. GREEN becomes YELLOW. YELLOW becomes ORANGE. ORANGE becomes RED. RED stays RED.

The bump is applied after the weighted score is mapped to a tier via thresholds, so it acts as a safety margin on top of the base classification. The bump direction is always toward more caution, never less.

This rule is part of the core safety logic in the risk classifier (ADR-006) and is not overridable by Hats.

## Consequences

**Positive:**
- Structurally enforces a conservative posture under uncertainty
- Prevents a situation where one evaluator's strong negative signal is silently averaged away
- The 0.8 disagreement threshold is wide enough to avoid triggering on minor differences
- Combined with the four-tier model (ADR-007), bumping up means "ask for confirmation" rather than "block entirely" in most cases

**Negative:**
- May increase false positives in domains where legitimate evaluator disagreement is common
- The 0.8 threshold and the "two or more evaluators" requirement are both somewhat arbitrary
- Hat creators cannot adjust this threshold even if their domain tolerates more evaluator disagreement
- Does not distinguish between "evaluators disagree about severity" and "evaluators are assessing different aspects"
