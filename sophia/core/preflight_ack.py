"""Pre-flight acknowledgment (ADR-021).

Deterministic, template-based acknowledgment message that fires after the
parameter gate and before the consequence engine. Provides immediate feedback
to the user while the full pipeline runs.
"""

import logging
import random
import re

from sophia.core.input_gate import Intent
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CONVERSE_TOOL_NAME = "converse"

CORE_DEFAULT_ACK = "One moment while I look into that."


def maybe_generate_ack(
    intent: Intent,
    candidates: list[CandidateAction],
    tool_registry: ToolRegistry,
    hat_config: HatConfig | None,
) -> str | None:
    """Generate a preflight acknowledgment message, or None if skipped.

    Returns None when any skip condition is met:
    - All candidates are converse (no tool execution ahead)
    - Top non-converse tool not found in registry
    - Tool authority_level is not "agent"
    - Tool max_financial_impact exceeds hat's ack_financial_ceiling
    - Hat has ack_enabled set to False
    """
    # 1. Filter to non-converse candidates
    non_converse = [c for c in candidates if c.tool_name != CONVERSE_TOOL_NAME]
    if not non_converse:
        return None

    # 2. Get the top non-converse candidate's tool
    top = non_converse[0]
    tool = tool_registry.get(top.tool_name)
    if tool is None:
        return None

    # 3. Authority check
    if tool.authority_level != "agent":
        return None

    # Read hat config values from raw_manifest
    raw = hat_config.raw_manifest if hat_config else {}

    # 4. Financial impact check
    ceiling = raw.get("ack_financial_ceiling", 0.0)
    if tool.max_financial_impact is not None and tool.max_financial_impact > ceiling:
        return None

    # 5. Hat master switch
    if not raw.get("ack_enabled", True):
        return None

    # 6. Template selection
    templates = raw.get("ack_templates", {})
    action = intent.action_requested
    if action in templates:
        template_list = templates[action]
    elif "_default" in templates:
        template_list = templates["_default"]
    else:
        template_list = None

    if template_list:
        template = random.choice(template_list)
    else:
        template = CORE_DEFAULT_ACK

    # 7. Slot fill
    rendered = _slot_fill(template, intent.parameters)

    return rendered


def _slot_fill(template: str, parameters: dict) -> str:
    """Replace {key} placeholders with values from parameters.

    Missing keys are removed and surrounding artifacts cleaned up.
    """

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        value = parameters.get(key)
        if value is not None and str(value).strip():
            return str(value)
        return ""

    result = re.sub(r"\{(\w+)\}", replacer, template)

    # Clean up artifacts from removed placeholders:
    # - collapse multiple spaces
    result = re.sub(r"  +", " ", result)
    # - remove orphaned prepositions/articles before end of sentence or punctuation
    result = re.sub(r"\b(for|of|on|to|the|a|an|order|your)\s+([.!?])", r"\2", result)
    # - trim spaces around punctuation
    result = re.sub(r"\s+([.!?,])", r"\1", result)
    # - strip leading/trailing whitespace
    result = result.strip()

    return result
