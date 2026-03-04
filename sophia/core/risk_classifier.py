"""Deterministic risk classifier. No LLM calls.

Takes four EvaluatorResults + hat config, produces a RiskClassification
with tier (GREEN/YELLOW/ORANGE/RED) and routing decision.
"""

import logging
from dataclasses import dataclass, field

from sophia.core.evaluators.base import EvaluatorResult
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig

logger = logging.getLogger(__name__)

# Default evaluator weights (used when hat has no overrides)
DEFAULT_WEIGHTS = {
    "tribal": 0.40,
    "domain": 0.25,
    "self_interest": 0.20,
    "authority": 0.15,
}

# Default risk tier thresholds
DEFAULT_THRESHOLDS = {
    "green": -0.1,
    "yellow": -0.4,
    "orange": -0.7,
}

# Tier ordering for bump logic
TIER_ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]


@dataclass
class RiskClassification:
    tier: str  # GREEN, YELLOW, ORANGE, RED
    weighted_score: float
    individual_scores: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    override_reason: str | None = None
    recommended_action: CandidateAction | None = None
    explanation: str = ""
    min_tier_applied: str | None = None


def classify(
    results: list[EvaluatorResult],
    hat_config: HatConfig | None = None,
    candidates: list[CandidateAction] | None = None,
    min_tier: str | None = None,
) -> RiskClassification:
    """Classify risk from evaluator results. Deterministic, no LLM.

    Override rules (core safety, not hat-configurable):
      - Any "catastrophic_harm" flag → RED
      - 3+ evaluators scoring below -0.5 → RED
      - 2+ evaluators disagreeing by >0.8 → bump tier up one level
    """
    candidates = candidates or []
    all_flags = []
    individual_scores: dict[str, float] = {}

    for r in results:
        individual_scores[r.evaluator_name] = r.score
        all_flags.extend(r.flags)

    # --- Override 1: catastrophic_harm flag → RED ---
    if "catastrophic_harm" in all_flags:
        return RiskClassification(
            tier="RED",
            weighted_score=_compute_weighted_score(results, hat_config),
            individual_scores=individual_scores,
            flags=all_flags,
            override_reason="Catastrophic harm flag detected",
            recommended_action=None,
            explanation=_build_explanation(results, "RED", "Catastrophic harm flag triggered automatic RED."),
        )

    # --- Override 2: 3+ evaluators below -0.5 → RED ---
    severe_count = sum(1 for r in results if r.score <= -0.5)
    if severe_count >= 3:
        return RiskClassification(
            tier="RED",
            weighted_score=_compute_weighted_score(results, hat_config),
            individual_scores=individual_scores,
            flags=all_flags,
            override_reason=f"{severe_count} evaluators scored below -0.5",
            recommended_action=None,
            explanation=_build_explanation(
                results, "RED", f"{severe_count} of {len(results)} evaluators flagged severe concerns."
            ),
        )

    # --- Compute weighted score ---
    weighted_score = _compute_weighted_score(results, hat_config)

    # --- Map to tier via thresholds ---
    thresholds = DEFAULT_THRESHOLDS.copy()
    if hat_config:
        # Hat can override via evaluator_config.risk_thresholds or manifest.risk_thresholds
        hat_thresholds = hat_config.evaluator_config.risk_thresholds
        if not hat_thresholds:
            hat_thresholds = hat_config.manifest.risk_thresholds
        if hat_thresholds:
            thresholds.update(hat_thresholds)

    tier = _score_to_tier(weighted_score, thresholds)

    # --- Override 3: evaluator disagreement bumps tier up ---
    if _has_significant_disagreement(results):
        original_tier = tier
        tier = _bump_tier(tier)
        if tier != original_tier:
            logger.info(
                "Evaluator disagreement: bumped tier from %s to %s",
                original_tier,
                tier,
            )

    # --- Apply minimum tier floor (from escalation gate) ---
    min_tier_applied = None
    if min_tier and TIER_ORDER.index(tier) < TIER_ORDER.index(min_tier):
        logger.info("Minimum tier floor %s applied (was %s)", min_tier, tier)
        tier = min_tier
        min_tier_applied = min_tier

    # --- Apply hat-configured minimum tier floor ---
    if hat_config and hat_config.evaluator_config.min_tier:
        hat_min = hat_config.evaluator_config.min_tier
        if TIER_ORDER.index(tier) < TIER_ORDER.index(hat_min):
            logger.info("Hat min_tier floor %s applied (was %s)", hat_min, tier)
            tier = hat_min
            min_tier_applied = hat_min

    # --- Select recommended action ---
    recommended = _select_recommended_action(tier, candidates)

    return RiskClassification(
        tier=tier,
        weighted_score=weighted_score,
        individual_scores=individual_scores,
        flags=all_flags,
        override_reason=None,
        recommended_action=recommended,
        explanation=_build_explanation(results, tier),
        min_tier_applied=min_tier_applied,
    )


def _compute_weighted_score(
    results: list[EvaluatorResult],
    hat_config: HatConfig | None,
) -> float:
    """Compute weighted score using hat weight overrides or defaults."""
    weights = DEFAULT_WEIGHTS.copy()

    if hat_config:
        overrides = hat_config.evaluator_config.weight_overrides
        if not overrides:
            overrides = hat_config.manifest.default_evaluator_weights
        if overrides:
            weights.update(overrides)

    total = 0.0
    weight_sum = 0.0

    for r in results:
        w = weights.get(r.evaluator_name, 0.0)
        total += r.score * w
        weight_sum += w

    if weight_sum == 0.0:
        return 0.0
    return total / weight_sum


def _score_to_tier(score: float, thresholds: dict[str, float]) -> str:
    """Map a weighted score to a risk tier."""
    if score >= thresholds.get("green", -0.1):
        return "GREEN"
    if score >= thresholds.get("yellow", -0.4):
        return "YELLOW"
    if score >= thresholds.get("orange", -0.7):
        return "ORANGE"
    return "RED"


def _has_significant_disagreement(results: list[EvaluatorResult]) -> bool:
    """Check if 2+ evaluators disagree by more than 0.8."""
    disagreements = 0
    scores = [r.score for r in results]
    for i in range(len(scores)):
        for j in range(i + 1, len(scores)):
            if abs(scores[i] - scores[j]) > 0.8:
                disagreements += 1
    return disagreements >= 2


def _bump_tier(tier: str) -> str:
    """Bump a tier up one level (more cautious). RED stays RED."""
    idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]


def _select_recommended_action(
    tier: str,
    candidates: list[CandidateAction],
) -> CandidateAction | None:
    """Select the recommended action based on risk tier."""
    if not candidates:
        return None

    if tier in ("GREEN", "YELLOW"):
        return candidates[0]

    if tier == "ORANGE":
        # Look for escalate_to_human among candidates
        for c in candidates:
            if c.tool_name == "escalate_to_human":
                return c
        return candidates[0]  # fallback to top candidate

    # RED — no recommended action
    return None


def _build_explanation(
    results: list[EvaluatorResult],
    tier: str,
    prefix: str = "",
) -> str:
    """Build a human-readable explanation from evaluator results."""
    parts = []
    if prefix:
        parts.append(prefix)

    parts.append(f"Risk tier: {tier}")

    for r in results:
        summary = f"  {r.evaluator_name}: score={r.score:.2f}"
        if r.flags:
            summary += f" flags={r.flags}"
        if r.key_concerns:
            summary += f" concerns={r.key_concerns}"
        parts.append(summary)

    return "\n".join(parts)
