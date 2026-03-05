"""Self-Interest Evaluator: Does this keep the system operational and trusted?"""

import json

from sophia.core.evaluators.base import BaseEvaluator, EvaluationContext
from sophia.llm.prompts.core.eval_self import EVAL_SELF_SYSTEM_PROMPT


class SelfInterestEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "self_interest"

    @property
    def stage(self) -> str:
        return "eval_self"

    def _get_core_prompt(self, context: EvaluationContext) -> str:
        return EVAL_SELF_SYSTEM_PROMPT.format(
            tree_summary=self.format_tree_summary(context.consequence_tree),
            stakeholders=self.format_stakeholders(context.stakeholders),
            constraints=json.dumps(context.constraints, indent=2)
            if context.constraints
            else "No constraints.",
        )

    def _get_user_message(self, context: EvaluationContext) -> str:
        action = context.consequence_tree.candidate_action
        return (
            f"Evaluate the self-interest implications of calling "
            f"{action.tool_name} with parameters {json.dumps(action.parameters)}."
        )
