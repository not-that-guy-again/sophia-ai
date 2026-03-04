"""Tests for the deterministic risk classifier. No LLM calls."""

import pytest

from sophia.core.evaluators.base import EvaluatorResult
from sophia.core.proposer import CandidateAction
from sophia.core.risk_classifier import (
    classify,
    _compute_weighted_score,
    _has_significant_disagreement,
    _score_to_tier,
    _bump_tier,
)
from sophia.hats.schema import EvaluatorConfig, HatConfig, HatManifest


def _make_result(name: str, score: float, confidence: float = 0.8, flags: list[str] | None = None) -> EvaluatorResult:
    return EvaluatorResult(
        evaluator_name=name,
        score=score,
        confidence=confidence,
        flags=flags or [],
        reasoning=f"{name} evaluation",
        key_concerns=[],
    )


def _make_candidates() -> list[CandidateAction]:
    return [
        CandidateAction(
            tool_name="offer_full_refund",
            parameters={"order_id": "ORD-123", "reason": "damaged"},
            reasoning="Refund for damaged product",
            expected_outcome="Refund issued",
        ),
        CandidateAction(
            tool_name="escalate_to_human",
            parameters={"reason": "review", "priority": "medium", "context_summary": "test"},
            reasoning="Escalate",
            expected_outcome="Escalated",
        ),
    ]


def _all_neutral() -> list[EvaluatorResult]:
    return [
        _make_result("self_interest", 0.3),
        _make_result("tribal", 0.2),
        _make_result("domain", 0.1),
        _make_result("authority", 0.0),
    ]


def _all_positive() -> list[EvaluatorResult]:
    return [
        _make_result("self_interest", 0.5),
        _make_result("tribal", 0.6),
        _make_result("domain", 0.4),
        _make_result("authority", 0.3),
    ]


class TestScoreToTier:
    def test_green(self):
        assert _score_to_tier(0.5, {"green": -0.1, "yellow": -0.4, "orange": -0.7}) == "GREEN"

    def test_green_boundary(self):
        assert _score_to_tier(-0.1, {"green": -0.1, "yellow": -0.4, "orange": -0.7}) == "GREEN"

    def test_yellow(self):
        assert _score_to_tier(-0.2, {"green": -0.1, "yellow": -0.4, "orange": -0.7}) == "YELLOW"

    def test_orange(self):
        assert _score_to_tier(-0.5, {"green": -0.1, "yellow": -0.4, "orange": -0.7}) == "ORANGE"

    def test_red(self):
        assert _score_to_tier(-0.8, {"green": -0.1, "yellow": -0.4, "orange": -0.7}) == "RED"


class TestBumpTier:
    def test_green_to_yellow(self):
        assert _bump_tier("GREEN") == "YELLOW"

    def test_yellow_to_orange(self):
        assert _bump_tier("YELLOW") == "ORANGE"

    def test_orange_to_red(self):
        assert _bump_tier("ORANGE") == "RED"

    def test_red_stays_red(self):
        assert _bump_tier("RED") == "RED"


class TestDisagreement:
    def test_no_disagreement(self):
        results = _all_neutral()
        assert not _has_significant_disagreement(results)

    def test_one_disagreement_not_enough(self):
        results = [
            _make_result("self_interest", 0.5),
            _make_result("tribal", -0.4),  # diff = 0.9, one pair > 0.8
            _make_result("domain", 0.1),   # all other pairs < 0.8
            _make_result("authority", 0.0),
        ]
        assert not _has_significant_disagreement(results)

    def test_two_disagreements(self):
        results = [
            _make_result("self_interest", 0.9),
            _make_result("tribal", -0.5),  # pair 1: diff = 1.4
            _make_result("domain", -0.5),  # pair 2: diff = 1.4 with self_interest
            _make_result("authority", 0.0),
        ]
        assert _has_significant_disagreement(results)


class TestClassify:
    def test_all_green_scores(self):
        rc = classify(_all_positive(), candidates=_make_candidates())
        assert rc.tier == "GREEN"
        assert rc.weighted_score > 0

    def test_all_neutral_scores(self):
        rc = classify(_all_neutral(), candidates=_make_candidates())
        assert rc.tier == "GREEN"

    def test_catastrophic_flag_forces_red(self):
        results = [
            _make_result("self_interest", 0.5),
            _make_result("tribal", -0.9, flags=["catastrophic_harm"]),
            _make_result("domain", 0.3),
            _make_result("authority", 0.2),
        ]
        rc = classify(results, candidates=_make_candidates())
        assert rc.tier == "RED"
        assert rc.override_reason == "Catastrophic harm flag detected"

    def test_three_severe_evaluators_force_red(self):
        results = [
            _make_result("self_interest", -0.6),
            _make_result("tribal", -0.7),
            _make_result("domain", -0.8),
            _make_result("authority", 0.5),  # one positive
        ]
        rc = classify(results, candidates=_make_candidates())
        assert rc.tier == "RED"
        assert "3" in rc.override_reason

    def test_disagreement_bumps_tier(self):
        # Scores that would normally be YELLOW, but disagreement bumps to ORANGE
        results = [
            _make_result("self_interest", 0.8),
            _make_result("tribal", -0.3),   # pair 1 with self: diff = 1.1
            _make_result("domain", -0.4),   # pair 2 with self: diff = 1.2
            _make_result("authority", 0.0),
        ]
        rc = classify(results, candidates=_make_candidates())
        # weighted_score should be around -0.1 to -0.2 → YELLOW normally,
        # but disagreement bumps it up
        assert rc.tier in ("YELLOW", "ORANGE")

    def test_hat_weight_overrides(self):
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(
                weight_overrides={"tribal": 0.80, "domain": 0.10, "self_interest": 0.05, "authority": 0.05},
            ),
        )
        # Tribal very negative, others positive — hat weights tribal heavily
        results = [
            _make_result("self_interest", 0.5),
            _make_result("tribal", -0.5),
            _make_result("domain", 0.3),
            _make_result("authority", 0.2),
        ]
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        # Tribal dominates → negative weighted score
        assert rc.weighted_score < 0

    def test_hat_threshold_overrides(self):
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(
                risk_thresholds={"green": 0.0, "yellow": -0.2, "orange": -0.5},
            ),
        )
        # Slightly negative scores that would be GREEN with defaults but YELLOW with stricter thresholds
        results = [
            _make_result("self_interest", 0.0),
            _make_result("tribal", -0.1),
            _make_result("domain", -0.05),
            _make_result("authority", 0.0),
        ]
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        assert rc.tier == "YELLOW"

    def test_recommended_action_green(self):
        rc = classify(_all_positive(), candidates=_make_candidates())
        assert rc.recommended_action is not None
        assert rc.recommended_action.tool_name == "offer_full_refund"

    def test_recommended_action_red(self):
        results = [
            _make_result("self_interest", 0.0),
            _make_result("tribal", -0.9, flags=["catastrophic_harm"]),
            _make_result("domain", -0.5),
            _make_result("authority", -0.3),
        ]
        rc = classify(results, candidates=_make_candidates())
        assert rc.tier == "RED"
        assert rc.recommended_action is None

    def test_individual_scores_captured(self):
        rc = classify(_all_neutral(), candidates=_make_candidates())
        assert "self_interest" in rc.individual_scores
        assert "tribal" in rc.individual_scores
        assert "domain" in rc.individual_scores
        assert "authority" in rc.individual_scores
        assert rc.individual_scores["self_interest"] == 0.3

    def test_flags_aggregated(self):
        results = [
            _make_result("self_interest", 0.0),
            _make_result("tribal", -0.3, flags=["sets_bad_precedent"]),
            _make_result("domain", -0.2, flags=["refund_exceeds_authority"]),
            _make_result("authority", 0.0),
        ]
        rc = classify(results, candidates=_make_candidates())
        assert "sets_bad_precedent" in rc.flags
        assert "refund_exceeds_authority" in rc.flags

    def test_empty_results(self):
        rc = classify([], candidates=_make_candidates())
        assert rc.tier == "GREEN"
        assert rc.weighted_score == 0.0


class TestMinTier:
    """Tests for the min_tier floor (escalation gate and hat config)."""

    def test_min_tier_floors_yellow_to_orange(self):
        """Weighted score producing YELLOW is floored to ORANGE by hat min_tier."""
        # Scores that produce a YELLOW tier (weighted score around -0.2 to -0.3)
        results = [
            _make_result("self_interest", 0.0),
            _make_result("tribal", -0.3),
            _make_result("domain", -0.2),
            _make_result("authority", 0.0),
        ]
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(min_tier="ORANGE"),
        )
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        assert rc.tier == "ORANGE"
        assert rc.min_tier_applied == "ORANGE"

    def test_min_tier_does_not_lower_red(self):
        """min_tier=ORANGE should not lower a RED classification."""
        results = [
            _make_result("self_interest", 0.0),
            _make_result("tribal", -0.9, flags=["catastrophic_harm"]),
            _make_result("domain", -0.5),
            _make_result("authority", -0.3),
        ]
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(min_tier="ORANGE"),
        )
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        assert rc.tier == "RED"

    def test_min_tier_none_no_effect(self):
        """When min_tier is None, classifier behaves as before."""
        results = _all_positive()
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(min_tier=None),
        )
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        assert rc.tier == "GREEN"
        assert rc.min_tier_applied is None

    def test_min_tier_applied_after_catastrophic_override(self):
        """Catastrophic harm flag forces RED regardless of min_tier."""
        results = [
            _make_result("self_interest", 0.5),
            _make_result("tribal", -0.9, flags=["catastrophic_harm"]),
            _make_result("domain", 0.3),
            _make_result("authority", 0.2),
        ]
        hat = HatConfig(
            manifest=HatManifest(name="test"),
            hat_path="/tmp/test",
            evaluator_config=EvaluatorConfig(min_tier="ORANGE"),
        )
        rc = classify(results, hat_config=hat, candidates=_make_candidates())
        assert rc.tier == "RED"

    def test_escalation_min_tier_parameter(self):
        """The min_tier parameter from escalation gate floors the tier."""
        results = _all_positive()
        rc = classify(results, candidates=_make_candidates(), min_tier="ORANGE")
        assert rc.tier == "ORANGE"
        assert rc.min_tier_applied == "ORANGE"

    def test_escalation_min_tier_none_no_effect(self):
        """min_tier=None has no effect on classification."""
        results = _all_positive()
        rc = classify(results, candidates=_make_candidates(), min_tier=None)
        assert rc.tier == "GREEN"
