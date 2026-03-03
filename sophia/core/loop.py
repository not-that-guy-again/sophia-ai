import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from sophia.config import Settings
from sophia.core.executor import ExecutionResult, Executor
from sophia.core.input_gate import InputGate, Intent
from sophia.core.proposer import Proposal, Proposer
from sophia.hats.registry import HatRegistry
from sophia.hats.schema import HatConfig
from sophia.llm.provider import get_provider
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Full result from one pass through the agent pipeline."""

    intent: Intent
    proposal: Proposal
    execution: ExecutionResult
    response: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": asdict(self.intent),
            "proposal": {
                "candidates": [asdict(c) for c in self.proposal.candidates],
            },
            "execution": {
                "action_taken": asdict(self.execution.action_taken),
                "tool_result": asdict(self.execution.tool_result),
                "risk_tier": self.execution.risk_tier,
            },
            "response": self.response,
            "metadata": self.metadata,
        }


class AgentLoop:
    """Main agent orchestration loop.

    On init, loads the configured hat via HatRegistry. All pipeline components
    receive hat context: tools are scoped, prompts are assembled from core + hat
    fragments, and domain constraints come from the hat.

    Phase 1: Input Gate -> Proposer -> Executor (no consequence tree or evaluation).
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

        # Set up LLM provider
        self.llm = get_provider(self.settings)

        # Set up tool registry and hat registry
        self.tool_registry = ToolRegistry()
        self.hat_registry = HatRegistry(
            hats_dir=Path(self.settings.hats_dir),
            tool_registry=self.tool_registry,
        )

        # Equip the default hat
        self.hat_registry.equip(self.settings.default_hat)
        self._rebuild_pipeline()

    def _rebuild_pipeline(self) -> None:
        """(Re)build pipeline components from the active hat."""
        hat = self.hat_registry.get_active()
        tool_defs = self.tool_registry.get_definitions_text()
        constraints = hat.constraints if hat else {}

        self.input_gate = InputGate(
            llm=self.llm,
            tool_definitions=tool_defs,
            hat_config=hat,
        )
        self.proposer = Proposer(
            llm=self.llm,
            tool_definitions=tool_defs,
            domain_constraints=constraints,
            hat_config=hat,
        )
        self.executor = Executor(registry=self.tool_registry)

    def equip_hat(self, hat_name: str) -> HatConfig:
        """Switch to a different hat and rebuild the pipeline."""
        hat_config = self.hat_registry.equip(hat_name)
        self._rebuild_pipeline()
        return hat_config

    async def process(self, message: str) -> PipelineResult:
        """Run a message through the full pipeline."""
        hat = self.hat_registry.get_active()
        hat_name = hat.name if hat else "none"
        logger.info("Processing message (hat=%s): %s", hat_name, message[:100])

        # Step 1: Parse intent
        intent = await self.input_gate.parse(message)
        logger.info("Intent parsed: action=%s target=%s", intent.action_requested, intent.target)

        # Step 2: Generate proposals
        proposal = await self.proposer.propose(intent)
        logger.info("Proposals generated: %d candidates", len(proposal.candidates))
        for i, c in enumerate(proposal.candidates):
            logger.info("  Candidate %d: %s — %s", i + 1, c.tool_name, c.reasoning[:80])

        # Step 3: Execute top candidate (Phase 1: naive, no evaluation)
        execution = await self.executor.execute(proposal)
        logger.info(
            "Executed: %s (success=%s, tier=%s)",
            execution.action_taken.tool_name,
            execution.tool_result.success,
            execution.risk_tier,
        )

        # Build response message
        response = self._build_response(execution)

        return PipelineResult(
            intent=intent,
            proposal=proposal,
            execution=execution,
            response=response,
            metadata={"hat": hat_name},
        )

    def _build_response(self, execution: ExecutionResult) -> str:
        """Build a user-facing response from the execution result."""
        result = execution.tool_result

        if not result.success:
            return f"I wasn't able to complete that action. {result.message}"

        parts = [result.message]
        if result.data and isinstance(result.data, dict):
            for key, value in result.data.items():
                if key not in ("applied",) and value is not None:
                    parts.append(f"  {key}: {value}")

        return "\n".join(parts)
