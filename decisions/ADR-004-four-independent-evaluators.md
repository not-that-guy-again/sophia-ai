# ADR-004: Four independent evaluators

**Date:** 2025  
**Status:** Accepted

## Context

The consequence tree (ADR-003) provides a simulation of what could happen. Something still needs to judge whether those outcomes are acceptable. A single evaluator prompt risks conflating different concerns: is this safe for people? Does it follow the rules? Does the requester have authority? Is this good for the system's reputation?

When these concerns are combined into a single prompt, the LLM tends to average them together, producing moderate scores that mask strong signals in any one dimension. A catastrophic tribal harm signal can be diluted by a positive self-interest signal if both are assessed in the same prompt.

Alternatives considered:
- Single evaluator with a comprehensive prompt (rejected: conflates orthogonal concerns)
- Two evaluators, harm and benefit (rejected: misses authority and domain compliance dimensions)
- N evaluators where N is configurable (rejected: adds complexity without clear value beyond four)

## Decision

Four independent evaluators run in parallel via `asyncio.gather`, each assessing the consequence tree from a distinct perspective:

1. **Self-Interest Evaluator:** "Does this action keep the system operational and trusted?" Evaluates trust preservation, operational continuity, reputation impact, and manipulation resistance.

2. **Tribal Evaluator:** "Does this action cause tangible, felt harm to real people?" Evaluates tangibility of harm, scale, reversibility, precedent, and fairness. Has veto power (see ADR-005).

3. **Domain Evaluator:** "Does this action comply with domain rules and constraints?" Evaluates policy compliance, financial limits, process adherence, and precedent. This is the most Hat-specific evaluator.

4. **Authority Evaluator:** "Does the requestor have standing to request this action?" Evaluates identity verification, role-based access, authority matching, and social engineering resistance.

Each evaluator receives the consequence tree, the Hat's configuration (constraints, stakeholders), and its own Hat-specific prompt fragment. Each returns an `EvaluatorResult` with a score (-1.0 to 1.0), confidence (0.0 to 1.0), flags, reasoning, and key concerns.

Evaluator weights default to: tribal 0.40, domain 0.25, self-interest 0.20, authority 0.15. Hats can override these weights.

## Consequences

**Positive:**
- Each evaluator focuses on one dimension, producing clearer and more extreme signals when warranted
- Parallel execution keeps latency manageable (all four run simultaneously)
- Independent evaluation means one evaluator's reasoning does not influence another's
- Custom flags per evaluator enable domain-specific risk signals
- Hat-specific prompt fragments allow deep per-domain customization of each evaluator

**Negative:**
- Four LLM calls per evaluation (on top of the consequence tree call and the proposer call) increase cost
- Evaluators may produce contradictory signals that the risk classifier must reconcile
- The four-evaluator structure is fixed; adding a fifth evaluator requires core code changes
- Each evaluator independently interprets the same consequence tree, which may lead to inconsistent readings of the same data
