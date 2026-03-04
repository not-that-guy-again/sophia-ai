# ADR-030: Situation evaluation for defensive proposals

**Date:** 2026-03
**Status:** Accepted

## Context

The first adversarial evaluation run (2026-03-04, `eval/results/findings.md`) revealed two critical structural failures:

1. **83% bypass rate.** The proposer selects `"converse"` on adversarial inputs because the LLM recognizes the request as illegitimate and declines conversationally. This bypasses the consequence engine, evaluation panel, risk classifier, and executor entirely. 15 of 18 adversarial turns produced no risk tier, no evaluator scores, and no formal audit record.

2. **Evaluating the wrong thing.** On the 3 turns where the pipeline ran, it evaluated the agent's proposed response (e.g., `escalate_to_human`) rather than the incoming request. A legal threat scored GREEN because escalation is a safe action. The pipeline answered "is my response safe?" instead of "is this situation dangerous?"

These are structural issues, not weight or prompt problems. The pipeline has one question — "Is the action I am about to take safe?" — when it needs two:

- "Is the situation I am in dangerous?" (evaluated against the requested action)
- "Is the response I am about to give appropriate?" (evaluated against the agent's proposed action)

ADR-017 established the conversational bypass for genuinely non-actionable inputs (greetings, chitchat, policy questions). The bypass is correct for those cases. The problem is that adversarial requests — which map to real tools but which the proposer declines to act on — take the same bypass path as greetings, receiving no formal evaluation.

## Decision

### Dual-tree approach

Introduce a **situation tree** — a consequence tree generated from the user's original intent, not from the proposer's candidate. The situation tree asks: *"What would happen if the requested action were executed?"*

A `SituationCandidate` dataclass represents the user's request:

```python
@dataclass
class SituationCandidate:
    action_requested: str      # from intent
    parameters: dict           # from intent
    reasoning: str = "Evaluating the consequences of the user's request if fulfilled"
    expected_outcome: str = "The user's requested action is executed as asked"

    @classmethod
    def from_intent(cls, intent) -> "SituationCandidate":
        return cls(
            action_requested=intent.action_requested,
            parameters=intent.parameters or {},
        )
```

`ConsequenceEngine.analyze_situation()` generates a consequence tree for the `SituationCandidate` using a prompt framing that evaluates the request, not the response. The tree is evaluated by all four evaluators and classified by the risk classifier, producing a `SituationRiskClassification`.

### When situation evaluation triggers

Situation evaluation runs when **all** of the following are true:

- The top candidate is a **defensive proposal**: `"converse"` or `"escalate_to_human"`
- `intent.action_requested` is not `"general_inquiry"`
- The `"converse"` candidate was NOT synthesized by the parameter gate (ADR-020) — a synthesized converse is a clarifying question, not an adversarial decline

Situation evaluation does **not** run when:

- The intent is `"general_inquiry"` (greetings, chitchat, policy questions — genuinely non-actionable)
- The proposer proposed a real tool action (the response tree already covers the situation)
- The parameter gate synthesized a `"converse"` candidate due to missing parameters

### How situation and response tiers combine

The final tier is `max(situation_tier, response_tier)`:

| Situation tier | Response tier | Final tier |
|---------------|---------------|------------|
| RED           | GREEN         | RED        |
| ORANGE        | GREEN         | ORANGE     |
| YELLOW        | GREEN         | YELLOW     |
| GREEN         | GREEN         | GREEN      |

The response generator receives the situation tier so it can shape the refusal — a RED situation produces a firmer decline than a YELLOW one.

### Evaluator context

When evaluators receive a situation tree, their `EvaluationContext` includes `evaluation_mode="situation"` and the original user message. The evaluator system prompts are amended when in situation mode to clarify they are evaluating the danger of the request, not the safety of the agent's response.

### Pipeline flow

**Before:**
```
Proposer → converse? → _handle_converse() → response generator (GREEN hardcoded)
```

**After:**
```
Proposer → defensive? → Is intent action_requested (not general_inquiry)?
                          ├── YES → Situation tree → Evaluators → Classifier
                          │         → _handle_converse_with_evaluation()
                          └── NO  → _handle_converse() (unchanged, ADR-017)
```

### PipelineResult additions

```python
@dataclass
class PipelineResult:
    # ... existing fields ...
    situation_tree: ConsequenceTree | None = None
    situation_evaluation_results: list[EvaluatorResult] = field(default_factory=list)
    situation_risk_classification: RiskClassification | None = None
```

### Amendment to ADR-017

The proposer prompt gains an explicit constraint: do NOT use `"converse"` to decline a request that maps to an available tool. If the user requests a refund, discount, free item, or any action that corresponds to a tool — even if the agent believes the request should be refused — propose the relevant tool as a candidate. The evaluation pipeline decides whether the action is appropriate. The proposer's role is to identify what is being requested, not to pre-approve it.

Exception: if the proposer is asking for a missing required parameter, `"converse"` remains appropriate.

This reduces the bypass rate by redirecting adversarial-but-tool-mapped requests into the standard evaluation pipeline.

### What does NOT change

- Genuinely conversational inputs (greetings, policy questions, chitchat) continue to bypass the pipeline entirely per ADR-017.
- The `"converse"` response is still the correct output for adversarial inputs. The agent still declines. The change is that the refusal is now backed by a formal risk tier.
- The parameter gate (ADR-020) runs before the bypass check. Synthesized `"converse"` due to missing parameters does not trigger situation evaluation.
- Evaluator weights and thresholds are unchanged.

## Consequences

**Positive:**
- Adversarial requests produce formal risk tiers, evaluator scores, and audit records regardless of whether the agent complies.
- The audit trail captures both the situation danger and the response safety, giving operators full visibility.
- The response generator can shape refusal language based on the situation tier — firmer for RED, clearer for ORANGE.
- The `[SITUATION]` prefix in tool_name makes situation trees identifiable in audit records without a schema change.
- The proposer prompt change independently reduces bypass rate by redirecting tool-mapped adversarial requests into the standard pipeline.

**Negative:**
- Situation evaluation adds LLM calls (consequence tree + 4 evaluators) to the adversarial response path. This increases latency and cost for adversarial inputs, which is acceptable since safety is the priority.
- The dual-tree approach adds complexity to `PipelineResult` and the audit record. Consumers of the pipeline output must handle the new fields.
- The proposer prompt constraint may cause the LLM to propose tools for genuinely ambiguous requests that would have been better handled conversationally. The parameter gate provides a safety net: if required parameters are missing, the converse fallback still activates.
- The `evaluation_mode` field in `EvaluationContext` is a simple string rather than a typed enum, which could lead to invalid values. This is acceptable for the current scope.
