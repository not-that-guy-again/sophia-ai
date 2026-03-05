"""Deterministic escalation trigger gate.

Checks the user message against hat-defined escalation triggers.
If matched, floors the minimum risk tier (default ORANGE, configurable per trigger).
"""

from dataclasses import dataclass

# Words to skip when extracting keywords from trigger strings.
# Includes standard stopwords plus operator-perspective framing words
# (triggers are written as "customer threatens X" — "customer" and "threatens"
# describe the reporter's framing, not the content to match).
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "have",
        "been",
        "will",
        "when",
        "what",
        "your",
        "their",
        # Operator-perspective framing words
        "customer",
        "agent",
        "claims",
        "threatens",
        "requests",
        "involves",
        "exceeds",
        "over",
    }
)

_MIN_KEYWORD_LEN = 4


@dataclass
class EscalationTriggerResult:
    triggered: bool
    matched_trigger: str | None
    min_tier: str  # "ORANGE" or "RED" if triggered, "GREEN" if not
    inherited: bool = False


def _extract_keywords(trigger: str) -> list[str]:
    """Extract significant keywords (4+ chars, not stopwords) from a trigger string."""
    return [
        word
        for word in trigger.lower().split()
        if len(word) >= _MIN_KEYWORD_LEN and word not in _STOPWORDS
    ]


def _matches_trigger(message: str, trigger: str) -> bool:
    """Check if a message matches a trigger via keyword decomposition.

    All significant keywords from the trigger must appear as substrings
    in the lowercased message.
    """
    keywords = _extract_keywords(trigger)
    if not keywords:
        return False
    message_lower = message.lower()
    return all(kw in message_lower for kw in keywords)


def _get_trigger_min_tier(trigger: str, constraints: dict) -> str:
    """Return the minimum tier for a matched trigger. Defaults to ORANGE."""
    severity_map = constraints.get("escalation_trigger_severity", {})
    return severity_map.get(trigger, "ORANGE")


def check_escalation_triggers(
    message: str,
    constraints: dict,
    conversation_history: list[dict] | None = None,
) -> EscalationTriggerResult:
    """Check message against escalation triggers from constraints.

    For each trigger, extract keywords (4+ chars, not stopwords) and require
    ALL keywords to appear in the lowercased message. Returns on first match.

    If conversation_history is provided, also checks prior user turns for
    inherited escalation (e.g., a legal threat from an earlier turn carries
    forward to subsequent turns in the same conversation).
    """
    triggers = constraints.get("escalation_triggers", [])
    if not triggers:
        return EscalationTriggerResult(triggered=False, matched_trigger=None, min_tier="GREEN")

    # Check current message first
    for trigger in triggers:
        if _matches_trigger(message, trigger):
            return EscalationTriggerResult(
                triggered=True,
                matched_trigger=trigger,
                min_tier=_get_trigger_min_tier(trigger, constraints),
                inherited=False,
            )

    # Check prior user turns for inherited escalation floor
    if conversation_history:
        for turn in conversation_history:
            if turn.get("role") != "user":
                continue
            prior_message = turn.get("content", "")
            for trigger in triggers:
                if _matches_trigger(prior_message, trigger):
                    return EscalationTriggerResult(
                        triggered=True,
                        matched_trigger=trigger,
                        min_tier=_get_trigger_min_tier(trigger, constraints),
                        inherited=True,
                    )

    return EscalationTriggerResult(triggered=False, matched_trigger=None, min_tier="GREEN")
