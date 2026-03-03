"""Tests for the pre-flight acknowledgment (ADR-021)."""

import pytest

from sophia.core.input_gate import Intent
from sophia.core.loop import CONVERSE_TOOL_NAME
from sophia.core.preflight_ack import CORE_DEFAULT_ACK, maybe_generate_ack
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig, HatManifest, StakeholderRegistry
from sophia.tools.base import Tool, ToolResult
from sophia.tools.registry import ToolRegistry


# --- Helpers ---


def _make_intent(action: str = "order_status", **params) -> Intent:
    return Intent(
        action_requested=action,
        target=None,
        parameters=params,
        raw_message="test",
    )


def _make_candidate(tool_name: str = "check_order_status", **params) -> CandidateAction:
    return CandidateAction(
        tool_name=tool_name,
        parameters=params,
        reasoning="test",
        expected_outcome="test",
    )


def _converse_candidate() -> CandidateAction:
    return CandidateAction(
        tool_name=CONVERSE_TOOL_NAME,
        parameters={},
        reasoning="Just chatting",
        expected_outcome="Conversational response",
    )


class _MockTool(Tool):
    """Minimal tool for testing preflight ack logic."""

    def __init__(
        self,
        name: str = "check_order_status",
        authority_level: str = "agent",
        max_financial_impact: float | None = None,
    ):
        self.name = name
        self.description = "mock"
        self.parameters = {"type": "object", "properties": {}, "required": []}
        self.authority_level = authority_level
        self.max_financial_impact = max_financial_impact

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, data=None, message="ok")


def _make_registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)
    return registry


def _make_hat_config(
    ack_enabled: bool = True,
    ack_financial_ceiling: float = 0.0,
    ack_templates: dict | None = None,
) -> HatConfig:
    raw = {
        "name": "test-hat",
        "ack_enabled": ack_enabled,
        "ack_financial_ceiling": ack_financial_ceiling,
    }
    if ack_templates is not None:
        raw["ack_templates"] = ack_templates
    return HatConfig(
        manifest=HatManifest(name="test-hat"),
        hat_path="/tmp/test",
        raw_manifest=raw,
    )


# --- Tests ---


class TestAgentLevelTool:
    """Agent-level tools with no financial impact should produce an ack."""

    def test_returns_template_for_agent_level_no_financial_impact(self):
        registry = _make_registry(_MockTool(authority_level="agent", max_financial_impact=None))
        hat = _make_hat_config()
        intent = _make_intent()
        candidates = [_make_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


class TestSupervisorLevelTool:
    """Supervisor-level tools should NOT produce an ack."""

    def test_returns_none_for_supervisor_level(self):
        registry = _make_registry(_MockTool(authority_level="supervisor"))
        hat = _make_hat_config()
        intent = _make_intent()
        candidates = [_make_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is None


class TestFinancialImpact:
    """Financial impact above ceiling should suppress ack."""

    def test_returns_none_for_impact_above_ceiling(self):
        registry = _make_registry(_MockTool(max_financial_impact=100.0))
        hat = _make_hat_config(ack_financial_ceiling=0.0)
        intent = _make_intent()
        candidates = [_make_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is None

    def test_returns_template_for_impact_below_ceiling(self):
        registry = _make_registry(_MockTool(max_financial_impact=25.0))
        hat = _make_hat_config(ack_financial_ceiling=50.0)
        intent = _make_intent()
        candidates = [_make_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is not None


class TestMasterSwitch:
    """ack_enabled=False should suppress ack."""

    def test_returns_none_when_ack_disabled(self):
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_enabled=False)
        intent = _make_intent()
        candidates = [_make_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is None


class TestConverseOnly:
    """All-converse candidate lists should not produce an ack."""

    def test_returns_none_when_all_converse(self):
        registry = _make_registry(_MockTool())
        hat = _make_hat_config()
        intent = _make_intent()
        candidates = [_converse_candidate()]

        result = maybe_generate_ack(intent, candidates, registry, hat)

        assert result is None


class TestTemplateSelection:
    """Template selection follows action_requested -> _default -> hardcoded."""

    def test_selects_action_specific_template(self):
        templates = {
            "order_status": ["Checking order {order_id}."],
            "_default": ["Default message."],
        }
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_templates=templates)
        intent = _make_intent(action="order_status", order_id="123")

        # Run multiple times to verify it never picks _default
        results = set()
        for _ in range(20):
            r = maybe_generate_ack(intent, [_make_candidate()], registry, hat)
            results.add(r)

        assert results == {"Checking order 123."}

    def test_falls_back_to_default_for_unknown_action(self):
        templates = {
            "order_status": ["Order template."],
            "_default": ["Fallback message."],
        }
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_templates=templates)
        intent = _make_intent(action="unknown_action")

        result = maybe_generate_ack(intent, [_make_candidate()], registry, hat)

        assert result == "Fallback message."

    def test_falls_back_to_hardcoded_when_no_templates(self):
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_templates=None)
        # raw_manifest won't have ack_templates key
        hat.raw_manifest.pop("ack_templates", None)
        intent = _make_intent()

        result = maybe_generate_ack(intent, [_make_candidate()], registry, hat)

        assert result == CORE_DEFAULT_ACK


class TestSlotFill:
    """Slot filling replaces {key} with intent.parameters values."""

    def test_fills_parameter_from_intent(self):
        templates = {"order_status": ["Checking order {order_id}."]}
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_templates=templates)
        intent = _make_intent(action="order_status", order_id="123456")

        result = maybe_generate_ack(intent, [_make_candidate()], registry, hat)

        assert result == "Checking order 123456."

    def test_handles_missing_slot_value_gracefully(self):
        templates = {"order_status": ["Checking order {order_id}."]}
        registry = _make_registry(_MockTool())
        hat = _make_hat_config(ack_templates=templates)
        intent = _make_intent(action="order_status")  # no order_id

        result = maybe_generate_ack(intent, [_make_candidate()], registry, hat)

        assert result is not None
        assert "{order_id}" not in result
        # Should still be a reasonable string
        assert len(result) > 0


class TestNoHatConfig:
    """When hat_config is None, ack should still work with defaults."""

    def test_returns_hardcoded_default_with_no_hat(self):
        registry = _make_registry(_MockTool())
        intent = _make_intent()

        result = maybe_generate_ack(intent, [_make_candidate()], registry, None)

        assert result == CORE_DEFAULT_ACK
