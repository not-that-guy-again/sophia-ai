import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sophia.core.proposer import CandidateAction, Proposal
from sophia.tools.base import ToolResult
from sophia.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from sophia.core.consequence import ConsequenceTree
    from sophia.core.risk_classifier import RiskClassification

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    action_taken: CandidateAction
    tool_result: ToolResult
    risk_tier: str  # GREEN, YELLOW, ORANGE, RED
    risk_classification: "RiskClassification | None" = field(default=None, repr=False)


class Executor:
    """Executes proposed actions via the tool registry with tiered behavior.

    - GREEN: execute the action
    - YELLOW: present action + top consequences for user confirmation
    - ORANGE: auto-escalate (call escalate_to_human if available)
    - RED: refuse with specific harmful branch citations
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, proposal: Proposal) -> ExecutionResult:
        """Execute the top candidate action (GREEN tier)."""
        if not proposal.candidates:
            return ExecutionResult(
                action_taken=CandidateAction(tool_name="none", reasoning="No candidates proposed"),
                tool_result=ToolResult(
                    success=False, data=None, message="No action candidates were proposed"
                ),
                risk_tier="GREEN",
            )

        candidate = proposal.candidates[0]

        # Conversational bypass — never call the tool registry for "converse"
        if candidate.tool_name == "converse":
            logger.info("Executor: converse candidate, skipping tool registry")
            return ExecutionResult(
                action_taken=candidate,
                tool_result=ToolResult(
                    success=True, data=None, message="Conversational response"
                ),
                risk_tier="GREEN",
            )

        logger.info(
            "Executing top candidate: %s (reasoning: %s)",
            candidate.tool_name,
            candidate.reasoning,
        )

        tool_result = await self.registry.execute(candidate.tool_name, candidate.parameters)

        return ExecutionResult(
            action_taken=candidate,
            tool_result=tool_result,
            risk_tier="GREEN",
        )

    def build_confirmation(
        self,
        proposal: Proposal,
        risk_classification: "RiskClassification",
        trees: "list[ConsequenceTree]",
    ) -> ExecutionResult:
        """Build a YELLOW tier response: present action for user confirmation."""
        candidate = proposal.candidates[0] if proposal.candidates else CandidateAction(
            tool_name="none", reasoning="No candidates"
        )

        concern_lines = []
        if risk_classification.explanation:
            concern_lines.append(risk_classification.explanation)
        if trees:
            tree = trees[0]
            if tree.worst_terminal:
                concern_lines.append(
                    f"Top concern: {tree.worst_terminal.description} "
                    f"(probability: {tree.worst_terminal.probability:.0%})"
                )

        message = (
            f"I'd like to proceed with {candidate.tool_name}, "
            f"but this requires your confirmation.\n\n"
            + "\n".join(concern_lines)
        )

        return ExecutionResult(
            action_taken=candidate,
            tool_result=ToolResult(success=True, data={"requires_confirmation": True}, message=message),
            risk_tier="YELLOW",
            risk_classification=risk_classification,
        )

    async def build_escalation(
        self,
        proposal: Proposal,
        risk_classification: "RiskClassification",
    ) -> ExecutionResult:
        """Build an ORANGE tier response: auto-escalate to human."""
        candidate = proposal.candidates[0] if proposal.candidates else CandidateAction(
            tool_name="none", reasoning="No candidates"
        )

        # Try to call escalate_to_human if the tool is registered
        escalation_result = None
        if self.registry.has_tool("escalate_to_human"):
            escalation_result = await self.registry.execute(
                "escalate_to_human",
                {
                    "reason": f"Risk assessment: {risk_classification.tier}",
                    "priority": "high",
                    "context_summary": risk_classification.explanation,
                },
            )

        if escalation_result and escalation_result.success:
            message = (
                f"This request has been escalated for human review. "
                f"Reason: {risk_classification.explanation}"
            )
            return ExecutionResult(
                action_taken=CandidateAction(
                    tool_name="escalate_to_human",
                    reasoning="Auto-escalated due to ORANGE risk tier",
                ),
                tool_result=escalation_result,
                risk_tier="ORANGE",
                risk_classification=risk_classification,
            )

        message = (
            f"This request requires human review and cannot be processed automatically.\n\n"
            f"{risk_classification.explanation}"
        )
        return ExecutionResult(
            action_taken=candidate,
            tool_result=ToolResult(success=False, data=None, message=message),
            risk_tier="ORANGE",
            risk_classification=risk_classification,
        )

    def build_refusal(
        self,
        proposal: Proposal,
        risk_classification: "RiskClassification",
        trees: "list[ConsequenceTree]",
    ) -> ExecutionResult:
        """Build a RED tier response: refuse with harmful branch citations."""
        candidate = proposal.candidates[0] if proposal.candidates else CandidateAction(
            tool_name="none", reasoning="No candidates"
        )

        harm_citations = []
        if trees:
            tree = trees[0]
            if tree.worst_terminal:
                harm_citations.append(
                    f"- {tree.worst_terminal.description} "
                    f"(harm_benefit={tree.worst_terminal.harm_benefit:.2f}, "
                    f"probability={tree.worst_terminal.probability:.0%})"
                )

        citation_text = "\n".join(harm_citations) if harm_citations else "Multiple risk factors identified."

        override = ""
        if risk_classification.override_reason:
            override = f" Override: {risk_classification.override_reason}."

        message = (
            f"Action refused: consequence analysis identified unacceptable risk.{override}\n\n"
            f"Harmful consequences identified:\n{citation_text}"
        )

        return ExecutionResult(
            action_taken=candidate,
            tool_result=ToolResult(success=False, data=None, message=message),
            risk_tier="RED",
            risk_classification=risk_classification,
        )
