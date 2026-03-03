# ADR-019: Pre-flight parameter gate

**Date:** 2026-03
**Status:** Proposed

## Context

ADR-017 introduced conversational bypass for non-actionable messages. When the proposer's top candidate is `converse`, the pipeline skips consequence tree generation, evaluation, and risk classification entirely. This works well for greetings and chitchat.

However, a structurally similar problem remains for actionable messages where a tool IS needed but a prerequisite is missing. The proposer recognizes the gap — it includes the missing information in its reasoning — but still ranks the tool call as the top candidate with placeholder parameter values.

This was observed in production on 2026-03-03. A customer asked about a missing delivery without providing an order number. The proposer generated two candidates:

1. `check_order_status` with `order_id: "UNKNOWN"` — reasoning explicitly noted "we need the order ID from the customer first"
2. `converse` — reasoning noted "we don't yet have the order ID, which is required to look up any order details"

Because `check_order_status` was ranked first, the full pipeline ran: consequence trees for both candidates (37 nodes total across two trees), four evaluators in parallel, and risk classification. This consumed approximately 90 seconds of wall time and 8 LLM calls. The consequence engine itself predicted the API call had a 95% probability of failure. The evaluators flagged `invalid_parameter_usage`, `unverified_order`, and `policy_compliance_risk`. The classifier landed on YELLOW.

The final response was correct — Sophia asked the customer for their order number — but the path to get there was wasteful and slow. A human agent would not mentally simulate 17 failure scenarios before asking "what's your order number?"

The information needed to short-circuit this decision was already present before the consequence engine ran. The tool's parameter schema declares `order_id` as required. The proposer filled it with the literal string `"UNKNOWN"`. No LLM inference is needed to determine this candidate cannot execute successfully.

## Decision

A deterministic parameter validation step runs between the proposer and the consequence engine. For each candidate (excluding `converse`), the gate checks the candidate's parameters against the tool's JSON Schema definition, which is already available in the `ToolRegistry`.

The gate applies two checks:

**1. Missing required parameters.** If the tool schema lists a field in `required` and the candidate's parameters omit it or set it to `null`, the candidate fails validation.

**2. Placeholder detection.** If a required parameter's value matches a known placeholder pattern, the candidate fails validation. The initial placeholder patterns are:

- Exact string matches (case-insensitive): `"UNKNOWN"`, `"TBD"`, `"N/A"`, `"NONE"`, `"PLACEHOLDER"`, `"TODO"`, `"?"`, `"???"`
- Empty or whitespace-only strings for `string`-typed parameters

This list is deliberately conservative. It covers the patterns observed in proposer output without attempting to be exhaustive. Hats may extend the placeholder list via a new optional field in `hat.json`.

**When a candidate fails validation:**

- If all non-`converse` candidates fail and a `converse` candidate exists in the proposal, the `converse` candidate is promoted to top position and the pipeline follows the existing conversational bypass path (ADR-017).
- If all non-`converse` candidates fail and no `converse` candidate exists, the gate synthesizes one. The synthesized candidate's reasoning is constructed from the validation failures (e.g., `"check_order_status requires order_id but received placeholder value 'UNKNOWN'. Asking the customer for the missing information."`). The pipeline then follows the conversational bypass path.
- If at least one non-`converse` candidate passes validation, the pipeline continues normally with passing candidates only. Failed candidates are removed from the proposal before consequence tree generation, saving LLM calls proportional to the number of removed candidates.

**What the gate does NOT do:**

- Semantic validation. It does not judge whether `order_id: "ABC123"` is a real order — that's the tool's job at execution time.
- Type coercion. It does not attempt to fix parameter types. A string where an integer is expected is not the gate's problem; the consequence engine and evaluators should handle type mismatches that might still produce meaningful outcomes.
- Override the proposer's ranking among passing candidates. If two candidates pass validation, their original ordering is preserved.

The gate produces a `ParameterValidationResult` for each candidate, which is included in the `PipelineResult` and audit record regardless of pass/fail. This preserves the auditability principle (ADR-011) — the record shows what was proposed, what failed validation, and why.

### Implementation location

The gate is implemented as `sophia/core/parameter_gate.py` and called from `sophia/core/loop.py` after the proposer returns and before the conversational bypass check. The existing bypass check (ADR-017) is adjusted to run after the parameter gate, so that gate-promoted `converse` candidates follow the same bypass path as proposer-originated ones.

### Pipeline flow (revised)

```
Proposer
    │
    ▼
Parameter Gate  ◄── NEW: validate each candidate's params against tool schema
    │
    ├── All candidates pass → continue to Consequence Engine
    ├── Some fail → remove failed, continue with survivors
    └── All fail → promote/synthesize converse → Conversational Bypass
```

### Hat extension point

Hats may add a `placeholder_patterns` field to `hat.json`:

```json
{
  "placeholder_patterns": ["PENDING", "UNSET", "0000"]
}
```

These are merged with the core placeholder list. This allows domain-specific sentinel values to be caught (e.g., a financial hat might flag `"0.00"` for `amount` fields).

## Consequences

**Positive:**
- Eliminates consequence tree generation, evaluation, and risk classification for proposals that cannot execute — saving 6–8 LLM calls and significant latency per occurrence.
- The validation is deterministic and adds zero LLM cost. It runs against data already in memory (tool schemas and candidate parameters).
- Failed candidates and their validation results are fully auditable, preserving ADR-011.
- The response to the customer arrives faster, which is the original goal of making Sophia's behavior more human. A human would ask for the order number immediately.
- Hats can extend placeholder detection for domain-specific sentinel values without modifying core code.
- The gate composes cleanly with the existing conversational bypass (ADR-017) rather than replacing it. Proposer-originated `converse` candidates still bypass the gate entirely.

**Negative:**
- The placeholder list is a heuristic. A proposer that uses `"customer_order"` or `"the one from last week"` as a placeholder would not be caught. The list will need to grow based on observed proposer behavior.
- Removing failed candidates changes the set of candidates the consequence engine sees. If a failed candidate would have been informative to the evaluators as a contrast (e.g., "here's what would happen if we tried this with bad data"), that signal is lost.
- Adds a new step to the pipeline that must be maintained and tested. However, it is purely deterministic and does not introduce LLM nondeterminism.
- The synthesized `converse` candidate (when no proposer-originated one exists) has machine-generated reasoning rather than LLM-generated reasoning, which may produce slightly less natural responses from the response generator.
- There is a theoretical risk that the gate could filter a candidate that would have passed at execution time (e.g., a tool that accepts `"UNKNOWN"` as a literal valid input). This is mitigated by keeping the placeholder list conservative and allowing Hats to customize it.
