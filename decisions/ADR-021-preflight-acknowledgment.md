# ADR-021: Pre-flight acknowledgment ("mirror on the elevator door")

**Date:** 2026-03
**Status:** Accepted

## Context

The propose-then-evaluate pipeline (ADR-001) trades latency for safety. A single user message that triggers tool execution passes through the consequence engine (1 LLM call per candidate), four evaluators in parallel (4 LLM calls), risk classification, and tiered execution before the user sees a response. In the 2026-03-03 audit, a customer who provided an email and order number waited through 2 consequence trees (37 nodes), 4 evaluator runs, and risk classification before receiving a response — even though the response was a straightforward order lookup result.

ADR-017 (conversational bypass) and ADR-019 (parameter gate) address the cases where the pipeline *shouldn't run at all*. This ADR addresses the remaining case: the pipeline *should* run, but the user shouldn't have to stare at a bouncing-dot animation for the full duration.

The UX principle is sometimes called "mirror on the elevator door" — people tolerate waits better when they receive an immediate signal that their input was received and work has begun. The chat UI already has a stage-label indicator (`stageLabel(currentStage)` in `ChatWindow.tsx`), but it only shows system-internal phase names. A brief natural-language acknowledgment from Sophia — "Let me look up order 123456 for you" — would make the delay feel shorter and more human.

A human agent does this automatically. When a customer says "my order is 123456 and my email is brent@example.com," the agent says "got it, let me pull that up" *before* they start typing the order number into the system. The acknowledgment and the work happen concurrently.

### Why not just make the pipeline faster?

Consequence tree generation and multi-evaluator scoring are inherently multi-call LLM operations. They can be optimized (tree caching, model selection, parallelization), but they will never be instant. The acknowledgment is complementary to performance optimization, not a substitute for it.

### Why not use an LLM call for the acknowledgment?

Adding an LLM call to generate a natural-sounding ack would itself add 1–3 seconds of latency at the exact moment we're trying to *reduce* perceived latency. The acknowledgment must be near-instantaneous, which means it must be deterministic.

## Decision

After the proposer returns candidates and the parameter gate validates them (ADR-019), but before the consequence engine begins, the loop emits a **preflight acknowledgment** via WebSocket. This acknowledgment is a short, natural-language message constructed from templates and slot-filled with data already available in the pipeline: the intent's `action_requested`, `target`, and `parameters`.

### Pipeline flow (revised)

```
Proposer
    │
    ▼
Parameter Gate (ADR-019)
    │
    ├── All fail → Conversational Bypass (no ack needed, response is fast)
    │
    ▼
Ack Decision
    │
    ├── Skip conditions met → proceed silently to Consequence Engine
    │
    ▼
Emit preflight_ack via WebSocket     ← NEW
    │
    ▼ (concurrent from user's perspective)
Consequence Engine → Evaluators → Risk Classifier → Executor → Response
```

### When the acknowledgment fires

The ack fires when ALL of the following are true:

1. **At least one non-`converse` candidate survived the parameter gate.** If the gate redirected everything to converse, the bypass path is fast enough that no ack is needed.
2. **The top surviving candidate's tool has `authority_level` of `"agent"`.** Tools at `"supervisor"` or `"admin"` authority represent sensitive operations (large refunds, account changes, escalations with financial impact). For these, Sophia should not signal "working on it" before the evaluation panel has assessed risk. The user experience for high-authority actions should be: wait → considered response, not: "on it!" → wait → "actually, I can't do that."
3. **No candidate tool has `max_financial_impact` above the hat's `ack_financial_ceiling`.** Default ceiling: `0.0` (tools with any declared financial impact skip the ack). Hats can raise this. The customer-service hat might set it to `50.00` to allow acks for small refund lookups while suppressing them for large refund processing.

If any condition fails, the pipeline proceeds without an ack — the user sees the existing stage-label animation until the full response arrives.

### What the acknowledgment contains

The ack is built from **templates**, not LLM calls. Each hat may define an `ack_templates` section in `hat.json`:

```json
{
  "ack_templates": {
    "order_status": [
      "Let me pull up order {order_id} for you.",
      "Checking on that order now — one moment.",
      "Got it, looking up {order_id}."
    ],
    "product_inquiry": [
      "Let me check on that for you.",
      "One moment while I look into that."
    ],
    "_default": [
      "One moment while I look into that.",
      "Let me check on that for you.",
      "Got it — looking into that now."
    ]
  }
}
```

Template selection logic:

1. Look up the intent's `action_requested` in the hat's `ack_templates`.
2. If a match exists, randomly select one template from the list.
3. If no match, fall back to `_default`.
4. If no `_default` exists, fall back to a hardcoded core default: `"One moment while I look into that."`
5. Slot-fill `{parameter_name}` placeholders from `intent.parameters`. Unfilled placeholders are removed (along with any surrounding phrase that becomes awkward — e.g., `"order {order_id}"` with no order_id becomes `"your order"`). The slot-fill logic is deterministic string replacement, not LLM inference.

### WebSocket event

A new event type is emitted:

```json
{
  "event": "preflight_ack",
  "data": {
    "message": "Let me pull up order 123456 for you.",
    "intent_action": "order_status",
    "top_candidate_tool": "check_order_status"
  }
}
```

This event is emitted from `sophia/api/routes.py` *before* the consequence engine call, in both the HTTP (`/chat`) and WebSocket (`/ws/chat`) paths. For the HTTP path, the ack is included in the `PipelineResult` but does not change the final response — it is metadata for clients that poll rather than stream.

### UI handling

The WebSocket hook (`useWebSocket.ts`) handles `preflight_ack` by immediately inserting a temporary assistant message into the chat:

```typescript
case "preflight_ack": {
  const ackMsg: ChatMessage = {
    id: genId(),
    role: "assistant",
    content: event.data.message,
    trace: null,
    tier: null,
    timestamp: Date.now(),
    isAck: true,  // new field
  };
  setMessages((prev) => [...prev, ackMsg]);
  break;
}
```

When the final `response_ready` event arrives, the ack message is **replaced**, not appended to. The ack was a placeholder; the real response supersedes it. `MessageBubble.tsx` can optionally animate this transition (e.g., a brief crossfade).

```typescript
case "response_ready": {
  // ... existing logic ...
  // Replace the ack message if one exists
  setMessages((prev) => {
    const withoutAck = prev.filter((m) => !m.isAck);
    return [...withoutAck, assistantMsg];
  });
  // ...
}
```

### What the ack is NOT

The ack is not a commitment to execute. It is not a preview of the action. It does not tell the user what Sophia *will* do — only that Sophia has received the input and is working on it. If the pipeline ultimately refuses (RED) or escalates (ORANGE), the ack was still accurate: Sophia *did* look into it, and the result of looking into it was a refusal or escalation.

The ack is not shown in the final audit record as a "response." It is logged as a `preflight_ack` event with its own timestamp, separate from the pipeline's `response` field. The audit schema gains a new optional field:

```python
@dataclass
class PipelineResult:
    # ... existing fields ...
    preflight_ack: str | None = None  # NEW
    preflight_ack_at: float | None = None  # timestamp, NEW
```

### Hat extension points

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ack_templates` | `dict[str, list[str]]` | `{}` | Templates keyed by `action_requested`. Must include `_default` or core fallback is used. |
| `ack_financial_ceiling` | `float` | `0.0` | Max `max_financial_impact` of any candidate tool for which acks are allowed. |
| `ack_enabled` | `bool` | `true` | Master switch. Set to `false` to disable acks entirely for this hat. |

### Implementation location

The ack decision and template rendering are implemented in `sophia/core/preflight_ack.py`. The function signature:

```python
def maybe_generate_ack(
    intent: Intent,
    candidates: list[CandidateAction],
    tool_registry: ToolRegistry,
    hat_config: HatConfig,
) -> str | None:
```

Returns `None` if any skip condition is met. Otherwise returns the rendered template string. Called from `sophia/core/loop.py` after the parameter gate and before the consequence engine.

## Consequences

**Positive:**
- Perceived latency drops significantly for the most common pipeline path (tool lookup with `authority_level="agent"` and no financial impact). The user sees a response within ~100ms of sending their message, even though the full pipeline takes 10–90 seconds.
- The implementation adds zero LLM calls and negligible compute. Template rendering is pure string replacement.
- The ack is auditable — it appears in the WebSocket event stream and the `PipelineResult`, preserving ADR-011.
- Hats control the entire ack experience: templates, financial ceiling, and the master switch. A hat for a high-stakes domain (e.g., medical, legal) can disable acks entirely.
- The ack naturally handles the msg-9 scenario from the 2026-03-03 audit: user provides email + order number → immediate "Let me pull up order 123456 for you" → full pipeline runs → real response replaces ack.
- Dangerous/unethical requests are not acknowledged prematurely. The `authority_level` and `max_financial_impact` gates ensure that sensitive operations go through the full pipeline silently. The PS5 scenario (`place_new_order`, `authority_level="agent"` but with financial impact) would skip the ack because `max_financial_impact > 0.0` on the tool.

**Negative:**
- Template-based messages are less natural than LLM-generated ones. A template might say "Let me pull up order 123456 for you" when the user said "my order is one-two-three-four-five-six" — the ack echoes the parsed parameter, not the user's phrasing. This is a minor uncanny valley effect. Hats can mitigate it with more varied templates.
- The ack-then-replace pattern in the UI introduces a visual state change: the user sees one message, then it morphs into another. If the pipeline is very fast (e.g., a simple GREEN execution), the ack might flash for only a fraction of a second before being replaced, which could feel janky. The UI should enforce a minimum display time (e.g., 800ms) before allowing replacement, or crossfade the transition.
- The `authority_level` heuristic is coarse. A tool with `authority_level="agent"` might still be sensitive in context (e.g., looking up a competitor's public pricing is fine, but looking up another customer's order is a privacy issue). The ack doesn't know this — it fires based on the tool's static metadata, not the specific parameters. This is acceptable because the ack makes no commitment; the pipeline still evaluates fully.
- If the parameter gate (ADR-019) is not yet implemented, the ack decision has no gate to rely on for filtering out placeholder-parameter candidates. The ack could fire for a candidate that will fail at execution time. This produces a slightly misleading UX ("Let me pull up order UNKNOWN for you") but is self-correcting when the real response arrives. ADR-019 should be implemented first or concurrently.
- Adding `isAck` to `ChatMessage` is a schema change in the UI types. Existing message rendering, export, and audit display must handle the new field gracefully (default to `false`/`undefined`).
