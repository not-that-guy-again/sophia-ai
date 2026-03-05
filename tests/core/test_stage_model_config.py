"""Tests for _build_model_config helper (ADR-032)."""

from sophia.config import Settings
from sophia.core.loop import _build_model_config


def test_build_model_config_all_none_returns_fallback_for_all_stages():
    """When no per-stage overrides are set, all stages use the fallback model."""
    s = Settings(llm_model="claude-sonnet-4-6")
    config = _build_model_config(s)

    assert config == {
        "input_gate": "claude-sonnet-4-6",
        "proposer": "claude-sonnet-4-6",
        "consequence": "claude-sonnet-4-6",
        "evaluators": "claude-sonnet-4-6",
        "response_gen": "claude-sonnet-4-6",
        "memory": "claude-sonnet-4-6",
    }


def test_build_model_config_partial_overrides_fill_correctly():
    """Stages with overrides use the override; others use the fallback."""
    s = Settings(
        llm_model="claude-sonnet-4-6",
        llm_model_evaluators="claude-haiku-4-5-20251001",
        llm_model_input_gate="claude-haiku-4-5-20251001",
    )
    config = _build_model_config(s)

    assert config["evaluators"] == "claude-haiku-4-5-20251001"
    assert config["input_gate"] == "claude-haiku-4-5-20251001"
    assert config["proposer"] == "claude-sonnet-4-6"
    assert config["consequence"] == "claude-sonnet-4-6"
    assert config["response_gen"] == "claude-sonnet-4-6"
    assert config["memory"] == "claude-sonnet-4-6"


def test_build_model_config_all_overrides_set():
    """When all overrides are set, no stage uses the fallback."""
    s = Settings(
        llm_model="claude-sonnet-4-6",
        llm_model_input_gate="model-a",
        llm_model_proposer="model-b",
        llm_model_consequence="model-c",
        llm_model_evaluators="model-d",
        llm_model_response_gen="model-e",
        llm_model_memory="model-f",
    )
    config = _build_model_config(s)

    assert config == {
        "input_gate": "model-a",
        "proposer": "model-b",
        "consequence": "model-c",
        "evaluators": "model-d",
        "response_gen": "model-e",
        "memory": "model-f",
    }
    # None of the values should be the fallback
    assert "claude-sonnet-4-6" not in config.values()
