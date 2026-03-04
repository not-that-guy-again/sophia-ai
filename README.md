<p align="center">
  <img src="assets/Sophia-Ai-Logo.png" alt="Sophia" width="280" />
</p>

<h1 align="center">Sophia</h1>

<p align="center">
  <strong>A consequence-aware AI agent framework.</strong><br>
  Open source. Domain-agnostic. Thinks before it acts.
</p>

<p align="center">
  <a href="#the-core-idea">Core Idea</a> · 
  <a href="#how-it-works">How It Works</a> · 
  <a href="#the-hat-system">Hats</a> · 
  <a href="#architecture">Architecture</a> · 
  <a href="#quickstart">Quickstart</a> · 
  <a href="#project-status">Status</a> · 
  <a href="docs/ARCHITECTURE.md">Full Docs</a>
</p>

---

## The Core Idea

Most AI agents work like this: the LLM decides to do something, and then it does it. Immediately. No review, no second thought, no "wait, should I actually do that?"

Sophia doesn't work like that.

Sophia inserts a full consequence simulation and multi-evaluator review step between "I think I should do this" and "I did it." Every candidate action gets run through a branching outcome tree, scored by four independent evaluators, classified into a risk tier, and then routed to the right level of autonomy. Some actions execute automatically. Some ask for confirmation. Some get escalated to a human. Some get refused outright.

The point is not to slow things down. The point is that actions have consequences, and an agent that doesn't think about consequences before acting is just a faster way to make mistakes.

## How It Works

When a message comes in, Sophia doesn't just generate a response. She runs a pipeline.

```
User Message
    │
    ▼
┌──────────────────────┐
│  Memory Recall       │  What do I already know about this person/situation?
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Input Gate          │  What is this person actually asking for?
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Proposer            │  Here are 1-3 candidate actions I could take.
└──────────┬───────────┘  (NO execution yet. Just proposals.)
           │
           ├─── just talking? ──────────────┐
           │                                │
           ▼                                ▼
┌──────────────────────┐           ┌──────────────────┐
│  Consequence Engine  │           │  Response Gen    │
│  (branching outcomes │           │  (conversational │
│   per candidate)     │           │   bypass)        │
└──────────┬───────────┘           └───────┬──────────┘
           │                               │
           ▼                               │
┌──────────────────────┐                   │
│  Evaluation Panel    │                   │
│  4 evaluators score  │                   │
│  in parallel:        │                   │
│  · Self-interest     │                   │
│  · Tribal harm       │                   │
│  · Domain rules      │                   │
│  · Authority         │                   │
└──────────┬───────────┘                   │
           │                               │
           ▼                               │
┌──────────────────────┐                   │
│  Risk Classifier     │                   │
│  GREEN / YELLOW /    │                   │
│  ORANGE / RED        │                   │
└──────────┬───────────┘                   │
           │                               │
           ▼                               │
┌──────────────────────┐                   │
│  Executor            │                   │
│  GREEN  → act        │                   │
│  YELLOW → confirm    │                   │
│  ORANGE → escalate   │                   │
│  RED    → refuse     │                   │
└──────────┬───────────┘                   │
           │                               │
           ▼                               │
┌──────────────────────┐                   │
│  Response Generator  │ ◄─────────────────┘
│  (natural language)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Memory Persist      │  Store what happened for next time.
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Audit Log           │  Full decision trail. Every time.
└──────────────────────┘
```

If the proposer decides the message is just conversation (a greeting, a clarifying question, small talk), it skips the consequence engine, evaluators, risk classifier, and executor entirely. No reason to score the consequences of saying "good morning." Memory still runs on both ends.

### The Evaluators

Four independent evaluators score every consequence tree in parallel. They don't talk to each other. They each look at the same tree from a different angle:

| Evaluator | Question It Answers | Weight (default) |
|---|---|---|
| **Self-Interest** | Does this serve the person's stated goals? | 0.20 |
| **Tribal** | Does this cause tangible harm to people or the community? | 0.40 |
| **Domain** | Does this violate the rules and policies for this domain? | 0.25 |
| **Authority** | Does this person have the standing to request this? | 0.15 |

The tribal evaluator has veto power. If it flags catastrophic harm, the action goes to RED regardless of what the other three think.

Weights and thresholds are configurable per Hat (more on Hats below). The defaults reflect a deliberate choice: community impact matters most.

### Risk Tiers

The risk classifier takes the weighted evaluator scores and sorts them into four tiers:

| Tier | What Happens | Default Threshold |
|---|---|---|
| 🟢 **GREEN** | Execute immediately | Score above -0.1 |
| 🟡 **YELLOW** | Ask for human confirmation first | Score above -0.4 |
| 🟠 **ORANGE** | Auto-escalate to a human agent | Score above -0.7 |
| 🔴 **RED** | Refuse the action entirely | Score below -0.7 |

Uncertainty always bumps up, never down. If the system isn't sure, it errs on the side of caution.

## The Hat System

Sophia is domain-agnostic. She doesn't know anything about customer service, or content moderation, or inventory management, or anything else until you give her a Hat.

A Hat is a pluggable module that gives Sophia a specific role. It brings tools, constraints, stakeholder definitions, evaluator tuning, backend configurations, and prompt fragments. When a Hat is equipped, only that Hat's tools are available. The consequence engine and evaluation panel work the same regardless of which Hat is worn.

Think of it like a job. A person who went to law school and also knows how to weld doesn't practice welding while they're working as a lawyer. Sophia works the same way. One hat at a time.

```
hats/customer-service/
├── hat.json                 ← manifest: tools, weights, thresholds, backends, webhooks
├── tools/                   ← the actions Sophia can take in this role
├── constraints.json         ← domain rules and policies
├── stakeholders.json        ← who gets affected by decisions
├── evaluator_config.json    ← weight/threshold overrides
├── prompts/                 ← domain-specific prompt additions per pipeline stage
└── seed/                    ← mock data for development
```

The first Hat that ships with Sophia is **Customer Service**, targeting bounded commercial interactions. It has 19 tools covering order management, shipping, returns, compensation, and escalation.

### Service Backends

Tools don't talk to external systems directly. They call service interfaces (`OrderService`, `CustomerService`, `ShippingService`, etc.), and the backend implementation is swapped via Hat configuration. This means `look_up_order` works identically whether the backend is Shopify, a custom REST API, or a mock.

Backends are configured per-Hat in `hat.json`:

```json
{
  "backends": {
    "order": { "provider": "shopify", "config": { "api_key_env": "SHOPIFY_API_KEY" } },
    "shipping": { "provider": "mock", "config": {} }
  }
}
```

Everything defaults to `mock` if you don't specify. You can point one service at a real provider and keep the rest on mock while you integrate incrementally.

There are also generic REST and GraphQL adapters that let you connect any API through configuration alone, zero custom code. And an MCP adapter (in progress) that uses public MCP servers as dumb connectors, routing everything through the consequence engine so no integration bypasses the safety pipeline.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Sophia Core                                 │
│                                                                      │
│  ┌───────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐            │
│  │  Input    │  │Proposer  │  │Consequence│  │Evaluation│            │
│  │  Gate     │→ │          │→ │Engine     │→ │Panel (x4)│            │
│  └───────────┘  └──────────┘  └───────────┘  └──────────┘            │
│       ↑                                          │                   │
│       │             ┌──────────┐  ┌──────────┐   │                   │
│       │             │  Risk    │  │ Executor │   │                   │
│       │             │Classifier│← │          │←──┘                   │
│       │             └──────────┘  └──────────┘                       │
│       │                    │                                         │
│       │                    ▼                                         │
│       │             ┌──────────────┐                                 │
│       │             │  Response    │                                 │
│       │             │  Generator   │                                 │
│       │             └──────────────┘                                 │
│       │                    │                                         │
│  ┌────┴────────────────────┴──────────────────────────┐              │
│  │              Memory System (SurrealDB)             │              │
│  │  Episodic memory · Entity graph · Relationships    │              │
│  └────────────────────────────────────────────────────┘              │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                        Hat Layer                                     │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌──────────────┐       │
│  │  Tools   │  │Constraints│  │Stakeholders│  │Prompt        │       │
│  │          │  │& Policies │  │            │  │Fragments     │       │
│  └────┬─────┘  └───────────┘  └────────────┘  └──────────────┘       │
│       │                                                              │
├───────┼──────────────────────────────────────────────────────────────┤
│       │           Service Provider Layer                             │
│       ▼                                                              │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐          │
│  │OrderSvc  │  │CustomerSvc│  │ShippingSvc│  │InventorySvc│          │
│  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬──────┘          │
│       │              │              │              │                 │
├───────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│       ▼              ▼              ▼              ▼                 │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐               │
│  │  Mock   │   │ Shopify │   │  REST   │   │   MCP   │               │
│  │         │   │         │   │ Adapter │   │ Adapter │               │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘               │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                          Data Layer                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ Hat Files    │  │  SurrealDB   │  │ Audit DB     │                │
│  │ (config,     │  │ (memory,     │  │ (decisions,  │                │
│  │  on disk)    │  │  entities,   │  │  traces,     │                │
│  │              │  │  embeddings) │  │  feedback)   │                │
│  └──────────────┘  └──────────────┘  └──────────────┘                │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

Sophia has 25 Architecture Decision Records documenting every significant choice. Here are the ones that matter most:

**Propose, then evaluate.** The LLM proposes actions. It does not execute them. Execution only happens after consequence analysis, evaluation, and risk classification. This is the foundational principle.

**Four independent evaluators.** They run in parallel and don't see each other's work. Different perspectives on the same consequence tree. The tribal evaluator can veto anything.

**Uncertainty bumps up, never down.** If the system isn't confident in its risk assessment, the tier goes up (toward more caution), not down. This is not negotiable.

**One hat at a time.** Domain expertise is pluggable and scoped. Tools from other Hats don't bleed through. This keeps token budgets sane and prevents the agent from doing things outside its current role.

**Three-system data architecture.** Hat configuration lives on disk (version-controlled). Memory lives in SurrealDB (document + graph + vector). Decision records live in the audit database (append-only, relational). No system stores data that belongs to another.

**The provider pattern.** Every external dependency (LLM, memory, service backends) sits behind an abstract interface with a factory resolver. You can swap Anthropic for Ollama, SurrealDB for a mock, Shopify for a generic REST adapter, all without touching pipeline code.

## Quickstart

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (package manager)
- An Anthropic API key, or [Ollama](https://ollama.ai) running locally

### Setup

```bash
git clone git@github.com:not-that-guy-again/sophia-ai.git
cd sophia

# Install dependencies
uv sync

# Configure
cp .env.example .env
# Edit .env with your API key and preferences

# Run
uv run uvicorn sophia.api:app --reload
```

The API starts at `http://localhost:8000`. The WebSocket endpoint at `/ws/chat` streams pipeline events in real time.

### Running with Ollama (no API key needed)

```bash
# In .env
LLM_PROVIDER=ollama
LLM_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
```

### Tests

```bash
uv run pytest
```

The entire test suite runs with zero external dependencies. No API keys, no databases, no network access. Everything is mocked.

## Project Status

| Phase | What | Status |
|---|---|---|
| 1 | Foundation: Hat system, pipeline, LLM abstraction, API | ✅ Complete |
| 2 | Consequence Engine: depth-first outcome trees | ✅ Complete |
| 3 | Evaluation Panel: 4 evaluators + risk classifier | ✅ Complete |
| 4 | Chat UI: React web interface with pipeline visualization | ✅ Complete |
| 5 | Audit & Feedback: persistent logging, outcome tracking | ✅ Complete |
| 6 | Memory System: three-tier memory with SurrealDB | ✅ Complete |
| 7 | Pipeline Optimization: conversational bypass, parameter gate, preflight ack, constitution | ✅ Complete |
| 8 | Production Readiness: service providers, adapters, webhooks, MCP | 🔧 In Progress |

## Documentation

- **[Architecture Reference](docs/ARCHITECTURE.md)** for the full technical deep-dive
- **[Hat Specification](docs/HAT_SPEC.md)** for the formal Hat interface
- **[Creating Hats](docs/CREATING_HATS.md)** if you want to build your own
- **[Architecture Decision Records](decisions/)** for every significant design choice (ADR-001 through ADR-025)
- **[Contributing](docs/CONTRIBUTING.md)** for development guidelines

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
