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
    risk_tier: str  # Phase 1: always "GREEN"


class Executor:
    """Executes proposed actions via the tool registry.

    Phase 1: Naive execution — takes the first candidate and runs it directly.
    No consequence evaluation or risk classification.
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
            risk_tier="GREEN",  # Phase 1: no evaluation, everything is green
        )
