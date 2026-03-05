"""Tests for the pre-flight parameter gate (ADR-019)."""

import pytest

from sophia.core.parameter_gate import (
    ParameterGate,
)
from sophia.core.proposer import CandidateAction, Proposal
from sophia.core.input_gate import Intent
from sophia.core.loop import CONVERSE_TOOL_NAME
from sophia.tools.registry import ToolRegistry


# --- Helpers ---


def _make_proposal(*candidates: CandidateAction) -> Proposal:
    return Proposal(
        intent=Intent(action_requested="test", target=None, raw_message="test"),
        candidates=list(candidates),
    )


def _converse_candidate(reasoning: str = "Just chatting") -> CandidateAction:
    return CandidateAction(
        tool_name=CONVERSE_TOOL_NAME,
        parameters={},
        reasoning=reasoning,
        expected_outcome="Conversational response",
    )


# --- Placeholder detection ---


class TestPlaceholderDetection:
    """Candidates with placeholder values in required params fail validation."""

    def test_unknown_placeholder_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "UNKNOWN"},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))

        assert len(result.validations) == 1
        assert result.validations[0].passed is False
        assert any("UNKNOWN" in f for f in result.validations[0].failures)

    def test_tbd_placeholder_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "TBD"},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False

    def test_na_placeholder_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "N/A"},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False

    def test_empty_string_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": ""},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False
        assert any("empty" in f.lower() for f in result.validations[0].failures)

    def test_whitespace_only_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "   "},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False

    def test_none_value_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": None},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False
        assert any("missing" in f.lower() for f in result.validations[0].failures)


# --- Valid parameters pass ---


class TestValidParametersPass:
    def test_real_order_id_passes(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "ORD-12345"},
            reasoning="Looking up order",
        )
        result = gate.validate(_make_proposal(candidate))

        assert result.validations[0].passed is True
        assert result.validations[0].failures == []
        assert candidate in result.surviving_candidates


# --- Converse candidates skip validation ---


class TestConverseSkipsValidation:
    def test_converse_always_passes(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = _converse_candidate()
        result = gate.validate(_make_proposal(candidate))

        assert result.validations[0].passed is True
        assert candidate in result.surviving_candidates
        assert result.promoted_converse is False


# --- Missing required field ---


class TestMissingRequiredField:
    def test_missing_required_param_fails(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={},
            reasoning="Need order ID",
        )
        result = gate.validate(_make_proposal(candidate))

        assert result.validations[0].passed is False
        assert any("missing" in f.lower() for f in result.validations[0].failures)


# --- Unknown tool passes ---


class TestUnknownToolPasses:
    def test_unknown_tool_not_blocked(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="nonexistent_tool",
            parameters={"anything": "UNKNOWN"},
            reasoning="Testing unknown tool",
        )
        result = gate.validate(_make_proposal(candidate))

        assert result.validations[0].passed is True
        assert candidate in result.surviving_candidates


# --- Mixed proposal ---


class TestMixedProposal:
    def test_mixed_passing_and_failing(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        good = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "ORD-12345"},
            reasoning="Valid order lookup",
        )
        bad = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "UNKNOWN"},
            reasoning="Placeholder order ID",
        )
        result = gate.validate(_make_proposal(good, bad))

        assert good in result.surviving_candidates
        assert bad not in result.surviving_candidates
        assert result.promoted_converse is False


# --- All-fail with existing converse ---


class TestAllFailWithConverse:
    def test_converse_promoted_when_all_fail(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        bad = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "UNKNOWN"},
            reasoning="Placeholder order ID",
        )
        converse = _converse_candidate("Missing order info")
        result = gate.validate(_make_proposal(bad, converse))

        assert result.promoted_converse is True
        assert len(result.surviving_candidates) == 1
        assert result.surviving_candidates[0].tool_name == CONVERSE_TOOL_NAME


# --- All-fail without converse (synthesized) ---


class TestAllFailSynthesizesConverse:
    def test_converse_synthesized_when_all_fail_and_no_converse(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry)
        bad = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "UNKNOWN"},
            reasoning="Placeholder order ID",
        )
        result = gate.validate(_make_proposal(bad))

        assert result.promoted_converse is True
        assert len(result.surviving_candidates) == 1
        synthesized = result.surviving_candidates[0]
        assert synthesized.tool_name == CONVERSE_TOOL_NAME
        assert "check_order_status" in synthesized.reasoning
        assert "UNKNOWN" in synthesized.reasoning


# --- Hat placeholder extension ---


class TestHatPlaceholderExtension:
    def test_extra_placeholders_merged(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry, extra_placeholders={"PENDING", "0000"})
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "PENDING"},
            reasoning="Testing hat placeholders",
        )
        result = gate.validate(_make_proposal(candidate))

        assert result.validations[0].passed is False
        assert any("PENDING" in f for f in result.validations[0].failures)

    def test_extra_placeholder_numeric_string(self, tool_registry: ToolRegistry):
        gate = ParameterGate(tool_registry, extra_placeholders={"0000"})
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "0000"},
            reasoning="Testing hat placeholders",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False


# --- Case insensitivity ---


class TestCaseInsensitivity:
    @pytest.mark.parametrize("value", ["Unknown", "UNKNOWN", "unknown", "UnKnOwN"])
    def test_placeholder_case_insensitive(self, tool_registry: ToolRegistry, value: str):
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": value},
            reasoning="Testing case insensitivity",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is False


# --- Non-required fields ignored ---


class TestNonRequiredFieldsIgnored:
    def test_placeholder_in_optional_field_passes(self, tool_registry: ToolRegistry):
        """offer_free_shipping has optional order_id — placeholder there should not fail."""
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="offer_free_shipping",
            parameters={
                "customer_id": "CUST-001",
                "reason": "Delayed shipment",
                "order_id": "UNKNOWN",  # optional field
            },
            reasoning="Testing optional param placeholder",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is True


# --- Tool with no required fields ---


class TestToolWithNoRequiredFields:
    def test_no_required_fields_passes(self, tool_registry: ToolRegistry):
        """A tool with no required params passes even with empty parameters."""
        # The converse tool has no required fields, but we skip it.
        # check_current_inventory also has no required fields.
        gate = ParameterGate(tool_registry)
        candidate = CandidateAction(
            tool_name="check_current_inventory",
            parameters={},
            reasoning="Checking inventory",
        )
        result = gate.validate(_make_proposal(candidate))
        assert result.validations[0].passed is True


# --- GateResult serialization for audit ---


class TestGateResultSerialization:
    def test_validations_serializable(self, tool_registry: ToolRegistry):
        """Validation results can be serialized to dicts for PipelineResult.metadata."""
        gate = ParameterGate(tool_registry)
        bad = CandidateAction(
            tool_name="check_order_status",
            parameters={"order_id": "UNKNOWN"},
            reasoning="Placeholder",
        )
        result = gate.validate(_make_proposal(bad))

        # Serialize the way loop.py does it
        serialized = [
            {
                "tool_name": v.candidate.tool_name,
                "passed": v.passed,
                "failures": v.failures,
            }
            for v in result.validations
        ]
        assert len(serialized) == 1
        assert serialized[0]["tool_name"] == "check_order_status"
        assert serialized[0]["passed"] is False
        assert len(serialized[0]["failures"]) > 0
