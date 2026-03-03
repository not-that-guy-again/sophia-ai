# ADR-007: Four-tier autonomy model

**Date:** 2025  
**Status:** Accepted

## Context

Most agent frameworks use a binary allow/block model: either the agent can do something or it cannot. This forces a choice between being too permissive (allowing risky actions) and too restrictive (blocking reasonable actions that happen to trigger a safety check).

Real-world decision-making is not binary. A junior employee can handle routine tasks independently, needs a manager's sign-off for medium-risk decisions, escalates high-risk situations to a specialist, and refuses to do things that are clearly wrong. The agent should behave the same way.

## Decision

The executor operates in four tiers, each with distinct behavior:

**GREEN:** Execute the action autonomously. The consequence tree and evaluation panel found acceptable risk. The tool is called, the result is returned, and no human involvement is needed.

**YELLOW:** Present the proposed action and its top consequence branches to the user for confirmation. The evaluation panel found moderate risk or edge-case concerns. The user can approve or decline. The action is not executed until confirmed.

**ORANGE:** Auto-escalate to a human agent. The evaluation panel found significant risk that exceeds the agent's authority. If an `escalate_to_human` tool is registered in the Hat, it is called automatically. If not, the user is told the request requires human review.

**RED:** Refuse the action with specific citations from the consequence tree explaining why. The evaluation panel found unacceptable risk (catastrophic harm flag, multiple severe evaluator scores, or a score below the RED threshold). No execution occurs. The refusal message includes the worst consequence branch and the override reason.

Tier assignment comes from the deterministic risk classifier (ADR-006). The executor does not make judgment calls about tier assignment.

## Consequences

**Positive:**
- Graduated response avoids the binary allow/block trap
- YELLOW tier preserves user agency on ambiguous decisions rather than blocking them outright
- ORANGE tier creates a natural handoff point to human operators
- RED refusals include specific reasoning from the consequence tree, not generic "I can't do that" messages
- Each tier is testable with known inputs

**Negative:**
- YELLOW tier adds friction to the user experience for moderate-risk actions
- ORANGE tier requires a human escalation path to be useful, which not all deployments will have
- The four tiers are fixed; some domains might benefit from more granularity (e.g., a "proceed with logging" tier between GREEN and YELLOW)
- Users may learn to always approve YELLOW actions without reading the consequences, reducing the tier's effectiveness over time
