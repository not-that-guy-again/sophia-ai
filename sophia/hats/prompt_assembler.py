import logging

from sophia.hats.schema import HatConfig

logger = logging.getLogger(__name__)

# Stages whose output is seen by the end user and receive the constitution.
USER_FACING_STAGES = {"response", "memory_extract"}

# Mapping from pipeline stage names to hat prompt file keys
STAGE_TO_PROMPT_KEY = {
    "input_parse": "system",
    "proposer": "proposer",
    "consequence": "consequence",
    "eval_self": "eval_self",
    "eval_tribal": "eval_tribal",
    "eval_domain": "eval_domain",
    "eval_authority": "eval_authority",
    "response": "system",
    "memory_extract": "system",
}


def assemble_prompt(
    stage: str,
    core_prompt: str,
    hat_config: HatConfig | None = None,
    constitution: str | None = None,
) -> str:
    """Combine a core prompt with hat-specific fragment for a pipeline stage.

    Assembly order for user-facing stages:
        core_prompt → constitution → hat fragment

    For non-user-facing stages the constitution is ignored.

    Args:
        stage: Pipeline stage name (e.g., "input_parse", "proposer").
        core_prompt: The core framework prompt for this stage.
        hat_config: The active hat config, or None if no hat equipped.
        constitution: The Sophia Constitution text, or None to skip.

    Returns:
        The assembled prompt string.
    """
    parts: list[str] = [core_prompt]

    # Insert constitution for user-facing stages only.
    if constitution and stage in USER_FACING_STAGES:
        parts.append(f"## Sophia's Identity\n\n{constitution}")

    # Resolve hat fragment.
    hat_fragment = ""
    if hat_config is not None:
        prompt_key = STAGE_TO_PROMPT_KEY.get(stage)
        if prompt_key is None:
            logger.warning("Unknown pipeline stage: %s", stage)
        else:
            hat_fragment = hat_config.prompts.get(prompt_key, "")

    if hat_fragment:
        parts.append(f"## Domain-Specific Context ({hat_config.display_name})\n\n{hat_fragment}")

    return "\n\n".join(parts)
