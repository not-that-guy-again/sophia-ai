import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from sophia.config import Settings
from sophia.core.consequence import ConsequenceEngine, ConsequenceTree
from sophia.core.executor import ExecutionResult, Executor
from sophia.core.input_gate import InputGate, Intent
from sophia.core.proposer import CandidateAction, Proposal, Proposer
from sophia.core.tree_analysis import classify_risk
from sophia.hats.registry import HatRegistry
from sophia.hats.schema import HatConfig
from sophia.llm.provider import get_provider
from sophia.tools.base import ToolResult
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _node_to_dict(node) -> dict:
    """Convert a ConsequenceNode to a serializable dict."""
    return {
        "id": node.id,
        "description": node.description,
        "stakeholders_affected": node.stakeholders_affected,
        "probability": node.probability,
        "tangibility": node.tangibility,
        "harm_benefit": node.harm_benefit,
        "affected_party": node.affected_party,
        "children": [_node_to_dict(c) for c in node.children],
        "is_terminal": node.is_terminal,
    }


def _tree_to_dict(tree: ConsequenceTree) -> dict:
    """Convert a ConsequenceTree to a serializable dict."""
    return {
        "candidate_tool_name": tree.candidate_action.tool_name,
        "root_nodes": [_node_to_dict(n) for n in tree.root_nodes],
        "max_depth": tree.max_depth,
        "total_nodes": tree.total_nodes,
        "worst_harm": tree.worst_terminal.harm_benefit if tree.worst_terminal else None,
        "best_benefit": tree.best_terminal.harm_benefit if tree.best_terminal else None,
    }


@dataclass
class PipelineResult:
    """Full result from one pass through the agent pipeline."""

    intent: Intent
    proposal: Proposal
    consequence_trees: list[ConsequenceTree]
    execution: ExecutionResult
    response: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": asdict(self.intent),
            "proposal": {
                "candidates": [asdict(c) for c in self.proposal.candidates],
            },
            "consequence_trees": [_tree_to_dict(t) for t in self.consequence_trees],
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

    Pipeline: Input Gate -> Proposer -> Consequence Engine -> Executor.
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
        self.consequence_engine = ConsequenceEngine(
            llm=self.llm,
            hat_config=hat,
            max_depth=self.settings.tree_max_depth,
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

        # Step 3: Generate consequence trees for each candidate
        consequence_trees: list[ConsequenceTree] = []
        for candidate in proposal.candidates:
            tree = await self.consequence_engine.analyze(candidate)
            consequence_trees.append(tree)
            logger.info(
                "Consequence tree for '%s': %d nodes, worst=%.2f, best=%.2f",
                candidate.tool_name,
                tree.total_nodes,
                tree.worst_terminal.harm_benefit if tree.worst_terminal else 0.0,
                tree.best_terminal.harm_benefit if tree.best_terminal else 0.0,
            )

        # Step 4: Classify risk on top candidate's tree
        top_tree = consequence_trees[0] if consequence_trees else None
        risk_tier = (
            classify_risk(top_tree, catastrophic_threshold=self.settings.catastrophic_threshold)
            if top_tree
            else "GREEN"
        )
        logger.info("Risk classification: %s", risk_tier)

        # Step 5: Execute based on risk tier
        if risk_tier == "RED":
            # REFUSE — do not execute the action
            execution = ExecutionResult(
                action_taken=proposal.candidates[0],
                tool_result=ToolResult(
                    success=False,
                    data=None,
                    message="Action refused: consequence analysis identified catastrophic risk.",
                ),
                risk_tier="RED",
            )
        else:
            execution = await self.executor.execute(proposal)
            execution.risk_tier = risk_tier

        logger.info(
            "Result: %s (success=%s, tier=%s)",
            execution.action_taken.tool_name,
            execution.tool_result.success,
            execution.risk_tier,
        )

        # Build response message
        response = self._build_response(execution)

        return PipelineResult(
            intent=intent,
            proposal=proposal,
            consequence_trees=consequence_trees,
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
