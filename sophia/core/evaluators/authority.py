"""Authority Evaluator: Does the requestor have standing?"""

import json
import logging

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext, EvaluatorResult
from sophia.llm.prompts.core.eval_authority import EVAL_AUTHORITY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AuthorityEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "authority"

    @property
    def stage(self) -> str:
        return "eval_authority"

    def _get_custom_flags(self) -> str:
        if self.hat_config and self.hat_config.evaluator_config.custom_flags:
            flags = self.hat_config.evaluator_config.custom_flags.get("authority", [])
            if flags:
                return ", ".join(flags)
        return "No domain-specific flags defined."

    def _get_core_prompt(self, context: EvaluationContext) -> str:
        return EVAL_AUTHORITY_SYSTEM_PROMPT.format(
            custom_flags=self._get_custom_flags(),
            requestor_context=json.dumps(context.requestor_context, indent=2),
            tree_summary=self.format_tree_summary(context.consequence_tree),
            stakeholders=self.format_stakeholders(context.stakeholders),
            constraints=json.dumps(context.constraints, indent=2)
            if context.constraints
            else "No constraints.",
        )

    def _get_user_message(self, context: EvaluationContext) -> str:
        action = context.consequence_tree.candidate_action
        base = (
            f"Evaluate requestor authority for calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
        if context.evaluation_mode == "situation" and context.original_request:
            return (
                f"Evaluate the requestor authority of the following customer request: "
                f'"{context.original_request}"\n\n'
                f"The requested action would be: {action.tool_name} "
                f"with parameters {json.dumps(action.parameters)}."
            )
        return base

    async def evaluate(self, context: EvaluationContext) -> EvaluatorResult:
        """Run authority evaluation with flag/score consistency enforcement."""
        result = await super().evaluate(context)

        # Enforce flag/score consistency: flags must correspond to negative scores
        if result.flags and result.score >= 0.0:
            logger.warning(
                "Authority evaluator: flags %s raised but score=%.2f — clamping to -0.30",
                result.flags,
                result.score,
            )
            result.score = -0.30

        # Enforce cross_customer_access severity floor
        if "cross_customer_access" in result.flags and result.score > -0.70:
            logger.warning(
                "Authority evaluator: cross_customer_access flag requires score ≤ -0.70, got %.2f",
                result.score,
            )
            result.score = -0.70

        if "social_engineering" in result.flags and result.score > -0.70:
            logger.warning(
                "Authority: social_engineering flag requires score ≤ -0.70, got %.2f — clamping",
                result.score,
            )
            result.score = -0.70

        if "fabricated_claim" in result.flags and result.score > -0.55:
            logger.warning(
                "Authority: fabricated_claim flag requires score ≤ -0.55, got %.2f — clamping",
                result.score,
            )
            result.score = -0.55

        return result
