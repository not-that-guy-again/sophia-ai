import logging
from dataclasses import dataclass

from sophia.core.proposer import CandidateAction, Proposal
from sophia.tools.base import ToolResult
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    action_taken: CandidateAction
    tool_result: ToolResult
    risk_tier: str  # Set by consequence analysis in the pipeline loop


class Executor:
    """Executes proposed actions via the tool registry.

    Takes the first candidate and runs it via the tool registry. Risk
    classification is handled upstream by the consequence engine; the
    loop overrides risk_tier on the result after execution.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, proposal: Proposal) -> ExecutionResult:
        if not proposal.candidates:
            return ExecutionResult(
                action_taken=CandidateAction(tool_name="none", reasoning="No candidates proposed"),
                tool_result=ToolResult(
                    success=False, data=None, message="No action candidates were proposed"
                ),
                risk_tier="GREEN",
            )

        # Phase 1: just take the top candidate
        candidate = proposal.candidates[0]
        logger.info(
            "Executing top candidate: %s (reasoning: %s)",
            candidate.tool_name,
            candidate.reasoning,
        )

        tool_result = await self.registry.execute(candidate.tool_name, candidate.parameters)

        return ExecutionResult(
            action_taken=candidate,
            tool_result=tool_result,
            risk_tier="GREEN",  # Default; overridden by consequence analysis in the loop
        )
