"""Base evaluator interface and shared data models for the evaluation panel."""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sophia.core.consequence import ConsequenceNode, ConsequenceTree
from sophia.core.input_gate import _extract_json
from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig, Stakeholder
from sophia.llm.provider import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class EvaluatorResult:
    evaluator_name: str
    score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    flags: list[str] = field(default_factory=list)
    reasoning: str = ""
    key_concerns: list[str] = field(default_factory=list)


@dataclass
class EvaluationContext:
    consequence_tree: ConsequenceTree
    hat_config: HatConfig | None
    constraints: dict = field(default_factory=dict)
    stakeholders: list[Stakeholder] = field(default_factory=list)
    requestor_context: dict = field(default_factory=dict)
    conversation_history: list[Any] = field(default_factory=list)
    evaluation_mode: str = "response"  # "response" | "situation"
    original_request: str | None = None  # the user's raw message


class BaseEvaluator(ABC):
    """Abstract base for all evaluators in the evaluation panel.

    Each evaluator receives a consequence tree and hat context, calls the LLM
    with an assembled prompt (core + hat fragment), and returns an EvaluatorResult.
    """

    def __init__(self, llm: LLMProvider, hat_config: HatConfig | None = None):
        self.llm = llm
        self.hat_config = hat_config

    @property
    @abstractmethod
    def name(self) -> str:
        """Evaluator name (e.g., 'tribal', 'domain')."""

    @property
    @abstractmethod
    def stage(self) -> str:
        """Prompt assembler stage key (e.g., 'eval_tribal')."""

    @abstractmethod
    def _get_core_prompt(self, context: EvaluationContext) -> str:
        """Return the formatted core prompt for this evaluator."""

    @abstractmethod
    def _get_user_message(self, context: EvaluationContext) -> str:
        """Return the user message for the LLM call."""

    async def evaluate(self, context: EvaluationContext) -> EvaluatorResult:
        """Run this evaluator against the consequence tree."""
        core_prompt = self._get_core_prompt(context)
        system_prompt = assemble_prompt(self.stage, core_prompt, self.hat_config)

        # ADR-030: when evaluating a situation, amend the system prompt
        if context.evaluation_mode == "situation":
            situation_note = (
                "\n\nNOTE: You are evaluating a SITUATION, not an action the agent "
                "is taking. The agent has declined or escalated this request. Your "
                "job is to assess how dangerous the customer's request was, not "
                "whether the agent's response is appropriate."
            )
            system_prompt = system_prompt + situation_note

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=self._get_user_message(context),
            response_format={"type": "json"},
        )

        logger.debug("%s evaluator raw response: %s", self.name, response.content)
        return self._parse_result(response.content)

    def _parse_result(self, raw: str) -> EvaluatorResult:
        """Parse LLM JSON response into an EvaluatorResult with clamped scores."""
        parsed = json.loads(_extract_json(raw))

        return EvaluatorResult(
            evaluator_name=self.name,
            score=_clamp(parsed.get("score", 0.0), -1.0, 1.0),
            confidence=_clamp(parsed.get("confidence", 0.5), 0.0, 1.0),
            flags=parsed.get("flags", []),
            reasoning=parsed.get("reasoning", ""),
            key_concerns=parsed.get("key_concerns", []),
        )

    @staticmethod
    def format_tree_summary(tree: ConsequenceTree) -> str:
        """Format a consequence tree into a text summary for evaluator prompts."""
        lines = [
            f"Action: {tree.candidate_action.tool_name}",
            f"Parameters: {json.dumps(tree.candidate_action.parameters)}",
            f"Reasoning: {tree.candidate_action.reasoning}",
            f"Total consequence nodes: {tree.total_nodes}",
        ]
        if tree.worst_terminal:
            lines.append(
                f"Worst terminal: {tree.worst_terminal.description} "
                f"(harm_benefit={tree.worst_terminal.harm_benefit:.2f}, "
                f"prob={tree.worst_terminal.probability:.2f})"
            )
        if tree.best_terminal:
            lines.append(
                f"Best terminal: {tree.best_terminal.description} "
                f"(harm_benefit={tree.best_terminal.harm_benefit:.2f}, "
                f"prob={tree.best_terminal.probability:.2f})"
            )

        lines.append("\nConsequence branches:")
        for root in tree.root_nodes:
            _format_node(root, lines, indent=1)

        return "\n".join(lines)

    @staticmethod
    def format_stakeholders(stakeholders: list[Stakeholder]) -> str:
        """Format stakeholders list for prompt injection."""
        if not stakeholders:
            return "No stakeholders defined."
        lines = []
        for s in stakeholders:
            lines.append(
                f"- {s.id} ({s.name}): interests={s.interests}, "
                f"harm_sensitivity={s.harm_sensitivity}, weight={s.weight}"
            )
        return "\n".join(lines)


def _format_node(node: ConsequenceNode, lines: list[str], indent: int) -> None:
    """Recursively format a consequence node for prompt text."""
    prefix = "  " * indent
    lines.append(
        f"{prefix}- {node.description} "
        f"[harm_benefit={node.harm_benefit:.2f}, prob={node.probability:.2f}, "
        f"stakeholders={node.stakeholders_affected}]"
    )
    for child in node.children:
        _format_node(child, lines, indent + 1)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
