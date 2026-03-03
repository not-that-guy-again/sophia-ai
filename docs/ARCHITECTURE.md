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
│  1. Input Gate   │  Parse intent, attach metadata, pull hat context
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. Proposer     │  LLM generates 1-3 candidate actions (NO execution)
└────────┬────────┘  Only tools from the equipped Hat are available
         │
         ▼
┌─────────────────┐
│  3. Consequence  │  For each candidate, generate branching outcome tree
│     Tree         │  Each node: stakeholders, probability, tangibility, harm/benefit
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. Evaluation   │  4 independent evaluators score the tree in parallel
│     Panel        │  Self-interest | Tribal harm | Domain rules | Authority
└────────┬────────┘  Evaluators use Hat-specific context and tuning
         │
         ▼
┌─────────────────┐
│  5. Risk         │  Aggregate scores → risk tier (GREEN/YELLOW/ORANGE/RED)
│     Classifier   │  Deterministic routing logic, not LLM inference
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. Executor     │  GREEN: act | YELLOW: confirm | ORANGE: escalate | RED: refuse
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. Audit Log    │  Full trail: input → proposals → tree → scores → action → outcome
└─────────────────┘
```

**Current state (Phase 1):** Steps 1, 2, and 6 are implemented. Steps 3-5 and 7 are future phases. The executor currently runs the top candidate directly with a hardcoded GREEN tier.

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
- **`proposer.py`** — Generates 1-3 `CandidateAction` items with reasoning. Only sees the active hat's tools. Prompt includes domain constraints.
- **`executor.py`** — Dispatches the selected action to the tool registry. In Phase 1, always takes the top candidate. Future phases route by risk tier.
- **`loop.py`** — `AgentLoop` orchestrates the pipeline. Initializes with a hat, rebuilds components on hat switch, runs the full Input Gate → Proposer → Executor chain.

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

```
User message (string)
  → InputGate.parse() → Intent
  → Proposer.propose(intent) → Proposal [1-3 CandidateActions]
  → Executor.execute(proposal) → ExecutionResult
  → AgentLoop._build_response() → response string

All wrapped in PipelineResult with full metadata.
```

## Configuration

Settings are loaded from environment variables (`.env` file) via Pydantic `BaseSettings`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Anthropic provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model for chosen provider |
| `DEFAULT_HAT` | `customer-service` | Hat to equip on startup |
| `HATS_DIR` | `./hats` | Directory to scan for hats |
| `DATABASE_URL` | `sqlite+aiosqlite:///sophia.db` | Database connection |
| `LOG_LEVEL` | `INFO` | Logging level |

Evaluator weights, risk thresholds, and domain constraints are all configured per-hat, not globally.

## Phase Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Foundation — hat system, pipeline, API | Complete |
| 2 | Consequence Engine — depth-first outcome trees | Planned |
| 3 | Evaluation Panel — 4 evaluators + risk classifier | Planned |
| 4 | Chat UI — React web interface | Planned |
| 5 | Audit & Feedback — persistent logging, outcome tracking | Planned |
