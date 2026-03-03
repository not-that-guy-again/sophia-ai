# Sophia Roadmap

## Completed

### Phase 1: Foundation

Hat system, LLM provider abstraction (Anthropic, Ollama), input gate, action proposer, tool system, executor, FastAPI skeleton, and orchestration loop.

### Phase 2: Consequence Engine

Depth-first consequence tree generation, tree analysis utilities (worst path, catastrophic branches, stakeholder impact), and pipeline integration with heuristic risk scoring.

### Phase 3: Evaluation Panel

Four independent evaluators (self-interest, tribal, domain, authority), deterministic risk classifier with weighted scoring, and tiered executor (GREEN/YELLOW/ORANGE/RED).

### Phase 4: Chat UI

Vite + React + TypeScript + Tailwind stack, WebSocket events during pipeline execution, chat interface with expandable decision trails, hat selector, and pipeline visualization.

### Phase 5: Audit and Feedback

Append-only audit database (SQLite dev, PostgreSQL production), ORM models for decisions/proposals/trees/evaluations/outcomes/feedback, hat config snapshots, outcome tracking, and API endpoints.

### Phase 6: Memory System

Three-tier memory (working/episodic/long-term) backed by SurrealDB, MemoryProvider interface with mock for tests, LLM-based memory extractor, recall at pipeline start, and persist after completion.

### Conversational Bypass (ADR-017)

Proposer "converse" candidate type that bypasses consequence tree generation, evaluation, and risk classification for non-actionable inputs. LLM decides when to bypass (no hardcoded keyword matching).

### Response Generation (ADR-018)

ResponseGenerator component between executor and final output. Converts raw tool results to natural language via LLM. Tier-aware: GREEN (confirm action), YELLOW (explain confirmation), ORANGE (explain escalation), RED (cite concerns and refuse). Includes dedicated converse path for conversational bypass.

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
