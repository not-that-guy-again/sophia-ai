import json
import logging

from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider
from sophia.llm.prompts.core.response import CONVERSE_SYSTEM_PROMPT, RESPONSE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Generates natural language responses from pipeline output.

    Replaces raw ToolResult dumping with LLM-generated conversational responses.
    Handles all tiers (GREEN/YELLOW/ORANGE/RED) and conversational bypass.
    """

    def __init__(self, llm: LLMProvider, hat_config: HatConfig | None = None):
        self.llm = llm
        self.hat_config = hat_config

    def _get_domain_context(self) -> str:
        if self.hat_config and self.hat_config.prompts.get("system"):
            return f"## Domain Context ({self.hat_config.display_name})\n\n{self.hat_config.prompts['system']}"
        return ""

    async def generate(
        self,
        user_message: str,
        risk_tier: str,
        action_taken: str,
        action_reasoning: str,
        tool_result_message: str,
        tool_result_data: dict | None = None,
    ) -> str:
        """Generate a natural language response for a pipeline result."""
        tool_result_str = tool_result_message
        if tool_result_data:
            tool_result_str += f"\nData: {json.dumps(tool_result_data, default=str)}"

        core_prompt = RESPONSE_SYSTEM_PROMPT.format(
            domain_context=self._get_domain_context(),
            risk_tier=risk_tier,
            user_message=user_message,
            tool_result=tool_result_str,
            action_taken=action_taken,
            action_reasoning=action_reasoning,
        )
        system_prompt = assemble_prompt("response", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        return response.content.strip()

    async def converse(self, user_message: str) -> str:
        """Generate a direct conversational response (no tool execution)."""
        core_prompt = CONVERSE_SYSTEM_PROMPT.format(
            domain_context=self._get_domain_context(),
        )
        system_prompt = assemble_prompt("response", core_prompt, self.hat_config)

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        return response.content.strip()
