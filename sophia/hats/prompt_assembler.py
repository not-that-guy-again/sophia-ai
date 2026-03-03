import logging

from sophia.hats.schema import HatConfig

logger = logging.getLogger(__name__)

# Mapping from pipeline stage names to hat prompt file keys
STAGE_TO_PROMPT_KEY = {
    "input_parse": "system",
    "proposer": "proposer",
    "consequence": "consequence",
    "eval_self": "eval_self",
    "eval_tribal": "eval_tribal",
    "eval_domain": "eval_domain",
    "eval_authority": "eval_authority",
}


def assemble_prompt(stage: str, core_prompt: str, hat_config: HatConfig | None = None) -> str:
    """Combine a core prompt with hat-specific fragment for a pipeline stage.

    Args:
        stage: Pipeline stage name (e.g., "input_parse", "proposer").
        core_prompt: The core framework prompt for this stage.
        hat_config: The active hat config, or None if no hat equipped.

    Returns:
        The assembled prompt string (core + hat fragment if available).
    """
    if hat_config is None:
        return core_prompt

    prompt_key = STAGE_TO_PROMPT_KEY.get(stage)
    if prompt_key is None:
        logger.warning("Unknown pipeline stage: %s", stage)
        return core_prompt

    hat_fragment = hat_config.prompts.get(prompt_key, "")
    if not hat_fragment:
        return core_prompt

    return f"{core_prompt}\n\n## Domain-Specific Context ({hat_config.display_name})\n\n{hat_fragment}"
