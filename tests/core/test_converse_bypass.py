"""Tests for conversational bypass (ADR-017) and memory integration in the loop."""

import json

import pytest

from sophia.core.loop import CONVERSE_TOOL_NAME, AgentLoop, PipelineResult
from sophia.llm.prompts.core.proposer import PROPOSER_SYSTEM_PROMPT
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


# --- Prompt quality tests: verify prompts guide the real LLM correctly ---


def test_proposer_prompt_does_not_require_multiple_candidates_for_converse():
    """The proposer prompt must NOT force 2+ candidates when converse is appropriate.

    This was the root cause of Bug 1: the old prompt said 'Always provide at least
    2 candidates', so the LLM generated tool candidates alongside converse and often
    ranked the tool first.
    """
    prompt_lower = PROPOSER_SYSTEM_PROMPT.lower()
    assert "always provide at least 2" not in prompt_lower
    assert "always generate at least 2" not in prompt_lower


def test_proposer_prompt_converse_is_first_decision():
    """The converse vs tool decision should appear before the tools list.

    If the LLM reads the full tools list first, it anchors on tool selection.
    The converse decision must come BEFORE Available Tools.
    """
    converse_pos = PROPOSER_SYSTEM_PROMPT.find("converse")
    tools_pos = PROPOSER_SYSTEM_PROMPT.find("## Available Tools")
    assert converse_pos < tools_pos, (
        "Converse guidance must appear before the Available Tools section"
    )


def test_proposer_prompt_converse_only_candidate():
    """The prompt must instruct the LLM to make converse the ONLY candidate."""
    assert "only candidate" in PROPOSER_SYSTEM_PROMPT.lower() or \
           "exactly 1 candidate" in PROPOSER_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_converse_bypass_skips_pipeline(mock_llm: MockLLMProvider, cs_hat_config):
    """When proposer selects 'converse', consequence/evaluation/execution are skipped."""
    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "general_inquiry",
            "target": None,
            "parameters": {},
        }),
        # 2. Proposer — selects converse
        json.dumps({
            "candidates": [{
                "tool_name": "converse",
                "parameters": {},
                "reasoning": "User is greeting the agent, no tool needed",
                "expected_outcome": "Agent responds with a friendly greeting",
            }]
        }),
        # 3. Response generator (converse path)
        "Hello! Welcome to TechMart. How can I help you today?",
        # 4. Memory extractor
        json.dumps({
            "episode": {
                "participants": ["customer", "agent"],
                "summary": "Customer greeted the agent.",
                "actions_taken": [],
                "outcome": "Conversational exchange",
            },
            "entities": [],
            "relationships": [],
        }),
    ])

    from sophia.config import Settings
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    memory = MockMemoryProvider()
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = mock_llm
    loop.memory = memory

    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("Hello!")

    assert result.bypassed is True
    assert result.consequence_trees == []
    assert result.evaluation_results == []
    assert result.response == "Hello! Welcome to TechMart. How can I help you today?"
    assert result.execution.action_taken.tool_name == CONVERSE_TOOL_NAME
    assert result.execution.risk_tier == "GREEN"


@pytest.mark.asyncio
async def test_executor_handles_converse_without_tool_registry(tool_registry):
    """Executor.execute() handles 'converse' gracefully without calling the tool registry."""
    from sophia.core.executor import Executor
    from sophia.core.proposer import CandidateAction, Proposal
    from sophia.core.input_gate import Intent

    executor = Executor(registry=tool_registry)
    proposal = Proposal(
        intent=Intent(action_requested="general_inquiry", target=None, raw_message="Hi"),
        candidates=[
            CandidateAction(
                tool_name="converse",
                parameters={},
                reasoning="User is greeting the agent",
                expected_outcome="Agent responds with a friendly greeting",
            )
        ],
    )

    result = await executor.execute(proposal)

    assert result.tool_result.success is True
    assert result.tool_result.data is None
    assert result.tool_result.message == "Conversational response"
    assert result.action_taken.tool_name == "converse"
    assert result.risk_tier == "GREEN"


@pytest.mark.asyncio
async def test_converse_candidate_has_expected_fields():
    """The converse candidate still has reasoning and expected_outcome."""
    from sophia.core.proposer import CandidateAction

    candidate = CandidateAction(
        tool_name="converse",
        parameters={},
        reasoning="User is greeting the agent",
        expected_outcome="Agent responds with a friendly greeting",
    )
    assert candidate.tool_name == CONVERSE_TOOL_NAME
    assert candidate.reasoning != ""
    assert candidate.expected_outcome != ""


def test_pipeline_result_bypassed_field():
    """PipelineResult includes 'bypassed' flag in serialization."""
    from sophia.core.input_gate import Intent
    from sophia.core.proposer import CandidateAction, Proposal
    from sophia.core.executor import ExecutionResult
    from sophia.core.risk_classifier import RiskClassification
    from sophia.tools.base import ToolResult

    result = PipelineResult(
        intent=Intent(action_requested="general_inquiry", target=None, raw_message="Hi"),
        proposal=Proposal(intent=None, candidates=[
            CandidateAction(tool_name="converse", reasoning="greeting")
        ]),
        consequence_trees=[],
        evaluation_results=[],
        risk_classification=RiskClassification(tier="GREEN", weighted_score=0.0),
        execution=ExecutionResult(
            action_taken=CandidateAction(tool_name="converse", reasoning="greeting"),
            tool_result=ToolResult(success=True, data=None, message="Hello!"),
            risk_tier="GREEN",
        ),
        response="Hello!",
        bypassed=True,
    )

    d = result.to_dict()
    assert d["bypassed"] is True
    assert d["consequence_trees"] == []
    assert d["evaluations"] == []


@pytest.mark.asyncio
async def test_green_execution_uses_response_generator(mock_llm: MockLLMProvider, cs_hat_config):
    """When a real tool runs on GREEN, the response goes through response_generator.generate()
    so the user sees natural language instead of raw JSON/ToolResult data."""
    from sophia.config import Settings
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path

    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "inventory_check",
            "target": "all",
            "parameters": {},
        }),
        # 2. Proposer — selects a real tool
        json.dumps({
            "candidates": [{
                "tool_name": "check_current_inventory",
                "parameters": {},
                "reasoning": "Customer wants to know product availability",
                "expected_outcome": "Inventory data returned",
            }]
        }),
        # 3. Consequence tree
        json.dumps({
            "consequences": [{
                "description": "Customer sees inventory data",
                "stakeholders_affected": ["customer"],
                "probability": 0.95,
                "tangibility": 0.8,
                "harm_benefit": 0.3,
                "affected_party": "customer",
                "is_terminal": True,
                "children": [],
            }]
        }),
        # 4-7. Four evaluators (all green)
        json.dumps({"score": 0.2, "confidence": 0.8, "flags": [], "reasoning": "ok", "key_concerns": []}),
        json.dumps({"score": 0.2, "confidence": 0.8, "flags": [], "reasoning": "ok", "key_concerns": []}),
        json.dumps({"score": 0.2, "confidence": 0.8, "flags": [], "reasoning": "ok", "key_concerns": []}),
        json.dumps({"score": 0.2, "confidence": 0.8, "flags": [], "reasoning": "ok", "key_concerns": []}),
        # 8. Response generator — natural language
        "We currently have a wide selection of electronics in stock, including laptops, headphones, and gaming consoles.",
        # 9. Memory extractor
        json.dumps({
            "episode": {
                "participants": ["customer", "agent"],
                "summary": "Customer checked inventory.",
                "actions_taken": ["check_current_inventory"],
                "outcome": "Inventory data shown",
            },
            "entities": [],
            "relationships": [],
        }),
    ])

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    memory = MockMemoryProvider()
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = mock_llm
    loop.memory = memory
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("What products do you have in stock?")

    # Should NOT be bypassed (real tool execution)
    assert result.bypassed is False

    # Response should be natural language from response_generator, not raw data
    assert result.response == "We currently have a wide selection of electronics in stock, including laptops, headphones, and gaming consoles."
    assert "{" not in result.response  # No JSON leakage


@pytest.mark.asyncio
async def test_converse_bypass_has_no_preflight_ack(mock_llm: MockLLMProvider, cs_hat_config):
    """When the pipeline takes the conversational bypass path, preflight_ack is None."""
    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "general_inquiry",
            "target": None,
            "parameters": {},
        }),
        # 2. Proposer — selects converse
        json.dumps({
            "candidates": [{
                "tool_name": "converse",
                "parameters": {},
                "reasoning": "User is asking a general question",
                "expected_outcome": "Conversational response",
            }]
        }),
        # 3. Response generator (converse path)
        "Sure, I can help with that!",
        # 4. Memory extractor
        json.dumps({
            "episode": {
                "participants": ["customer", "agent"],
                "summary": "General inquiry.",
                "actions_taken": [],
                "outcome": "Conversational exchange",
            },
            "entities": [],
            "relationships": [],
        }),
    ])

    from sophia.config import Settings
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    memory = MockMemoryProvider()
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = mock_llm
    loop.memory = memory

    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("What can you help me with?")

    assert result.bypassed is True
    assert result.preflight_ack is None
    assert result.preflight_ack_at is None
