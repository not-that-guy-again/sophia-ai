# Sophia Architecture

## Overview

Sophia is a consequence-aware AI agent framework. Instead of executing actions the moment an LLM suggests them, Sophia inserts a consequence simulation and multi-evaluator review step between proposal and execution. Every candidate action is run through a depth-first consequence tree, scored by independent evaluators, classified by risk tier, and routed to the appropriate autonomy level.

Domain expertise is provided through **Hats** — pluggable modules that give the agent a specific role. The core framework is domain-agnostic; all domain-specific tools, constraints, stakeholders, and evaluator tuning come from the equipped Hat.

## The Core Loop

```
User Input
    │
    ▼
┌─────────────────┐
│  0. Memory       │  Query memory for relevant entities/episodes (read-only)
│     Recall       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  1. Input Gate   │  Parse intent, attach metadata, pull hat context
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. Proposer     │  LLM generates 1-3 candidate actions (NO execution)
└────────┬────────┘  Can select "converse" to bypass bracketed stages
         │
         ├── converse ──────────────────────────┐
         │                                      ▼
         ▼                            ┌──────────────────┐
┌─────────────────┐                   │  7. Response Gen  │
│  3. Consequence  │                  │     (converse)    │
│     Tree         │                  └────────┬─────────┘
└────────┬────────┘                            │
         │                                     │
         ▼                                     │
┌─────────────────┐                            │
│  4. Evaluation   │                           │
│     Panel        │                           │
└────────┬────────┘                            │
         │                                     │
         ▼                                     │
┌─────────────────┐                            │
│  5. Risk         │                           │
│     Classifier   │                           │
└────────┬────────┘                            │
         │                                     │
         ▼                                     │
┌─────────────────┐                            │
│  6. Executor     │                           │
└────────┬────────┘                            │
         │                                     │
         ▼                                     │
┌─────────────────┐                            │
│  7. Response Gen │  LLM turns raw results ◄──┘
│     (generate)   │  into natural language
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  8. Memory       │  Extract and store entities/episodes (write-only)
│     Persist      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  9. Audit Log    │  Full trail: input → proposals → tree → scores → action → outcome
└─────────────────┘
```

### Conversational Bypass (ADR-017)

When the proposer selects `"converse"` as the tool_name, the bracketed stages (consequence tree, evaluation panel, risk classifier, executor) are skipped entirely. The message goes directly to the response generator's `converse()` path. This handles greetings, general questions, and messages where no tool is appropriate — without wasting LLM calls on consequence analysis.

### Response Generation (ADR-018)

The response generator replaces the old `_build_response()` method. Instead of dumping raw tool results, an LLM call turns pipeline output into natural language matching the hat's voice and tone. This ensures users never see Python dicts, tool names, or pipeline internals.

## Design Principles

- **Propose, don't execute.** The LLM suggests actions. A separate pipeline decides whether to carry them out.
- **Tribal harm overrides self-interest.** Any single evaluator flagging catastrophic harm triggers automatic RED, regardless of other scores.
- **Uncertainty means caution.** Evaluator disagreement bumps the risk tier up, never down.
- **Everything is auditable.** Every decision produces an immutable record with full reasoning chain.
- **Tiered autonomy, not binary.** Four tiers calibrated to risk level, not a simple allow/block.
- **Hats, not hardcoding.** Domain expertise is pluggable. The core framework never assumes what domain it's operating in.

## Key Components

### Hat System (`sophia/hats/`)

The Hat system is the abstraction that makes Sophia domain-agnostic. See [HAT_SPEC.md](HAT_SPEC.md) for the full interface specification and [CREATING_HATS.md](CREATING_HATS.md) for a guide on building new Hats.

- **`schema.py`** — Pydantic models: `HatManifest`, `HatConfig`, `Stakeholder`, `EvaluatorConfig`
- **`loader.py`** — Discovers hats on disk, validates structure, dynamically imports tool modules
- **`registry.py`** — Manages the active hat, scopes tools, provides hat context to the pipeline
- **`prompt_assembler.py`** — Merges core framework prompts with hat-specific fragments

When a Hat is equipped:
1. Its tools are registered (and only its tools — previous tools are cleared)
2. Its constraints and stakeholders are loaded into the memory store
3. Its prompt fragments are injected into each pipeline stage
4. Its evaluator weights and risk thresholds override the defaults

### LLM Providers (`sophia/llm/`)

Abstract interface supporting multiple backends:

- **`provider.py`** — `LLMProvider` ABC with `async complete()`, `LLMResponse` dataclass, `get_provider()` factory
- **`anthropic.py`** — Claude via the Anthropic SDK
- **`ollama.py`** — Local models via Ollama's HTTP API

### Pipeline Components (`sophia/core/`)

- **`input_gate.py`** — Parses raw user messages into structured `Intent` objects. Prompt is assembled from core + hat system prompt.
- **`proposer.py`** — Generates 1-3 `CandidateAction` items with reasoning. Only sees the active hat's tools. Can select `"converse"` to bypass consequence/evaluation stages.
- **`consequence.py`** — Generates depth-first consequence trees for each candidate action. Each node carries stakeholders, probability, tangibility, and harm/benefit scores.
- **`evaluators/`** — Four independent evaluators (tribal, domain, self-interest, authority) score consequence trees in parallel.
- **`risk_classifier.py`** — Deterministic aggregation of evaluator scores into risk tiers (GREEN/YELLOW/ORANGE/RED). Supports catastrophic-harm overrides and evaluator-disagreement bumps.
- **`executor.py`** — Tiered execution: GREEN executes, YELLOW requests confirmation, ORANGE auto-escalates, RED refuses. Handles `"converse"` gracefully without touching the tool registry.
- **`response_generator.py`** — LLM-based natural language generation from raw pipeline output. `generate()` for tool results, `converse()` for conversational bypass. Uses the hat's system prompt for domain-appropriate tone.
- **`loop.py`** — `AgentLoop` orchestrates the full pipeline: Memory Recall → Input Gate → Proposer → [Consequence → Evaluation → Risk → Executor] → Response Generator → Memory Persist.

### Tool System (`sophia/tools/`)

- **`base.py`** — `Tool` ABC defining the interface all tools must implement: `name`, `description`, `parameters` (JSON schema), `authority_level`, `max_financial_impact`, `async execute()`
- **`registry.py`** — `ToolRegistry` registers/dispatches tools by name. Supports `clear()` for hat switching. Refuses calls to unregistered tools.

Actual tool implementations live inside Hats, not in the core framework.

### API (`sophia/api/`)

FastAPI application exposing:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/tools` | GET | List tools from the active hat |
| `/chat` | POST | Run the full pipeline |
| `/hats` | GET | List available hats |
| `/hats/active` | GET | Current hat details |
| `/hats/{name}/equip` | POST | Switch hats |
| `/ws/chat` | WS | Streaming pipeline events |

The WebSocket sends granular events as the pipeline progresses: `hat_equipped`, `intent_parsed`, `proposals_generated`, `action_executed`, `response_ready`.

## Data Flow

### Full Pipeline (tool execution)

```
User message (string)
  → MemoryProvider.search_entities() → memory context (read-only)
  → InputGate.parse() → Intent
  → Proposer.propose(intent) → Proposal [1-3 CandidateActions]
  → ConsequenceEngine.analyze(candidate) → ConsequenceTree (per candidate)
  → Evaluators.evaluate() → [EvaluatorResult × 4] (parallel)
  → classify() → RiskClassification (GREEN/YELLOW/ORANGE/RED)
  → Executor (tiered) → ExecutionResult
  → ResponseGenerator.generate() → natural language response
  → MemoryExtractor.extract_and_store() → memory persist (write-only)

All wrapped in PipelineResult with full metadata.
```

### Conversational Bypass (no tool)

```
User message (string)
  → MemoryProvider.search_entities() → memory context
  → InputGate.parse() → Intent
  → Proposer.propose(intent) → Proposal [tool_name="converse"]
  → ResponseGenerator.converse() → natural language response
  → MemoryExtractor.extract_and_store() → memory persist

PipelineResult with bypassed=True, empty trees/evaluations/classification.
```

## Configuration

Settings are loaded from environment variables (`.env` file) via Pydantic `BaseSettings`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Anthropic provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model for chosen provider |
| `LLM_MODEL_INPUT_GATE` | *(uses `LLM_MODEL`)* | Model for the input gate stage |
| `LLM_MODEL_PROPOSER` | *(uses `LLM_MODEL`)* | Model for the proposer stage |
| `LLM_MODEL_CONSEQUENCE` | *(uses `LLM_MODEL`)* | Model for consequence tree generation |
| `LLM_MODEL_EVALUATORS` | *(uses `LLM_MODEL`)* | Model for all four evaluators |
| `LLM_MODEL_RESPONSE_GEN` | *(uses `LLM_MODEL`)* | Model for response generation |
| `LLM_MODEL_MEMORY` | *(uses `LLM_MODEL`)* | Model for memory extraction |
| `DEFAULT_HAT` | `customer-service` | Hat to equip on startup |
| `HATS_DIR` | `./hats` | Directory to scan for hats |
| `DATABASE_URL` | `sqlite+aiosqlite:///sophia.db` | Database connection |
| `LOG_LEVEL` | `INFO` | Logging level |

All per-stage model variables are optional. Unset variables fall back to `LLM_MODEL`. Changing any per-stage model requires re-equipping the hat or restarting the server to take effect.

Evaluator weights, risk thresholds, and domain constraints are all configured per-hat, not globally.

### Memory System (`sophia/memory/`)

- **`models.py`** — `Episode`, `Entity`, `Relationship` dataclasses
- **`provider.py`** — `MemoryProvider` ABC with search, recall, and store methods; `get_memory_provider()` factory
- **`mock.py`** — Dict-based in-memory provider for tests
- **`surrealdb.py`** — Production provider backed by SurrealDB (document + graph + vector)
- **`extractor.py`** — LLM-based extraction of entities, episodes, and relationships from pipeline results

### Audit System (`sophia/audit/`)

- **`models.py`** — SQLAlchemy ORM: Decision, DecisionProposal, DecisionTree, DecisionEvaluation, DecisionOutcome, Feedback, HatConfigSnapshot
- **`database.py`** — Async engine, session factory, lifecycle management
- **`service.py`** — Append-only operations: store_decision_with_hat, store_outcome, store_feedback, query_decisions

Audit is non-intrusive — logged at the API layer, not in the core loop. Hat config is snapshotted at decision time for historical interpretability.

## Phase Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Foundation — hat system, pipeline, API | Complete |
| 2 | Consequence Engine — depth-first outcome trees | Complete |
| 3 | Evaluation Panel — 4 evaluators + risk classifier | Complete |
| 4 | Chat UI — React web interface | Complete |
| 5 | Audit & Feedback — persistent logging, outcome tracking | Complete |
| 6 | Memory System — three-tier memory with SurrealDB | Complete |
