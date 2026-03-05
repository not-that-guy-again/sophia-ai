import json
import logging
from dataclasses import dataclass, field

from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider
from sophia.llm.prompts.core.input_parse import INPUT_PARSE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    action_requested: str
    target: str | None
    parameters: dict = field(default_factory=dict)
    requestor_context: dict = field(default_factory=lambda: {"role": "customer"})
    raw_message: str = ""
    hat_name: str = ""


class InputGate:
    """Parses raw user messages into structured Intent objects via LLM."""

    def __init__(
        self, llm: LLMProvider, tool_definitions: str, hat_config: HatConfig | None = None
    ):
        self.llm = llm
        self.tool_definitions = tool_definitions
        self.hat_config = hat_config

    async def parse(self, raw_message: str) -> Intent:
        core_prompt = INPUT_PARSE_SYSTEM_PROMPT.format(tool_definitions=self.tool_definitions)
        system_prompt = assemble_prompt("input_parse", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=raw_message,
            response_format={"type": "json"},
        )

        logger.debug("InputGate raw LLM response: %s", response.content)

        parsed = json.loads(_extract_json(response.content))

        return Intent(
            action_requested=parsed.get("action_requested", "general_inquiry"),
            target=parsed.get("target"),
            parameters=parsed.get("parameters", {}),
            raw_message=raw_message,
            hat_name=self.hat_config.name if self.hat_config else "",
        )


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        for line in lines[1:]:
            if line.strip() == "```":
                break
            json_lines.append(line)
        return "\n".join(json_lines)
    return text
