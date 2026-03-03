# Hat Specification

Formal interface definition for Sophia Hats. Version 0.1.0.

## Overview

A Hat is a directory containing a manifest, tools, and optional configuration files that give Sophia domain expertise. The core framework is domain-agnostic — all domain-specific behavior comes from the equipped Hat.

## Directory Structure

```
hats/<hat-name>/
├── hat.json                # REQUIRED — manifest
├── tools/                  # REQUIRED — tool implementations
│   ├── *.py                # One or more Python modules with Tool subclasses
│   └── (no __init__.py needed)
├── constraints.json        # OPTIONAL — domain rules and policies
├── stakeholders.json       # OPTIONAL — affected parties
├── evaluator_config.json   # OPTIONAL — evaluator weight/threshold overrides
├── prompts/                # OPTIONAL — prompt fragments for pipeline stages
│   ├── system.txt
│   ├── proposer.txt
│   ├── consequence.txt
│   ├── eval_self.txt
│   ├── eval_tribal.txt
│   ├── eval_domain.txt
│   └── eval_authority.txt
└── seed/                   # OPTIONAL — mock/seed data for development
    └── *.json
```

### Naming Convention

- Directory name must be lowercase, hyphen-separated (e.g., `customer-service`, `content-moderation`).
- The `name` field in `hat.json` must exactly match the directory name.

## Manifest (`hat.json`)

### Schema

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Hat identifier, must match directory name |
| `version` | string | No | `"0.1.0"` | Semantic version of this Hat |
| `display_name` | string | No | `""` | Human-readable name |
| `description` | string | No | `""` | One-line description |
| `author` | string | No | `""` | Author or organization |
| `license` | string | No | `"Apache-2.0"` | License identifier |
| `sophia_version` | string | No | `">=0.1.0"` | Required Sophia version (semver range) |
| `tools` | string[] | Yes | `[]` | Tool names to register (whitelist) |
| `default_evaluator_weights` | object | No | see below | Evaluator weight distribution |
| `risk_thresholds` | object | No | see below | Score boundaries between risk tiers |

### Default Evaluator Weights

```json
{
  "tribal": 0.40,
  "domain": 0.25,
  "self_interest": 0.20,
  "authority": 0.15
}
```

Values must sum to 1.0. These determine how much each evaluator's score contributes to the aggregate risk score.

### Default Risk Thresholds

```json
{
  "green": -0.1,
  "yellow": -0.4,
  "orange": -0.7
}
```

Aggregate score above `green` → GREEN tier. Between `green` and `yellow` → YELLOW. Between `yellow` and `orange` → ORANGE. Below `orange` → RED.

### Validation

The manifest is validated by `sophia.hats.schema.HatManifest` (Pydantic model). Invalid manifests raise a validation error at load time and are skipped during discovery.

## Tool Interface

Tools must extend `sophia.tools.base.Tool` (ABC).

### Required Class Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier, must be in the manifest's `tools` list |
| `description` | `str` | Human/LLM-readable description of what the tool does |
| `parameters` | `dict` | JSON Schema describing the tool's parameters |
| `authority_level` | `str` | One of `"agent"`, `"supervisor"`, `"admin"` |

### Optional Class Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_financial_impact` | `float \| None` | `None` | Maximum financial cost of a single invocation |

### Required Methods

```python
async def execute(self, params: dict) -> ToolResult
```

Execute the tool with validated parameters. Must return a `ToolResult`:

```python
@dataclass
class ToolResult:
    success: bool   # Whether the operation succeeded
    data: Any       # Structured result data
    message: str    # Human-readable summary
```

### Tool Definition Export

Every tool inherits `to_definition() -> dict`, which serializes the tool's metadata for inclusion in LLM prompts:

```python
{
    "name": "tool_name",
    "description": "What the tool does",
    "parameters": { ... },
    "authority_level": "agent",
    "max_financial_impact": 50.00
}
```

### Tool Loading Process

1. The loader scans all `.py` files in the hat's `tools/` directory (excluding files starting with `_`).
2. Each file is dynamically imported via `importlib.util`.
3. All classes that are subclasses of `Tool` (not `Tool` itself) are instantiated.
4. Only instances whose `name` appears in the manifest's `tools` list are kept.
5. Loaded tools are registered in the `ToolRegistry`.

### Tool Scoping

- When a Hat is equipped, its tools are registered and **only** its tools are available.
- When a Hat is unequipped, `ToolRegistry.clear()` removes all tools.
- Calls to unregistered tool names are refused by the registry.

## Constraints (`constraints.json`)

Free-form JSON. No enforced schema — structure it to match your domain. Constraints are:

- Loaded into the memory store for pipeline access
- Available to the proposer and evaluators as domain context
- Injected into prompts via the hat's prompt fragments

### Recommended Structure

```json
{
  "business_name": "string",
  "policies": { },
  "escalation_triggers": ["string"],
  "hard_rules": ["string"]
}
```

`hard_rules` should be absolute prohibitions. `escalation_triggers` define conditions that should bump actions out of agent autonomy.

## Stakeholders (`stakeholders.json`)

### Schema

```json
{
  "stakeholders": [
    {
      "id": "string",
      "name": "string",
      "interests": ["string"],
      "harm_sensitivity": "low | medium | high",
      "weight": 0.0
    }
  ]
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | — | Unique identifier |
| `name` | string | Yes | — | Human-readable name |
| `interests` | string[] | No | `[]` | What this stakeholder cares about |
| `harm_sensitivity` | string | No | `"medium"` | How sensitive this party is to harm |
| `weight` | float | No | `0.25` | Relative importance (should sum to ~1.0) |

Stakeholders are used by the consequence engine to model who is affected by each outcome branch, and by evaluators to score impact.

## Evaluator Config (`evaluator_config.json`)

### Schema

```json
{
  "weight_overrides": {
    "tribal": 0.40,
    "domain": 0.25,
    "self_interest": 0.20,
    "authority": 0.15
  },
  "custom_flags": {
    "domain": ["string"],
    "authority": ["string"],
    "tribal": ["string"]
  },
  "risk_thresholds": {
    "green": -0.1,
    "yellow": -0.4,
    "orange": -0.7
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `weight_overrides` | object | Override manifest's default evaluator weights |
| `custom_flags` | object | Domain-specific risk flags per evaluator |
| `risk_thresholds` | object | Override manifest's default risk thresholds |

`custom_flags` are keyed by evaluator name. Each evaluator checks for its flags during scoring. A triggered flag adds negative weight to the score.

## Prompt Fragments (`prompts/`)

Plain text files. Each is appended to the corresponding core framework prompt during pipeline execution via `prompt_assembler.assemble_prompt()`.

### Stage Mapping

| File | Pipeline Stage | Core Prompt |
|------|---------------|-------------|
| `system.txt` | `input_parse` | `sophia.llm.prompts.core.input_parse` |
| `proposer.txt` | `proposer` | `sophia.llm.prompts.core.proposer` |
| `consequence.txt` | `consequence` | (Phase 2) |
| `eval_self.txt` | `eval_self` | (Phase 3) |
| `eval_tribal.txt` | `eval_tribal` | (Phase 3) |
| `eval_domain.txt` | `eval_domain` | (Phase 3) |
| `eval_authority.txt` | `eval_authority` | (Phase 3) |

### Assembly Format

When a hat fragment exists for a stage, the assembled prompt is:

```
{core_prompt}

## Domain-Specific Context ({hat_display_name})

{hat_fragment}
```

When no fragment exists, the core prompt is used unmodified.

## Hat Lifecycle

### Discovery

`discover_hats(hats_dir)` scans all subdirectories of the hats directory for valid `hat.json` files. Returns a list of `HatManifest` objects.

### Loading

`load_hat(hat_path)` loads all components from disk into a `HatConfig` object:
1. Parse and validate `hat.json` → `HatManifest`
2. Load `constraints.json` → `dict`
3. Load `stakeholders.json` → `StakeholderRegistry`
4. Load `evaluator_config.json` → `EvaluatorConfig`
5. Load `prompts/*.txt` → `dict[str, str]`

### Equipping

`HatRegistry.equip(hat_name)`:
1. Unequip current hat (if any) — clears tool registry
2. Load the new hat from disk
3. Dynamically import and instantiate tools via `load_hat_tools()`
4. Register tools in the `ToolRegistry`
5. Rebuild pipeline components (InputGate, Proposer, Executor) with new hat context
6. Load hat's seed data into memory store

### Unequipping

`HatRegistry.unequip()`:
1. Clear all tools from the `ToolRegistry`
2. Set active hat to `None`

## Pydantic Models Reference

All models are defined in `sophia.hats.schema`:

- **`HatManifest`** — validated manifest structure
- **`EvaluatorConfig`** — evaluator tuning
- **`Stakeholder`** — single stakeholder definition
- **`StakeholderRegistry`** — collection of stakeholders
- **`HatConfig`** — fully loaded hat with all components, properties: `path`, `name`, `display_name`, `tools_module_path`
