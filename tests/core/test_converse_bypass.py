"""Tests for conversational bypass (ADR-017) and memory integration in the loop."""

import json

import pytest

from sophia.core.loop import CONVERSE_TOOL_NAME, AgentLoop, PipelineResult
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


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
    loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()

    result = await loop.process("Hello!")

    assert result.bypassed is True
    assert result.consequence_trees == []
    assert result.evaluation_results == []
    assert result.response == "Hello! Welcome to TechMart. How can I help you today?"
    assert result.execution.action_taken.tool_name == CONVERSE_TOOL_NAME
    assert result.execution.risk_tier == "GREEN"


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
