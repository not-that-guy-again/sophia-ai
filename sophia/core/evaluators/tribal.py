"""Tribal Evaluator: Does this cause tangible, felt harm to real people?

Has veto power — catastrophic harm flag triggers automatic RED.
"""

import json
import logging

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext, EvaluatorResult
from sophia.llm.prompts.core.eval_tribal import EVAL_TRIBAL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Score at or below this threshold auto-adds catastrophic_harm flag
CATASTROPHIC_SCORE_THRESHOLD = -0.8


class TribalEvaluator(BaseEvaluator):

    @property
    def name(self) -> str:
        return "tribal"

    @property
    def stage(self) -> str:
        return "eval_tribal"

    def _get_custom_flags(self) -> str:
        if self.hat_config and self.hat_config.evaluator_config.custom_flags:
            flags = self.hat_config.evaluator_config.custom_flags.get("tribal", [])
            if flags:
                return ", ".join(flags)
        return "No domain-specific flags defined."

    def _get_core_prompt(self, context: EvaluationContext) -> str:
        return EVAL_TRIBAL_SYSTEM_PROMPT.format(
            custom_flags=self._get_custom_flags(),
            tree_summary=self.format_tree_summary(context.consequence_tree),
            stakeholders=self.format_stakeholders(context.stakeholders),
            constraints=json.dumps(context.constraints, indent=2) if context.constraints else "No constraints.",
        )

    def _get_user_message(self, context: EvaluationContext) -> str:
        action = context.consequence_tree.candidate_action
        base = (
            f"Evaluate the tribal harm implications of calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
        if context.evaluation_mode == "situation" and context.original_request:
            return (
                f"Evaluate the tribal harm of the following customer request: "
                f'"{context.original_request}"\n\n'
                f"The requested action would be: {action.tool_name} "
                f"with parameters {json.dumps(action.parameters)}."
            )
        return base

    async def evaluate(self, context: EvaluationContext) -> EvaluatorResult:
        """Run tribal evaluation with automatic catastrophic_harm flag enforcement."""
        result = await super().evaluate(context)

        # Enforce catastrophic_harm flag if score is at or below threshold
        if result.score <= CATASTROPHIC_SCORE_THRESHOLD and "catastrophic_harm" not in result.flags:
            logger.warning(
                "Tribal score %.2f <= %.2f, auto-adding catastrophic_harm flag",
                result.score,
                CATASTROPHIC_SCORE_THRESHOLD,
            )
            result.flags.append("catastrophic_harm")

        if "social_engineering" in result.flags and result.score > -0.50:
            logger.warning(
                "Tribal: social_engineering flag requires score ≤ -0.50, got %.2f — clamping",
                result.score,
            )
            result.score = -0.50

        if "fabricated_claim" in result.flags and result.score > -0.50:
            logger.warning(
                "Tribal: fabricated_claim flag requires score ≤ -0.50, got %.2f — clamping",
                result.score,
            )
            result.score = -0.50

        return result
