import asyncio
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sophia.config import Settings
from sophia.core.consequence import ConsequenceEngine, ConsequenceTree
from sophia.core.evaluators import (
    AuthorityEvaluator,
    DomainEvaluator,
    EvaluationContext,
    EvaluatorResult,
    SelfInterestEvaluator,
    TribalEvaluator,
)
from sophia.core.executor import ExecutionResult, Executor
from sophia.core.input_gate import InputGate, Intent
from sophia.core.proposer import CandidateAction, Proposal, Proposer
from sophia.core.risk_classifier import RiskClassification, classify
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


def _evaluation_to_dict(result: EvaluatorResult) -> dict:
    return asdict(result)


def _classification_to_dict(rc: RiskClassification) -> dict:
    return {
        "tier": rc.tier,
        "weighted_score": rc.weighted_score,
        "individual_scores": rc.individual_scores,
        "flags": rc.flags,
        "override_reason": rc.override_reason,
        "explanation": rc.explanation,
    }


@dataclass
class PipelineResult:
    """Full result from one pass through the agent pipeline."""

    intent: Intent
    proposal: Proposal
    consequence_trees: list[ConsequenceTree]
    evaluation_results: list[EvaluatorResult]
    risk_classification: RiskClassification
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
            "evaluations": [_evaluation_to_dict(e) for e in self.evaluation_results],
            "risk_classification": _classification_to_dict(self.risk_classification),
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

    Pipeline: Input Gate -> Proposer -> Consequence Engine ->
              Evaluation Panel (4 evaluators in parallel) ->
              Risk Classifier -> Tiered Executor.
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

        # Evaluation panel: 4 independent evaluators
        self.evaluators = [
            SelfInterestEvaluator(llm=self.llm, hat_config=hat),
            TribalEvaluator(llm=self.llm, hat_config=hat),
            DomainEvaluator(llm=self.llm, hat_config=hat),
            AuthorityEvaluator(llm=self.llm, hat_config=hat),
        ]

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

        # Step 4: Evaluation panel — run 4 evaluators in parallel on top candidate's tree
        top_tree = consequence_trees[0] if consequence_trees else None
        evaluation_results, risk_classification = await self._run_evaluation_panel(
            top_tree, hat, intent, proposal.candidates
        )
        logger.info("Risk classification: %s (score=%.2f)", risk_classification.tier, risk_classification.weighted_score)

        # Step 5: Tiered execution based on risk classification
        execution = await self._tiered_execute(
            risk_classification, proposal, consequence_trees
        )

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
            evaluation_results=evaluation_results,
            risk_classification=risk_classification,
            execution=execution,
            response=response,
            metadata={"hat": hat_name},
        )

    async def _run_evaluation_panel(
        self,
        tree: ConsequenceTree | None,
        hat: HatConfig | None,
        intent: Intent,
        candidates: list[CandidateAction],
    ) -> tuple[list[EvaluatorResult], RiskClassification]:
        """Run all evaluators in parallel and classify risk."""
        if tree is None:
            # No tree to evaluate — default to GREEN
            empty_classification = RiskClassification(
                tier="GREEN",
                weighted_score=0.0,
                recommended_action=candidates[0] if candidates else None,
                explanation="No consequence tree generated.",
            )
            return [], empty_classification

        context = EvaluationContext(
            consequence_tree=tree,
            hat_config=hat,
            constraints=hat.constraints if hat else {},
            stakeholders=hat.stakeholders.stakeholders if hat else [],
            requestor_context=intent.requestor_context,
        )

        # Run all evaluators in parallel
        results = await asyncio.gather(
            *[evaluator.evaluate(context) for evaluator in self.evaluators]
        )
        evaluation_results = list(results)

        for r in evaluation_results:
            logger.info(
                "  %s: score=%.2f confidence=%.2f flags=%s",
                r.evaluator_name, r.score, r.confidence, r.flags,
            )

        # Deterministic risk classification
        risk_classification = classify(evaluation_results, hat, candidates)
        return evaluation_results, risk_classification

    async def _tiered_execute(
        self,
        risk_classification: RiskClassification,
        proposal: Proposal,
        trees: list[ConsequenceTree],
    ) -> ExecutionResult:
        """Execute based on risk tier."""
        tier = risk_classification.tier

        if tier == "GREEN":
            execution = await self.executor.execute(proposal)
            execution.risk_tier = "GREEN"
            execution.risk_classification = risk_classification
            return execution

        if tier == "YELLOW":
            return self.executor.build_confirmation(proposal, risk_classification, trees)

        if tier == "ORANGE":
            return await self.executor.build_escalation(proposal, risk_classification)

        # RED
        return self.executor.build_refusal(proposal, risk_classification, trees)

    def _build_response(self, execution: ExecutionResult) -> str:
        """Build a user-facing response from the execution result."""
        result = execution.tool_result

        if not result.success:
            return f"I wasn't able to complete that action. {result.message}"

        parts = [result.message]
        if result.data and isinstance(result.data, dict):
            for key, value in result.data.items():
                if key not in ("applied", "requires_confirmation") and value is not None:
                    parts.append(f"  {key}: {value}")

        return "\n".join(parts)
