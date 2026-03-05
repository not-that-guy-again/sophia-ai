import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sophia.config import Settings
from sophia.core.consequence import ConsequenceEngine, ConsequenceTree, SituationCandidate
from sophia.core.constitution import load_constitution
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
from sophia.core.parameter_gate import ParameterGate
from sophia.core.preflight_ack import maybe_generate_ack
from sophia.core.proposer import CandidateAction, Proposal, Proposer
from sophia.core.response_generator import ResponseGenerator
from sophia.core.escalation_gate import check_escalation_triggers
from sophia.core.risk_classifier import RiskClassification, classify
from sophia.core.risk_floor import TIER_ORDER as _FLOOR_TIER_ORDER, get_proposal_floor
from sophia.hats.registry import HatRegistry
from sophia.hats.schema import HatConfig
from sophia.llm.provider import get_provider
from sophia.memory.extractor import MemoryExtractor
from sophia.memory.provider import MemoryProvider, get_memory_provider
from sophia.tools.base import ToolResult
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CONVERSE_TOOL_NAME = "converse"
DEFENSIVE_TOOL_NAMES = {CONVERSE_TOOL_NAME, "escalate_to_human"}

# Intents that are genuinely non-actionable and should not trigger situation evaluation.
# cross_customer_access is intentionally NOT in this set — it is action-bearing.
_SITUATION_EVAL_EXEMPT_INTENTS = frozenset({"general_inquiry"})


def _is_defensive_proposal(candidate) -> bool:
    """Return True if the candidate is a defensive (non-action) proposal."""
    return candidate.tool_name in DEFENSIVE_TOOL_NAMES


def _find_floor_trigger(
    candidates: list[CandidateAction],
    tool_registry: ToolRegistry,
    floor: str,
) -> str | None:
    """Return the name of the first tool declaring the given risk_floor."""
    for candidate in candidates:
        tool = tool_registry.get(candidate.tool_name)
        if tool and getattr(tool, "risk_floor", None) == floor:
            return candidate.tool_name
    return None


def _max_tier(a: str | None, b: str | None) -> str | None:
    """Return the higher of two tier values, or the non-None one."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _FLOOR_TIER_ORDER[a] >= _FLOOR_TIER_ORDER[b] else b


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
    preflight_ack: str | None = None
    preflight_ack_at: float | None = None
    metadata: dict = field(default_factory=dict)
    escalation_trigger_matched: str | None = None
    risk_floor_short_circuit: bool = False
    risk_floor_trigger_tool: str | None = None
    risk_floor_trigger_value: str | None = None
    situation_tree: ConsequenceTree | None = None
    situation_evaluation_results: list = field(default_factory=list)
    situation_risk_classification: RiskClassification | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
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
            "preflight_ack": self.preflight_ack,
            "preflight_ack_at": self.preflight_ack_at,
            "escalation_trigger_matched": self.escalation_trigger_matched,
            "risk_floor_short_circuit": self.risk_floor_short_circuit,
            "risk_floor_trigger_tool": self.risk_floor_trigger_tool,
            "risk_floor_trigger_value": self.risk_floor_trigger_value,
            "metadata": self.metadata,
        }
        if self.situation_tree is not None:
            result["situation_tree"] = _tree_to_dict(self.situation_tree)
        if self.situation_evaluation_results:
            result["situation_evaluations"] = [
                _evaluation_to_dict(e) for e in self.situation_evaluation_results
            ]
        if self.situation_risk_classification is not None:
            result["situation_risk_classification"] = _classification_to_dict(
                self.situation_risk_classification
            )
        return result


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

        # Load the Sophia Constitution once at startup
        self.constitution = load_constitution()

        # Set up memory provider (injected or from config)
        self.memory = memory_provider or get_memory_provider(self.settings)

        # Set up tool registry and hat registry
        self.tool_registry = ToolRegistry()
        self.hat_registry = HatRegistry(
            hats_dir=Path(self.settings.hats_dir),
            tool_registry=self.tool_registry,
        )

        # Set refs on hat_registry so webhooks can access memory and pipeline
        self.hat_registry.memory = self.memory
        self.hat_registry.agent_loop = self

        # Hat equipping is deferred to first process() or explicit equip_hat()
        # because service initialization is async
        self._hat_equipped = False

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

        extra_placeholders = set(hat.manifest.placeholder_patterns) if hat else set()
        self.parameter_gate = ParameterGate(
            tool_registry=self.tool_registry,
            extra_placeholders=extra_placeholders,
        )

        self.executor = Executor(registry=self.tool_registry)
        self.response_generator = ResponseGenerator(
            llm=self.llm,
            hat_config=hat,
            constitution=getattr(self, "constitution", ""),
        )
        self.memory_extractor = MemoryExtractor(llm=self.llm, memory=self.memory, hat_config=hat)

    async def _ensure_hat_equipped(self) -> None:
        """Equip the default hat if not already done (deferred from __init__)."""
        if not self._hat_equipped:
            await self.hat_registry.equip(self.settings.default_hat)
            self._rebuild_pipeline()
            self._hat_equipped = True

    async def equip_hat(self, hat_name: str) -> HatConfig:
        """Switch to a different hat and rebuild the pipeline."""
        hat_config = await self.hat_registry.equip(hat_name)
        self._rebuild_pipeline()
        self._hat_equipped = True
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

    async def process(
        self,
        message: str,
        on_preflight_ack: Callable[[str], Awaitable[None]] | None = None,
        source: str = "user",
        metadata: dict | None = None,
        conversation_history: list[dict] | None = None,
    ) -> PipelineResult:
        """Run a message through the full pipeline."""
        await self._ensure_hat_equipped()
        hat = self.hat_registry.get_active()
        hat_name = hat.name if hat else "none"
        logger.info("Processing message (hat=%s, source=%s): %s", hat_name, source, message[:100])

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

        # Step 2.5: Parameter gate (ADR-019)
        gate_result = self.parameter_gate.validate(proposal)
        gate_metadata = {
            "parameter_gate": [
                {
                    "tool_name": v.candidate.tool_name,
                    "passed": v.passed,
                    "failures": v.failures,
                }
                for v in gate_result.validations
            ]
        }
        if gate_result.promoted_converse or len(gate_result.surviving_candidates) < len(
            gate_result.original_candidates
        ):
            proposal = Proposal(intent=proposal.intent, candidates=gate_result.surviving_candidates)
            logger.info(
                "Parameter gate filtered %d candidates",
                len(gate_result.original_candidates) - len(gate_result.surviving_candidates),
            )

        # Step 2.55: Escalation trigger gate — deterministic, no LLM
        escalation_result = check_escalation_triggers(
            message,
            hat.constraints or {},
            conversation_history=conversation_history,
        )
        if escalation_result.triggered:
            logger.info(
                "Escalation trigger: %r → minimum tier ORANGE",
                escalation_result.matched_trigger,
            )
        escalation_min_tier = escalation_result.min_tier if escalation_result.triggered else None

        # Step 2.6: Pre-flight acknowledgment (ADR-021)
        # Skip for webhook-sourced messages
        preflight_ack: str | None = None
        preflight_ack_at: float | None = None
        if source != "webhook":
            preflight_ack = maybe_generate_ack(
                intent=intent,
                candidates=proposal.candidates,
                tool_registry=self.tool_registry,
                hat_config=hat,
            )
            if preflight_ack:
                preflight_ack_at = time.time()
                logger.info("Preflight ack: %s", preflight_ack)
                if on_preflight_ack:
                    await on_preflight_ack(preflight_ack)

        # ── Risk floor check (ADR-031) ──────────────────────────────────────
        proposal_floor = get_proposal_floor(proposal.candidates, self.tool_registry)

        if proposal_floor == "RED":
            trigger_tool = _find_floor_trigger(proposal.candidates, self.tool_registry, "RED")
            logger.info("Risk floor RED on tool '%s' — skipping evaluation", trigger_tool)

            refusal_rc = RiskClassification(
                tier="RED",
                weighted_score=-1.0,
                recommended_action=None,
                explanation=(
                    f"Tool '{trigger_tool}' declares risk_floor='RED'. "
                    "This action is prohibited by policy regardless of context."
                ),
                override_reason="risk_floor",
            )
            execution = self.executor.build_refusal(proposal, refusal_rc, trees=[])
            response = await self.response_generator.generate(
                user_message=message,
                risk_tier="RED",
                action_taken=execution.action_taken.tool_name,
                action_reasoning=execution.action_taken.reasoning,
                tool_result_message=execution.tool_result.message,
            )

            pipeline_result = PipelineResult(
                intent=intent,
                proposal=proposal,
                consequence_trees=[],
                evaluation_results=[],
                risk_classification=refusal_rc,
                execution=execution,
                response=response,
                bypassed=False,
                risk_floor_short_circuit=True,
                risk_floor_trigger_tool=trigger_tool,
                risk_floor_trigger_value="RED",
                preflight_ack=preflight_ack,
                preflight_ack_at=preflight_ack_at,
                metadata={"hat": hat_name, "short_circuit_reason": "risk_floor"},
            )
            await self._persist_memory(message, pipeline_result)
            return pipeline_result

        # For YELLOW/ORANGE floors, the pipeline runs but the floor is applied
        evaluation_min_tier = proposal_floor  # None, "YELLOW", or "ORANGE"

        # Check for defensive proposal requiring situation evaluation (ADR-030)
        top_candidate = proposal.candidates[0] if proposal.candidates else None
        if top_candidate and _is_defensive_proposal(top_candidate):
            should_evaluate = self._should_run_situation_evaluation(
                intent, top_candidate, gate_result, escalation_result=escalation_result
            )
            if should_evaluate:
                result = await self._handle_converse_with_evaluation(
                    message,
                    intent,
                    proposal,
                    hat_name,
                    hat,
                    conversation_history=conversation_history,
                    escalation_min_tier=escalation_min_tier,
                )
            else:
                # Genuine conversational bypass — greeting, chitchat, general inquiry (ADR-017)
                result = await self._handle_converse(
                    message,
                    intent,
                    proposal,
                    hat_name,
                    conversation_history=conversation_history,
                )
            result.escalation_trigger_matched = escalation_result.matched_trigger
            result.metadata.update(gate_metadata)
            return result

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
        effective_min_tier = _max_tier(escalation_min_tier, evaluation_min_tier)
        evaluation_results, risk_classification = await self._run_evaluation_panel(
            top_tree,
            hat,
            intent,
            proposal.candidates,
            min_tier=effective_min_tier,
        )
        logger.info(
            "Risk classification: %s (score=%.2f)",
            risk_classification.tier,
            risk_classification.weighted_score,
        )

        # Step 5: Tiered execution based on risk classification
        execution = await self._tiered_execute(risk_classification, proposal, consequence_trees)

        logger.info(
            "Result: %s (success=%s, tier=%s)",
            execution.action_taken.tool_name,
            execution.tool_result.success,
            execution.risk_tier,
        )

        # Step 6: Generate natural language response (ADR-018)
        # GREEN/YELLOW: pass through response generator for natural language
        # ORANGE/RED: build_escalation/build_refusal already produce human-readable messages
        if execution.risk_tier in ("GREEN", "YELLOW"):
            response = await self.response_generator.generate(
                user_message=message,
                risk_tier=execution.risk_tier,
                action_taken=execution.action_taken.tool_name,
                action_reasoning=execution.action_taken.reasoning,
                tool_result_message=execution.tool_result.message,
                tool_result_data=execution.tool_result.data
                if isinstance(execution.tool_result.data, dict)
                else None,
                conversation_history=conversation_history,
            )
        else:
            response = execution.tool_result.message

        # Populate risk floor metadata for non-short-circuit paths
        rf_trigger_tool = None
        rf_trigger_value = None
        if evaluation_min_tier is not None:
            rf_trigger_tool = _find_floor_trigger(
                proposal.candidates, self.tool_registry, evaluation_min_tier
            )
            rf_trigger_value = evaluation_min_tier

        pipeline_result = PipelineResult(
            intent=intent,
            proposal=proposal,
            consequence_trees=consequence_trees,
            evaluation_results=evaluation_results,
            risk_classification=risk_classification,
            execution=execution,
            response=response,
            preflight_ack=preflight_ack,
            preflight_ack_at=preflight_ack_at,
            escalation_trigger_matched=escalation_result.matched_trigger,
            risk_floor_short_circuit=False,
            risk_floor_trigger_tool=rf_trigger_tool,
            risk_floor_trigger_value=rf_trigger_value,
            metadata={
                "hat": hat_name,
                "source": source,
                "memory_context": {
                    "entities_recalled": len(memory_context.get("entities", [])),
                    "episodes_recalled": len(memory_context.get("episodes", [])),
                },
                **gate_metadata,
                **(metadata or {}),
            },
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
        conversation_history: list[dict] | None = None,
    ) -> PipelineResult:
        """Handle conversational bypass — skip consequence/evaluation/execution."""
        logger.info("Conversational bypass: skipping consequence engine and evaluation panel")

        response = await self.response_generator.converse(
            message, conversation_history=conversation_history
        )

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

    def _should_run_situation_evaluation(
        self, intent, top_candidate, gate_result, escalation_result=None
    ) -> bool:
        """Return True if the situation should be formally evaluated.

        Triggers when:
        - The proposal is defensive (converse or escalate_to_human)
        - The intent is action-bearing (not general_inquiry)
        - The converse was NOT synthesized by the parameter gate

        Escalation gate override: if an escalation trigger fired (direct or
        inherited), always evaluate regardless of intent classification.
        A message that matches an escalation trigger is not genuinely
        non-actionable even if the input gate says otherwise.
        """
        if not _is_defensive_proposal(top_candidate):
            return False

        # Escalation gate override: deterministic signal trumps LLM classification
        if escalation_result and escalation_result.triggered:
            return True

        if intent.action_requested in _SITUATION_EVAL_EXEMPT_INTENTS:
            return False
        # Don't evaluate situations where the parameter gate synthesized converse
        # (that's a clarifying question, not an adversarial decline)
        if gate_result and gate_result.promoted_converse:
            return False
        return True

    async def _handle_converse_with_evaluation(
        self,
        message: str,
        intent: Intent,
        proposal: Proposal,
        hat_name: str,
        hat_config: HatConfig | None,
        conversation_history: list[dict] | None = None,
        escalation_min_tier: str | None = None,
    ) -> PipelineResult:
        """Handle a defensive response with full situation evaluation.

        The agent responds conversationally (converse) or escalates, but the
        incoming situation is formally evaluated by the consequence engine and
        evaluation panel. The audit record includes a risk tier for the situation.
        """
        logger.info(
            "Situation evaluation: proposer selected %s for action_requested=%s",
            proposal.candidates[0].tool_name,
            intent.action_requested,
        )

        # 1. Build situation candidate from intent
        situation = SituationCandidate.from_intent(intent)

        # 2. Generate situation consequence tree
        situation_tree = await self.consequence_engine.analyze_situation(situation)

        # 3. Evaluate situation with all four evaluators
        situation_context = EvaluationContext(
            consequence_tree=situation_tree,
            hat_config=hat_config,
            constraints=hat_config.constraints if hat_config else {},
            stakeholders=hat_config.stakeholders.stakeholders if hat_config else [],
            requestor_context=intent.requestor_context,
            evaluation_mode="situation",
            original_request=message,
        )

        situation_eval_results = list(
            await asyncio.gather(*[e.evaluate(situation_context) for e in self.evaluators])
        )

        # 4. Classify situation risk
        situation_classification = classify(
            situation_eval_results,
            hat_config=hat_config,
            candidates=proposal.candidates,
            min_tier=escalation_min_tier,
        )

        logger.info(
            "Situation risk tier: %s (score: %.3f)",
            situation_classification.tier,
            situation_classification.weighted_score,
        )

        # 5. Generate conversational response, informed by situation tier
        response = await self.response_generator.converse(
            message,
            conversation_history=conversation_history,
            situation_tier=situation_classification.tier,
        )

        # 6. Build result — risk tier is the situation tier, not hardcoded GREEN
        converse_candidate = proposal.candidates[0]
        execution = ExecutionResult(
            action_taken=converse_candidate,
            tool_result=ToolResult(
                success=True,
                data=None,
                message=f"Situation evaluated as {situation_classification.tier}. Responded conversationally.",
            ),
            risk_tier=situation_classification.tier,
        )

        pipeline_result = PipelineResult(
            intent=intent,
            proposal=proposal,
            consequence_trees=[],
            evaluation_results=[],
            risk_classification=RiskClassification(
                tier=situation_classification.tier,
                weighted_score=situation_classification.weighted_score,
                explanation=f"Situation evaluation: {situation_classification.explanation}",
            ),
            execution=execution,
            response=response,
            bypassed=False,
            situation_tree=situation_tree,
            situation_evaluation_results=situation_eval_results,
            situation_risk_classification=situation_classification,
            metadata={"hat": hat_name, "evaluation_mode": "situation"},
        )

        # Memory persist
        await self._persist_memory(message, pipeline_result)

        return pipeline_result

    async def _run_evaluation_panel(
        self,
        tree: ConsequenceTree | None,
        hat: HatConfig | None,
        intent: Intent,
        candidates: list[CandidateAction],
        min_tier: str | None = None,
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
                r.evaluator_name,
                r.score,
                r.confidence,
                r.flags,
            )

        # Deterministic risk classification
        risk_classification = classify(evaluation_results, hat, candidates, min_tier=min_tier)
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
