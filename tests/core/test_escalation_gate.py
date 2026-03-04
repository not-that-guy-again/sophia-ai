"""Tests for the deterministic escalation trigger gate."""

from sophia.core.escalation_gate import check_escalation_triggers


# Load the real customer-service constraints for realistic testing
CS_CONSTRAINTS = {
    "escalation_triggers": [
        "customer threatens legal action",
        "refund amount exceeds agent authority",
        "customer claims injury or safety issue",
        "request involves multiple orders over $200 total",
        "customer requests to speak with manager",
    ]
}


def test_legal_threat_matches():
    result = check_escalation_triggers(
        "I'm going to take legal action against you",
        CS_CONSTRAINTS,
    )
    assert result.triggered is True
    assert result.min_tier == "ORANGE"
    assert result.matched_trigger == "customer threatens legal action"


def test_manager_request_matches():
    result = check_escalation_triggers(
        "I want to speak with a manager",
        CS_CONSTRAINTS,
    )
    assert result.triggered is True
    assert result.matched_trigger == "customer requests to speak with manager"


def test_injury_claim_matches():
    result = check_escalation_triggers(
        "This product caused me injury and I have a safety issue",
        CS_CONSTRAINTS,
    )
    assert result.triggered is True
    assert result.matched_trigger == "customer claims injury or safety issue"


def test_normal_message_no_match():
    result = check_escalation_triggers(
        "I'd like a refund on my order",
        CS_CONSTRAINTS,
    )
    assert result.triggered is False
    assert result.matched_trigger is None
    assert result.min_tier == "GREEN"


def test_empty_triggers_list():
    result = check_escalation_triggers(
        "I'm going to take legal action against you",
        {"escalation_triggers": []},
    )
    assert result.triggered is False
    assert result.matched_trigger is None


def test_case_insensitive():
    result = check_escalation_triggers(
        "I WILL TAKE LEGAL ACTION AGAINST YOUR COMPANY",
        CS_CONSTRAINTS,
    )
    assert result.triggered is True


def test_partial_keyword_no_match():
    """Message with only some keywords from a trigger should not match."""
    result = check_escalation_triggers(
        "I have a legal question about my order",
        CS_CONSTRAINTS,
    )
    # "legal" alone matches but "action" is missing from "customer threatens legal action"
    # and other triggers don't match either
    assert result.triggered is False


def test_missing_constraints_key():
    """Constraints dict without escalation_triggers key."""
    result = check_escalation_triggers(
        "I'm going to take legal action",
        {"policies": {}},
    )
    assert result.triggered is False


# --- Conversation history (inherited escalation) tests ---


def test_inherited_escalation_from_prior_turn():
    """Current message has no trigger, but prior user turn has legal threat → inherited."""
    result = check_escalation_triggers(
        "So what are you going to do about it?",
        CS_CONSTRAINTS,
        conversation_history=[
            {"role": "user", "content": "I will take legal action against you"},
            {"role": "assistant", "content": "I understand your concern."},
        ],
    )
    assert result.triggered is True
    assert result.inherited is True
    assert result.matched_trigger == "customer threatens legal action"


def test_inherited_escalation_not_triggered_if_no_prior_match():
    """No triggers in current message or prior turns → not triggered."""
    result = check_escalation_triggers(
        "What is your return policy?",
        CS_CONSTRAINTS,
        conversation_history=[
            {"role": "user", "content": "Hello, I have a question about my order."},
            {"role": "assistant", "content": "Sure, how can I help?"},
        ],
    )
    assert result.triggered is False
    assert result.inherited is False


def test_current_message_takes_priority_over_history():
    """Current message matches trigger A, prior turn matches trigger B → current wins."""
    result = check_escalation_triggers(
        "I want to speak with a manager right now",
        CS_CONSTRAINTS,
        conversation_history=[
            {"role": "user", "content": "I will take legal action against you"},
        ],
    )
    assert result.triggered is True
    assert result.inherited is False
    assert result.matched_trigger == "customer requests to speak with manager"


def test_empty_conversation_history():
    """conversation_history=[] behaves same as None."""
    result = check_escalation_triggers(
        "What is your return policy?",
        CS_CONSTRAINTS,
        conversation_history=[],
    )
    assert result.triggered is False
    assert result.inherited is False


# --- Per-trigger minimum tier tests ---


CS_CONSTRAINTS_WITH_SEVERITY = {
    **CS_CONSTRAINTS,
    "escalation_trigger_severity": {
        "customer threatens legal action": "RED",
    },
}


def test_legal_threat_trigger_floors_to_red():
    """Legal threat trigger with severity map → min_tier is RED."""
    result = check_escalation_triggers(
        "I'm going to take legal action against you",
        CS_CONSTRAINTS_WITH_SEVERITY,
    )
    assert result.triggered is True
    assert result.min_tier == "RED"
    assert result.matched_trigger == "customer threatens legal action"


def test_default_trigger_floors_to_orange():
    """Trigger not in severity map → min_tier defaults to ORANGE."""
    result = check_escalation_triggers(
        "I want to speak with a manager",
        CS_CONSTRAINTS_WITH_SEVERITY,
    )
    assert result.triggered is True
    assert result.min_tier == "ORANGE"


def test_inherited_trigger_uses_severity_map():
    """Inherited trigger for legal action → min_tier is RED via severity map."""
    result = check_escalation_triggers(
        "So what are you going to do about it?",
        CS_CONSTRAINTS_WITH_SEVERITY,
        conversation_history=[
            {"role": "user", "content": "I will take legal action against you"},
        ],
    )
    assert result.triggered is True
    assert result.inherited is True
    assert result.min_tier == "RED"


def test_missing_severity_map_defaults_to_orange():
    """Constraints with no escalation_trigger_severity → all triggers default to ORANGE."""
    result = check_escalation_triggers(
        "I'm going to take legal action against you",
        CS_CONSTRAINTS,  # no severity map
    )
    assert result.triggered is True
    assert result.min_tier == "ORANGE"


def test_only_user_turns_checked_for_inheritance():
    """Prior assistant turn with trigger keywords → not matched (only user turns count)."""
    result = check_escalation_triggers(
        "OK thanks",
        CS_CONSTRAINTS,
        conversation_history=[
            {"role": "assistant", "content": "You mentioned legal action earlier."},
        ],
    )
    assert result.triggered is False
    assert result.inherited is False
