# ADR-031: Tool-declared risk floors

**Date:** 2026-03  
**Status:** Accepted

## Context

The propose-then-evaluate pipeline (ADR-001) runs every tool-bearing proposal through consequence tree generation, four parallel evaluators, and risk classification before any action executes. This is the right design for ambiguous, context-dependent decisions where the pipeline's deliberation produces genuine signal.

It is the wrong design for decisions that are not ambiguous.

Some tools have risk profiles that are fixed by policy, not by context. `offer_free_item` is never appropriate — not for any customer, any order, any justification. `delete_customer_account` always requires human confirmation — not because the consequences are unclear, but because the policy is clear. For these tools, running consequence trees and evaluators is not deliberation; it is theater. The pipeline will reliably produce the same tier every time, but only after spending 5–6 LLM calls to get there.

The current mechanism for expressing risk intent on a tool is `authority_level` (`"agent"`, `"supervisor"`, `"admin"`). This was designed to communicate to the LLM during proposal generation which tools require elevated authorization. It is a hint to the proposer, not a hard machine-enforced constraint. Nothing in the pipeline reads `authority_level` and short-circuits based on it. The consequence engine runs regardless.

There is a related mechanism in the risk classifier: `catastrophic_harm` flags trigger automatic RED, and the Hat's `min_tier` can floor the overall pipeline output. But both of these fire *after* the consequence engine and evaluators have already run. They reduce harm from bad decisions, not cost from obvious ones.

The gap is: **no mechanism exists to declare a tool's minimum safe tier before the pipeline runs**, allowing obvious cases to exit early.

## Decision

Tools gain an optional `risk_floor` class attribute declaring the minimum risk tier any proposal involving that tool can ever produce:

```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict
    authority_level: str
    max_financial_impact: float | None = None
    risk_floor: str | None = None  # NEW: "GREEN" | "YELLOW" | "ORANGE" | "RED"
```

`risk_floor` is optional. A value of `None` means no floor — the pipeline decides as before. Valid string values are `"GREEN"`, `"YELLOW"`, `"ORANGE"`, and `"RED"`.

### Short-circuit behavior

A new check runs in `AgentLoop.process()` immediately after the parameter gate and before consequence tree generation. For each candidate in the proposal, the loop inspects the candidate's tool's `risk_floor`. The highest floor across all candidates becomes the **proposal floor**.

If the proposal floor is `RED`:
- Consequence engine does not run
- Evaluators do not run
- Risk classifier does not run
- A refusal `ExecutionResult` is built directly, identical in structure to a classifier-produced RED refusal
- `PipelineResult.risk_floor_short_circuit = True` is set
- The audit record includes `short_circuit_reason: "risk_floor"` and identifies which tool triggered it

If the proposal floor is `ORANGE` or `YELLOW`:
- The pipeline runs in full
- The classifier's output is floored to at least the declared tier (the same `min_tier` mechanism already used by the Hat's global `min_tier` field)
- Trees and evaluations are still generated and logged — they provide explanatory context even when the outcome is predetermined

`GREEN` floors are not enforced (a floor of the lowest tier has no effect) and exist only as an explicit documentation signal that a tool's author considered the question.

### Why RED alone short-circuits, and lower floors do not

A RED floor means the tool must never execute. There is nothing the consequence engine could find that would change this. The trees would add cost and latency to produce a predetermined refusal, and would potentially mislead the evaluators into thinking the question is open.

A YELLOW or ORANGE floor means the tool requires confirmation or escalation, but the specific request may still inform how that is communicated to the user. The consequence tree and evaluator reasoning are useful even when the tier is predetermined — they provide the explanation shown in YELLOW confirmation prompts and ORANGE escalation summaries. The floor ensures the tier cannot drop below the declared minimum; the pipeline provides the reasoning.

### Distinction from `authority_level`

These two attributes serve different systems and must not be conflated:

| | `authority_level` | `risk_floor` |
|---|---|---|
| **Read by** | LLM (proposer prompt) | Pipeline code (loop.py) |
| **Purpose** | Inform the LLM which tools require authorization | Enforce a minimum tier before evaluation |
| **Enforcement** | None — it is a hint | Hard — the loop short-circuits on RED |
| **When it acts** | Proposal generation | After parameter gate, before consequence engine |

A tool can have any combination: `authority_level = "agent"` with `risk_floor = "RED"` is valid and means "the proposer is not restricted from proposing this tool, but if proposed, the pipeline immediately refuses."

### Distinction from Hat `min_tier`

The Hat's `min_tier` field (in `hat.json`) is a global floor applied to all tools in the Hat, after full pipeline evaluation. `risk_floor` on a Tool is per-tool and fires before evaluation. They compose: a `risk_floor = "YELLOW"` tool in a Hat with `min_tier = "ORANGE"` produces ORANGE minimum (the higher of the two floors).

### Audit trail

Risk floor short-circuits are fully auditable per ADR-011. The `PipelineResult` gains:

```python
@dataclass
class PipelineResult:
    # ... existing fields ...
    risk_floor_short_circuit: bool = False           # NEW
    risk_floor_trigger_tool: str | None = None       # NEW — which tool's floor fired
    risk_floor_trigger_value: str | None = None      # NEW — what floor value was declared
```

The absence of consequence trees and evaluator results in the audit record is explained by these fields, not by missing data.

### Hat spec and CREATING_HATS documentation

`risk_floor` is added to the Tool interface section of `docs/HAT_SPEC.md` and `docs/CREATING_HATS.md`. Hat authors should set `risk_floor = "RED"` on any tool that must never execute autonomously and for which no context could ever justify execution. The guidance distinguishes this from `authority_level` and from policy-based restrictions expressed in `constraints.json`.

## Consequences

**Positive:**
- RED-floored proposals skip 5–6 LLM calls, reducing latency from ~6s to ~1.5s and cost by ~75% for those cases
- Hard policy prohibitions are enforced in code, not by evaluator reliability — the pipeline cannot accidentally approve a `risk_floor = "RED"` tool
- Hat authors have an explicit, documented mechanism for declaring "this tool is never safe" that is separate from LLM-facing hints
- The eval suite's free-item scenarios (T2-1, T2-2) short-circuit immediately, cutting their runtime from ~12 LLM calls to ~4
- The audit trail distinguishes "evaluated and refused" from "refused before evaluation" — a meaningful difference for operators reviewing decisions

**Negative:**
- Consequence trees and evaluator reasoning are not generated for RED-floored refusals, which means the audit record shows a leaner refusal than a fully-evaluated one. Operators may want to understand *why* a request was refused; the answer "because the tool declared risk_floor=RED" is correct but less explanatory than a full tree
- Hat authors must actively consider `risk_floor` for each tool they define. A tool without `risk_floor` set produces no floor; a tool that *should* have `risk_floor = "RED"` but doesn't will fall through to the full pipeline, which may or may not produce RED depending on the request
- The distinction between `risk_floor` and `authority_level` requires documentation and discipline; conflating them is a natural mistake
- `risk_floor = "GREEN"` has no runtime effect, which may confuse authors who expect it to do something
