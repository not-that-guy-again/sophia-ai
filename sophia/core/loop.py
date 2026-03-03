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
from sophia.core.response_generator import ResponseGenerator
from sophia.core.risk_classifier import RiskClassification, classify
from sophia.hats.registry import HatRegistry
from sophia.hats.schema import HatConfig
from sophia.llm.provider import get_provider
from sophia.memory.extractor import MemoryExtractor
from sophia.memory.provider import MemoryProvider, get_memory_provider
from sophia.tools.base import ToolResult
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CONVERSE_TOOL_NAME = "converse"


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
    bypassed: bool = False
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
            "bypassed": self.bypassed,
            "metadata": self.metadata,
        }


class AgentLoop:
    """Main agent orchestration loop.

    Pipeline: Memory Recall -> Input Gate -> Proposer ->
              [Consequence Engine -> Evaluation Panel ->
              Risk Classifier -> Tiered Executor] ->
              Response Generator -> Memory Persist.

    When the proposer selects "converse", the bracketed stages are skipped.
    Memory recall happens before the pipeline; memory persist happens after.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        memory_provider: MemoryProvider | None = None,
    ):
        self.settings = settings or Settings()

        # Set up LLM provider
        self.llm = get_provider(self.settings)

        # Set up memory provider (injected or from config)
        self.memory = memory_provider or get_memory_provider(self.settings)

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
        self.response_generator = ResponseGenerator(llm=self.llm, hat_config=hat)
        self.memory_extractor = MemoryExtractor(
            llm=self.llm, memory=self.memory, hat_config=hat
        )

    def equip_hat(self, hat_name: str) -> HatConfig:
        """Switch to a different hat and rebuild the pipeline."""
        hat_config = self.hat_registry.equip(hat_name)
        self._rebuild_pipeline()
        return hat_config

    async def _recall_memory(self, message: str) -> dict:
        """Step 0: Query memory for relevant context before pipeline runs."""
        context: dict = {"entities": [], "episodes": []}
        try:
            # Search for entities mentioned in the message
            entities = await self.memory.search_entities(message, limit=5)
            context["entities"] = entities

            # For each found entity, get recent episodes and relationships
            for entity in entities[:3]:  # Limit to top 3 to control latency
                episodes = await self.memory.recall_by_entity(
                    entity.entity_type, entity.name, limit=3
                )
                context["episodes"].extend(episodes)
                relationships = await self.memory.get_relationships(entity.id)
                context.setdefault("relationships", []).extend(relationships)

            if entities:
                logger.info(
                    "Memory recall: %d entities, %d episodes",
                    len(context["entities"]),
                    len(context["episodes"]),
                )
        except Exception:
            logger.exception("Memory recall failed (non-fatal, continuing without memory)")

        return context

    async def _persist_memory(self, message: str, result: PipelineResult) -> None:
        """Step 8: Extract and store memory after pipeline completes."""
        try:
            await self.memory_extractor.extract_and_store(
                user_message=message,
                action_taken=result.execution.action_taken.tool_name,
                action_parameters=result.execution.action_taken.parameters,
                outcome=result.execution.tool_result.message,
            )
        except Exception:
            logger.exception("Memory persist failed (non-fatal)")

    async def process(self, message: str) -> PipelineResult:
        """Run a message through the full pipeline."""
        hat = self.hat_registry.get_active()
        hat_name = hat.name if hat else "none"
        logger.info("Processing message (hat=%s): %s", hat_name, message[:100])

        # Step 0: Memory recall — query for relevant context
        memory_context = await self._recall_memory(message)

        # Step 1: Parse intent
        intent = await self.input_gate.parse(message)
        logger.info("Intent parsed: action=%s target=%s", intent.action_requested, intent.target)

        # Step 2: Generate proposals
        proposal = await self.proposer.propose(intent)
        logger.info("Proposals generated: %d candidates", len(proposal.candidates))
        for i, c in enumerate(proposal.candidates):
            logger.info("  Candidate %d: %s — %s", i + 1, c.tool_name, c.reasoning[:80])

        # Check for conversational bypass (ADR-017)
        top_candidate = proposal.candidates[0] if proposal.candidates else None
        if top_candidate and top_candidate.tool_name == CONVERSE_TOOL_NAME:
            return await self._handle_converse(message, intent, proposal, hat_name)

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

        # Step 6: Generate natural language response (ADR-018)
        response = await self.response_generator.generate(
            user_message=message,
            risk_tier=execution.risk_tier,
            action_taken=execution.action_taken.tool_name,
            action_reasoning=execution.action_taken.reasoning,
            tool_result_message=execution.tool_result.message,
            tool_result_data=execution.tool_result.data if isinstance(execution.tool_result.data, dict) else None,
        )

        pipeline_result = PipelineResult(
            intent=intent,
            proposal=proposal,
            consequence_trees=consequence_trees,
            evaluation_results=evaluation_results,
            risk_classification=risk_classification,
            execution=execution,
            response=response,
            metadata={"hat": hat_name, "memory_context": {
                "entities_recalled": len(memory_context.get("entities", [])),
                "episodes_recalled": len(memory_context.get("episodes", [])),
            }},
        )

        # Step 8: Memory persist — extract and store
        await self._persist_memory(message, pipeline_result)

        return pipeline_result

    async def _handle_converse(
        self,
        message: str,
        intent: Intent,
        proposal: Proposal,
        hat_name: str,
    ) -> PipelineResult:
        """Handle conversational bypass — skip consequence/evaluation/execution."""
        logger.info("Conversational bypass: skipping consequence engine and evaluation panel")

        response = await self.response_generator.converse(message)

        # Build minimal pipeline result with empty consequence/evaluation/execution
        converse_candidate = proposal.candidates[0]
        empty_classification = RiskClassification(
            tier="GREEN",
            weighted_score=0.0,
            explanation="Conversational bypass — no tool execution needed.",
        )
        converse_execution = ExecutionResult(
            action_taken=converse_candidate,
            tool_result=ToolResult(success=True, data=None, message=response),
            risk_tier="GREEN",
            risk_classification=empty_classification,
        )

        pipeline_result = PipelineResult(
            intent=intent,
            proposal=proposal,
            consequence_trees=[],
            evaluation_results=[],
            risk_classification=empty_classification,
            execution=converse_execution,
            response=response,
            bypassed=True,
            metadata={"hat": hat_name},
        )

        # Memory persist for conversational messages too
        await self._persist_memory(message, pipeline_result)

        return pipeline_result

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
