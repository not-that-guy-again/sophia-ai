# ADR-005: Tribal evaluator veto power

**Date:** 2025  
**Status:** Accepted

## Context

The four evaluators (ADR-004) produce independent scores that are aggregated by the risk classifier. In a pure weighted-average system, a strongly negative tribal score could be offset by positive scores from the other three evaluators. For example, giving away a free PS5 might score well on self-interest (customer is happy, good review), neutral on authority (the customer is who they say they are), and only mildly negative on domain (it bends but does not break a policy). Only the tribal evaluator sees the full picture: this harms employees whose livelihoods depend on the business, is unfair to paying customers, and sets a precedent that enables widespread abuse.

The framework's core philosophy is that tribal harm overrides self-interest. The AI agent exists within a human ecosystem. Its operational needs (compute, storage, billing, power) depend on humans being healthy, employed, and trusting the system. Actions that harm the tribe ultimately harm the agent, even if the immediate self-interest signal is positive.

This principle needs to be enforced structurally, not just through prompt engineering.

## Decision

The tribal evaluator has veto power. When it flags an action as catastrophic harm (score at or below -0.8), it sets a `catastrophic_harm` flag. The risk classifier treats this flag as an automatic override to RED tier, regardless of the other three evaluators' scores.

The -0.8 threshold is configured globally via `CATASTROPHIC_THRESHOLD` and is a core safety parameter, not overridable by Hats. This prevents a Hat from loosening the catastrophic harm standard.

Additionally, the tribal evaluator's code enforces the flag: if the LLM returns a score at or below -0.8 but forgets to include `catastrophic_harm` in its flags, the evaluator adds it automatically. If the LLM already included it, no duplicate is added.

## Consequences

**Positive:**
- Structural enforcement of the "tribal harm overrides self-interest" principle
- Cannot be bypassed by prompt injection or evaluator tuning in Hats
- The threshold is a single, auditable configuration value
- Automatic flag injection means the safety mechanism does not depend on the LLM remembering to flag correctly

**Negative:**
- A single evaluator can block any action, which could produce false positives if the tribal evaluator is poorly calibrated
- The -0.8 threshold is somewhat arbitrary and may need empirical tuning
- Hat creators cannot adjust the catastrophic threshold even in domains where the default may be too sensitive or not sensitive enough
- The veto is binary: once triggered, there is no graduated response (it jumps straight to RED)
