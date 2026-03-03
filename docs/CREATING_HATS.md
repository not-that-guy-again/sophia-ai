# Creating Hats

This guide walks you through building a new Hat for Sophia. A Hat gives the agent a domain role — its tools, constraints, stakeholders, evaluator tuning, and prompt context all come from the Hat you create.

## Prerequisites

- A working Sophia installation (`uv sync`)
- Familiarity with the [Hat Specification](HAT_SPEC.md)
- Python 3.11+

## Quick Start

Create a directory under `hats/` with your Hat name:

```
hats/
└── my-domain/
    ├── hat.json              # Required: manifest
    ├── tools/                # Required: at least one tool module
    │   └── actions.py
    ├── constraints.json      # Recommended: domain rules
    ├── stakeholders.json     # Recommended: affected parties
    ├── evaluator_config.json # Optional: evaluator tuning
    └── prompts/              # Recommended: domain prompt fragments
        ├── system.txt
        ├── proposer.txt
        ├── consequence.txt
        ├── eval_self.txt
        ├── eval_tribal.txt
        ├── eval_domain.txt
        └── eval_authority.txt
```

## Step 1: Write the Manifest (`hat.json`)

The manifest identifies your Hat and declares its tools.

```json
{
  "name": "my-domain",
  "version": "0.1.0",
  "display_name": "My Domain",
  "description": "What this hat does, in one sentence.",
  "author": "your-name",
  "license": "Apache-2.0",
  "sophia_version": ">=0.1.0",
  "tools": [
    "do_thing",
    "check_status",
    "escalate"
  ],
  "default_evaluator_weights": {
    "tribal": 0.40,
    "domain": 0.25,
    "self_interest": 0.20,
    "authority": 0.15
  },
  "risk_thresholds": {
    "green": -0.1,
    "yellow": -0.4,
    "orange": -0.7
  }
}
```

**Key fields:**

- **`name`**: Must match the directory name. Lowercase, hyphen-separated.
- **`tools`**: List of tool names that this Hat makes available. Only tools listed here will be registered — any `Tool` subclass in your `tools/` directory whose `name` is not in this list will be ignored.
- **`default_evaluator_weights`**: How much each evaluator matters for this domain. Must sum to 1.0.
- **`risk_thresholds`**: Score boundaries between risk tiers. Scores above `green` → GREEN, between `green` and `yellow` → YELLOW, etc. Below `orange` → RED.

## Step 2: Implement Tools

Tools live in Python files under `tools/`. Each tool is a class that extends `sophia.tools.base.Tool`.

```python
# hats/my-domain/tools/actions.py

from sophia.tools.base import Tool, ToolResult


class DoThingTool(Tool):
    name = "do_thing"
    description = "Performs the primary action in this domain."
    parameters = {
        "type": "object",
        "properties": {
            "target_id": {
                "type": "string",
                "description": "The ID of the target to act on",
            },
            "reason": {
                "type": "string",
                "description": "Why this action is being taken",
            },
        },
        "required": ["target_id", "reason"],
    }
    authority_level = "agent"      # "agent", "supervisor", or "admin"
    max_financial_impact = 50.00   # None if not applicable

    async def execute(self, params: dict) -> ToolResult:
        target_id = params.get("target_id", "")
        # Your domain logic here
        return ToolResult(
            success=True,
            data={"target_id": target_id, "status": "completed"},
            message=f"Action completed for {target_id}",
        )
```

**Rules:**

- The `name` class attribute must match an entry in `hat.json`'s `tools` list.
- `parameters` follows JSON Schema format — this is shown to the LLM so it knows how to call the tool.
- `authority_level` indicates who can approve this action: `"agent"` (autonomous), `"supervisor"` (needs confirmation), `"admin"` (needs explicit authorization).
- `max_financial_impact` is used by evaluators to gauge risk. Set to `None` if the tool has no direct financial impact.
- Files starting with `_` (like `__init__.py`) are skipped during tool loading.
- You can put multiple tool classes in one file, or spread them across files — the loader scans all `.py` files in the directory.

## Step 3: Define Constraints (`constraints.json`)

Constraints encode the business rules and policies for your domain.

```json
{
  "business_name": "Acme Corp",
  "policies": {
    "max_agent_spend": 200.00,
    "require_verification": true,
    "allow_exceptions": false
  },
  "escalation_triggers": [
    "customer threatens legal action",
    "request exceeds agent authority"
  ],
  "hard_rules": [
    "Never bypass verification",
    "Never commit to timelines you cannot guarantee"
  ]
}
```

The structure is free-form — design it to match your domain. Constraints are loaded into the memory store and injected into pipeline prompts so the LLM understands what rules to follow.

## Step 4: Define Stakeholders (`stakeholders.json`)

Stakeholders are the parties affected by the agent's actions. The consequence engine and evaluators use these to assess impact.

```json
{
  "stakeholders": [
    {
      "id": "end_user",
      "name": "The End User",
      "interests": ["get help quickly", "accurate information", "fair treatment"],
      "harm_sensitivity": "medium",
      "weight": 0.35
    },
    {
      "id": "organization",
      "name": "The Organization",
      "interests": ["maintain reputation", "control costs", "comply with regulations"],
      "harm_sensitivity": "medium",
      "weight": 0.30
    },
    {
      "id": "community",
      "name": "The Broader Community",
      "interests": ["fair access", "no precedent abuse", "trust in the system"],
      "harm_sensitivity": "high",
      "weight": 0.20
    },
    {
      "id": "staff",
      "name": "Internal Staff",
      "interests": ["manageable workload", "clear accountability"],
      "harm_sensitivity": "medium",
      "weight": 0.15
    }
  ]
}
```

**Fields:**

- **`harm_sensitivity`**: `"low"`, `"medium"`, or `"high"`. High-sensitivity stakeholders trigger more cautious risk classification.
- **`weight`**: How much this stakeholder's outcomes matter relative to others. Should sum to ~1.0 across all stakeholders.

## Step 5: Tune Evaluators (`evaluator_config.json`)

Override the default evaluator behavior for your domain.

```json
{
  "weight_overrides": {
    "tribal": 0.40,
    "domain": 0.25,
    "self_interest": 0.20,
    "authority": 0.15
  },
  "custom_flags": {
    "domain": ["policy_violation", "unauthorized_action"],
    "authority": ["unverified_identity"],
    "tribal": ["sets_bad_precedent"]
  },
  "risk_thresholds": {
    "green": -0.1,
    "yellow": -0.4,
    "orange": -0.7
  }
}
```

**`custom_flags`** are domain-specific signals that evaluators can raise. When the consequence engine and evaluation panel are active (Phase 2-3), these flags trigger additional scrutiny.

## Step 6: Write Prompt Fragments (`prompts/`)

Prompt fragments are injected into the pipeline at each stage. They give the LLM domain-specific context beyond what the core framework provides.

| File | Pipeline Stage | Purpose |
|------|---------------|---------|
| `system.txt` | Input Gate | Role description and general behavior |
| `proposer.txt` | Proposer | Action proposal guidelines |
| `consequence.txt` | Consequence Engine | How to simulate outcomes (Phase 2) |
| `eval_self.txt` | Self-Interest Evaluator | Self-interest scoring context (Phase 3) |
| `eval_tribal.txt` | Tribal Evaluator | Community impact context (Phase 3) |
| `eval_domain.txt` | Domain Evaluator | Policy compliance context (Phase 3) |
| `eval_authority.txt` | Authority Evaluator | Authorization context (Phase 3) |

All files are optional. Missing files mean the core framework prompt is used without domain additions.

**Example `system.txt`:**

```
You are operating as a Support Agent for Acme Corp.

Your role is to help users with account management, billing inquiries, and
technical troubleshooting. Always be professional and solution-oriented.
```

**Example `proposer.txt`:**

```
When proposing actions:
- Always verify the user's identity before account changes
- Prefer self-service solutions when available
- Include an escalation option for complex issues
- Never propose actions that bypass security checks
```

## Step 7: Test Your Hat

### Verify Discovery

```python
from pathlib import Path
from sophia.hats.loader import discover_hats

manifests = discover_hats(Path("./hats"))
names = [m.name for m in manifests]
assert "my-domain" in names
```

### Verify Loading

```python
from sophia.hats.loader import load_hat, load_hat_tools

config = load_hat(Path("./hats/my-domain"))
assert config.name == "my-domain"
assert len(config.manifest.tools) > 0

tools = load_hat_tools(config)
assert len(tools) == len(config.manifest.tools)
```

### Verify Tool Execution

```python
import asyncio
from sophia.hats.loader import load_hat, load_hat_tools
from sophia.tools.registry import ToolRegistry

config = load_hat(Path("./hats/my-domain"))
registry = ToolRegistry()
for tool in load_hat_tools(config):
    registry.register(tool)

result = asyncio.run(registry.call("do_thing", {"target_id": "T-001", "reason": "test"}))
assert result.success
```

### Write Proper Tests

Create tests under `tests/` following the existing patterns:

```python
# tests/hats/test_my_domain.py

import pytest
from pathlib import Path
from sophia.hats.loader import load_hat, load_hat_tools

HAT_DIR = Path(__file__).resolve().parent.parent.parent / "hats" / "my-domain"


def test_hat_loads():
    config = load_hat(HAT_DIR)
    assert config.name == "my-domain"


def test_tools_load():
    config = load_hat(HAT_DIR)
    tools = load_hat_tools(config)
    names = {t.name for t in tools}
    for expected in config.manifest.tools:
        assert expected in names
```

## Equipping Your Hat

Once your Hat is in the `hats/` directory, equip it via the API:

```bash
# List available hats
curl http://localhost:8000/hats

# Equip your hat
curl -X POST http://localhost:8000/hats/my-domain/equip

# Verify
curl http://localhost:8000/hats/active
```

Or set it as the default in `.env`:

```
DEFAULT_HAT=my-domain
```

## Common Patterns

### Read-Only Tools

Tools that only look up information should have `max_financial_impact = None` and `authority_level = "agent"`.

### Destructive or Expensive Tools

Set `authority_level` to `"supervisor"` or `"admin"` and specify `max_financial_impact`. In Phase 2+, these will require confirmation or escalation.

### Escalation Tool

Every Hat should include a way to hand off to a human. This is a safety valve for edge cases the agent shouldn't handle autonomously.

```python
class EscalateToHumanTool(Tool):
    name = "escalate_to_human"
    description = "Escalate to a human agent when the request is beyond agent capability."
    parameters = {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "context_summary": {"type": "string"},
        },
        "required": ["reason", "priority", "context_summary"],
    }
    authority_level = "agent"
    max_financial_impact = None

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=True,
            data={"ticket_id": "ESC-001", "priority": params.get("priority")},
            message=f"Escalated: {params.get('reason')}",
        )
```

## Reference

- [Hat Specification](HAT_SPEC.md) — formal interface definition
- [Architecture](ARCHITECTURE.md) — how Hats fit into the pipeline
- `hats/customer-service/` — complete reference implementation
