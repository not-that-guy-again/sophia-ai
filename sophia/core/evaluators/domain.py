"""Domain Evaluator: Does this comply with domain rules and constraints?"""

import json
import logging

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext, EvaluatorResult
from sophia.llm.prompts.core.eval_domain import EVAL_DOMAIN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class DomainEvaluator(BaseEvaluator):

    @property
    def name(self) -> str:
        return "domain"

    @property
    def stage(self) -> str:
        return "eval_domain"

    def _get_custom_flags(self) -> str:
        if self.hat_config and self.hat_config.evaluator_config.custom_flags:
            flags = self.hat_config.evaluator_config.custom_flags.get("domain", [])
            if flags:
                return ", ".join(flags)
        return "No domain-specific flags defined."

    def _get_core_prompt(self, context: EvaluationContext) -> str:
        return EVAL_DOMAIN_SYSTEM_PROMPT.format(
            custom_flags=self._get_custom_flags(),
            tree_summary=self.format_tree_summary(context.consequence_tree),
            stakeholders=self.format_stakeholders(context.stakeholders),
            constraints=json.dumps(context.constraints, indent=2) if context.constraints else "No constraints.",
        )

    def _get_user_message(self, context: EvaluationContext) -> str:
        action = context.consequence_tree.candidate_action
        base = (
            f"Evaluate domain rule compliance for calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
        if context.evaluation_mode == "situation" and context.original_request:
            return (
                f"Evaluate the domain rule compliance of the following customer request: "
                f'"{context.original_request}"\n\n'
                f"The requested action would be: {action.tool_name} "
                f"with parameters {json.dumps(action.parameters)}."
            )
        return base

    async def evaluate(self, context: EvaluationContext) -> EvaluatorResult:
        """Run domain evaluation with flag/score consistency enforcement."""
        result = await super().evaluate(context)

        if "social_engineering" in result.flags and result.score > -0.50:
            logger.warning(
                "Domain: social_engineering flag requires score ≤ -0.50, got %.2f — clamping",
                result.score,
            )
            result.score = -0.50

        if "free_item_attempt" in result.flags and result.score > -0.70:
            logger.warning(
                "Domain: free_item_attempt flag requires score ≤ -0.70, got %.2f — clamping",
                result.score,
            )
            result.score = -0.70

        return result
