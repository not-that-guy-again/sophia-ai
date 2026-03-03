# Sophia Roadmap

## Active Work

### Conversational Bypass (ADR-017)

The pipeline currently forces every input through tool selection. Greetings, questions, and other non-actionable messages get routed to arbitrary tools. The proposer needs a "converse" candidate type that bypasses tool execution and generates a direct conversational response. This also skips consequence tree generation, evaluation, and risk classification for non-actionable inputs.

### Response Generation (ADR-018)

After tool execution, raw ToolResult data (Python dicts) is dumped directly into the chat. A new response generator component sits between the executor and final output. It takes the original message, tool result, hat context, and memory context, then makes an LLM call to produce natural language. Applies to all tiers: GREEN gets a conversational response incorporating data, YELLOW gets an explanation of what needs confirmation and why, ORANGE gets an escalation explanation, RED gets a refusal citing specific concerns.

---

## Planned: Phase 5 (Audit and Feedback)

Persistent decision logging, outcome tracking, and feedback loops. See 05-audit.md for full spec.

- Database schema for decisions, proposals, trees, evaluations, outcomes, feedback
- Append-only immutable audit log
- Outcome tracking: compare predicted consequences vs actual
- Feedback loop: analyze human overrides on YELLOW/ORANGE for prompt tuning
- API endpoints for querying audit history

## Planned: Phase 6 (Memory System)

Three-tier memory backed by SurrealDB, independent from the Hat system. See 06-memory-system.md and ADRs 012-016 for full design.

- MemoryProvider interface (same pattern as LLMProvider)
- SurrealDB implementation with document + graph + vector support
- MockMemoryProvider for tests
- Memory extractor: LLM calls to convert conversations into structured episodes and entities
- Memory recall flow: query at interaction start, inject relevant context
- Memory storage: extract and persist after pipeline completes
- Remove legacy sophia/memory/store.py

---

## Future Enhancements

### Consequence Engine

**Red Team Node:** Adversarial consequence node exploring worst-case scenarios, manipulation vectors, cascading failures. Could be a third mandatory root node or separate LLM call with adversarial persona.

**Transaction-Level Risk Floors:** Tools declare minimum risk tier (e.g., transfer_funds always YELLOW). Complements existing authority_level and max_financial_impact.

**Consequence Tree Caching:** Cache trees by tool name + parameter shape + hat name with TTL for repeated similar actions.

### Evaluator Improvements

**Per-Hat Weight Documentation:** Guidance for weight distribution across domains. Finance: increase authority. Content moderation: increase tribal. Internal tools: increase domain.

**Multi-Model Evaluator Panel:** Different LLM models per evaluator to reduce correlated failure modes.

### Hat System

**Hat Stacking:** Multiple simultaneous hats with merged tool sets and conflict resolution.

**Community Hat Registry:** Package hats for pip/git distribution with template generator and validation suite.

### Infrastructure

**Outcome Tracking and Feedback Loops:** Compare predicted vs actual consequences to tune evaluators over time.

### UI

**Consequence Tree Visualization:** Color gradients for harm_benefit, node sizing by probability, interactive drill-down, distinct red team node treatment.
