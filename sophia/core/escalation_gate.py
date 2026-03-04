"""Deterministic escalation trigger gate.

Checks the user message against hat-defined escalation triggers.
If matched, floors the minimum risk tier to ORANGE.
"""

from dataclasses import dataclass

# Words to skip when extracting keywords from trigger strings.
# Includes standard stopwords plus operator-perspective framing words
# (triggers are written as "customer threatens X" — "customer" and "threatens"
# describe the reporter's framing, not the content to match).
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "with",
    "that", "this", "from", "into", "have", "been",
    "will", "when", "what", "your", "their",
    # Operator-perspective framing words
    "customer", "agent", "claims", "threatens",
    "requests", "involves", "exceeds", "over",
})

_MIN_KEYWORD_LEN = 4


@dataclass
class EscalationTriggerResult:
    triggered: bool
    matched_trigger: str | None
    min_tier: str  # "ORANGE" if triggered, "GREEN" if not


def _extract_keywords(trigger: str) -> list[str]:
    """Extract significant keywords (4+ chars, not stopwords) from a trigger string."""
    return [
        word
        for word in trigger.lower().split()
        if len(word) >= _MIN_KEYWORD_LEN and word not in _STOPWORDS
    ]


def check_escalation_triggers(
    message: str,
    constraints: dict,
) -> EscalationTriggerResult:
    """Check message against escalation triggers from constraints.

    For each trigger, extract keywords (4+ chars, not stopwords) and require
    ALL keywords to appear in the lowercased message. Returns on first match.
    """
    triggers = constraints.get("escalation_triggers", [])
    message_lower = message.lower()

    for trigger in triggers:
        keywords = _extract_keywords(trigger)
        if not keywords:
            continue
        if all(kw in message_lower for kw in keywords):
            return EscalationTriggerResult(
                triggered=True,
                matched_trigger=trigger,
                min_tier="ORANGE",
            )

    return EscalationTriggerResult(
        triggered=False,
        matched_trigger=None,
        min_tier="GREEN",
    )
