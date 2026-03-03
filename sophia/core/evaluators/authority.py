"""Authority Evaluator: Does the requestor have standing?"""

import json

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext
from sophia.llm.prompts.core.eval_authority import EVAL_AUTHORITY_SYSTEM_PROMPT


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
            constraints=json.dumps(context.constraints, indent=2) if context.constraints else "No constraints.",
        )

    def _get_user_message(self, context: EvaluationContext) -> str:
        action = context.consequence_tree.candidate_action
        return (
            f"Evaluate requestor authority for calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
