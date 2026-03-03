"""Domain Evaluator: Does this comply with domain rules and constraints?"""

import json

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext
from sophia.llm.prompts.core.eval_domain import EVAL_DOMAIN_SYSTEM_PROMPT


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
        return (
            f"Evaluate domain rule compliance for calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
