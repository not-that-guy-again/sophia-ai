"""Tests for prompt_assembler with constitution injection."""

from sophia.hats.prompt_assembler import USER_FACING_STAGES, assemble_prompt
from sophia.hats.schema import HatConfig, HatManifest, StakeholderRegistry


def _make_hat(display_name: str = "TestHat", system_prompt: str = "Hat system prompt") -> HatConfig:
    return HatConfig(
        hat_path="/tmp/test-hat",
        manifest=HatManifest(
            name="test",
            display_name=display_name,
            version="1.0.0",
            description="test hat",
            tools=[],
        ),
        prompts={"system": system_prompt},
        constraints={},
        stakeholders=StakeholderRegistry(stakeholders=[]),
    )


CORE = "Core prompt text."
CONSTITUTION = "I am Sophia."
HAT = _make_hat()


def test_user_facing_stage_three_layers():
    """User-facing stages produce core → constitution → hat in order."""
    result = assemble_prompt("response", CORE, HAT, constitution=CONSTITUTION)
    assert result.index(CORE) < result.index(CONSTITUTION) < result.index("Hat system prompt")
    assert "## Sophia's Identity" in result
    assert f"## Domain-Specific Context ({HAT.display_name})" in result


def test_non_user_facing_stage_no_constitution():
    """Non-user-facing stages omit the constitution even if provided."""
    result = assemble_prompt("proposer", CORE, HAT, constitution=CONSTITUTION)
    assert CONSTITUTION not in result
    assert CORE in result


def test_user_facing_stage_constitution_none():
    """Passing constitution=None still produces a valid two-layer prompt."""
    result = assemble_prompt("response", CORE, HAT, constitution=None)
    assert CORE in result
    assert "Hat system prompt" in result
    assert "Sophia's Identity" not in result


def test_user_facing_stage_no_hat():
    """Constitution is injected even when no hat is equipped."""
    result = assemble_prompt("response", CORE, hat_config=None, constitution=CONSTITUTION)
    assert "## Sophia's Identity" in result
    assert CONSTITUTION in result


def test_memory_extract_is_user_facing():
    """memory_extract should also receive the constitution."""
    assert "memory_extract" in USER_FACING_STAGES
    result = assemble_prompt("memory_extract", CORE, HAT, constitution=CONSTITUTION)
    assert CONSTITUTION in result
