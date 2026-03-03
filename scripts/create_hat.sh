#!/usr/bin/env bash
set -euo pipefail

# Sophia — Hat Scaffolding Script
# Creates a new hat directory from a template with all required files.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HATS_DIR="${REPO_ROOT}/hats"

usage() {
    echo "Usage: $0 <hat-name> [display-name]"
    echo ""
    echo "  hat-name      Lowercase, hyphen-separated (e.g., content-moderation)"
    echo "  display-name  Optional human-readable name (e.g., \"Content Moderation\")"
    echo ""
    echo "Example:"
    echo "  $0 content-moderation \"Content Moderation\""
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

HAT_NAME="$1"
DISPLAY_NAME="${2:-$HAT_NAME}"
HAT_DIR="${HATS_DIR}/${HAT_NAME}"

# Validate hat name
if [[ ! "$HAT_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
    echo "ERROR: Hat name must be lowercase, start with a letter, and use hyphens only."
    echo "       Got: ${HAT_NAME}"
    exit 1
fi

# Check for conflicts
if [ -d "$HAT_DIR" ]; then
    echo "ERROR: Hat directory already exists: ${HAT_DIR}"
    exit 1
fi

echo "=== Creating Hat: ${HAT_NAME} ==="
echo ""

# --- Create directory structure ---
mkdir -p "${HAT_DIR}/tools"
mkdir -p "${HAT_DIR}/prompts"
mkdir -p "${HAT_DIR}/seed"

# --- hat.json ---
cat > "${HAT_DIR}/hat.json" << EOF
{
  "name": "${HAT_NAME}",
  "version": "0.1.0",
  "display_name": "${DISPLAY_NAME}",
  "description": "",
  "author": "",
  "license": "Apache-2.0",
  "sophia_version": ">=0.1.0",
  "tools": [
    "example_action",
    "escalate_to_human"
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
EOF

# --- Starter tool ---
cat > "${HAT_DIR}/tools/actions.py" << 'TOOLEOF'
from sophia.tools.base import Tool, ToolResult


class ExampleActionTool(Tool):
    name = "example_action"
    description = "Example tool — replace with your domain action."
    parameters = {
        "type": "object",
        "properties": {
            "target_id": {
                "type": "string",
                "description": "The target to act on",
            },
        },
        "required": ["target_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    async def execute(self, params: dict) -> ToolResult:
        target_id = params.get("target_id", "")
        return ToolResult(
            success=True,
            data={"target_id": target_id, "status": "completed"},
            message=f"Action completed for {target_id}",
        )
TOOLEOF

# --- Escalation tool ---
cat > "${HAT_DIR}/tools/escalation.py" << 'TOOLEOF'
from sophia.tools.base import Tool, ToolResult


class EscalateToHumanTool(Tool):
    name = "escalate_to_human"
    description = "Escalate to a human when the request is beyond agent capability."
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why this needs human review",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Escalation priority",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary of the situation for the human agent",
            },
        },
        "required": ["reason", "priority", "context_summary"],
    }
    authority_level = "agent"
    max_financial_impact = None

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "ticket_id": "ESC-001",
                "priority": params.get("priority", "medium"),
            },
            message=f"Escalated: {params.get('reason', 'No reason provided')}",
        )
TOOLEOF

# --- constraints.json ---
cat > "${HAT_DIR}/constraints.json" << EOF
{
  "business_name": "",
  "policies": {},
  "escalation_triggers": [],
  "hard_rules": []
}
EOF

# --- stakeholders.json ---
cat > "${HAT_DIR}/stakeholders.json" << EOF
{
  "stakeholders": [
    {
      "id": "end_user",
      "name": "The End User",
      "interests": ["get help", "fair treatment"],
      "harm_sensitivity": "medium",
      "weight": 0.35
    },
    {
      "id": "organization",
      "name": "The Organization",
      "interests": ["maintain reputation", "follow policies"],
      "harm_sensitivity": "medium",
      "weight": 0.30
    },
    {
      "id": "community",
      "name": "The Broader Community",
      "interests": ["fair access", "trust in the system"],
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
EOF

# --- evaluator_config.json ---
cat > "${HAT_DIR}/evaluator_config.json" << EOF
{
  "weight_overrides": {},
  "custom_flags": {
    "domain": [],
    "authority": [],
    "tribal": []
  },
  "risk_thresholds": {}
}
EOF

# --- Prompt fragments ---
cat > "${HAT_DIR}/prompts/system.txt" << EOF
You are operating as a ${DISPLAY_NAME} agent.

Describe the agent's role, responsibilities, and general behavior here.
EOF

cat > "${HAT_DIR}/prompts/proposer.txt" << EOF
When proposing actions for ${DISPLAY_NAME} requests:
- Add domain-specific proposal guidelines here
- Include an escalation option for complex or risky requests
EOF

cat > "${HAT_DIR}/prompts/consequence.txt" << EOF
When simulating consequences for ${DISPLAY_NAME} actions:
- Add domain-specific consequence modeling guidelines here
EOF

cat > "${HAT_DIR}/prompts/eval_self.txt" << EOF
When evaluating self-interest for ${DISPLAY_NAME} actions:
- Add domain-specific self-interest evaluation context here
EOF

cat > "${HAT_DIR}/prompts/eval_tribal.txt" << EOF
When evaluating community/tribal impact for ${DISPLAY_NAME} actions:
- Add domain-specific community impact evaluation context here
EOF

cat > "${HAT_DIR}/prompts/eval_domain.txt" << EOF
When evaluating domain rule compliance for ${DISPLAY_NAME} actions:
- Add domain-specific policy compliance evaluation context here
EOF

cat > "${HAT_DIR}/prompts/eval_authority.txt" << EOF
When evaluating authority and authorization for ${DISPLAY_NAME} actions:
- Add domain-specific authority validation context here
EOF

echo "[ok] Created ${HAT_DIR}/"
echo ""
echo "Files created:"
find "${HAT_DIR}" -type f | sort | sed "s|${HATS_DIR}/||"
echo ""
echo "Next steps:"
echo "  1. Edit hat.json — add your tool names and description"
echo "  2. Replace the example tools in tools/ with your domain tools"
echo "  3. Fill in constraints.json with your domain rules"
echo "  4. Define stakeholders in stakeholders.json"
echo "  5. Write prompt fragments in prompts/"
echo "  6. Test: uv run pytest"
echo "  7. Equip: curl -X POST http://localhost:8000/hats/${HAT_NAME}/equip"
echo ""
