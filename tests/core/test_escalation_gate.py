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
