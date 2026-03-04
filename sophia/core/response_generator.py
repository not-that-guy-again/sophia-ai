import json
import logging
from datetime import datetime

from sophia.hats.prompt_assembler import assemble_prompt
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider
from sophia.llm.prompts.core.response import CONVERSE_SYSTEM_PROMPT, RESPONSE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_TIME_BUCKETS = [
    (6, 12, "morning"),
    (12, 15, "midday"),
    (15, 18, "afternoon"),
]


def _time_bucket(now: datetime | None = None) -> tuple[str, str]:
    """Return (bucket_name, HH:MM) for the current local time."""
    now = now or datetime.now()
    hour = now.hour
    for start, end, name in _TIME_BUCKETS:
        if start <= hour < end:
            return name, now.strftime("%H:%M")
    return "evening", now.strftime("%H:%M")


class ResponseGenerator:
    """Generates natural language responses from pipeline output.

    Replaces raw ToolResult dumping with LLM-generated conversational responses.
    Handles all tiers (GREEN/YELLOW/ORANGE/RED) and conversational bypass.
    """

    def __init__(
        self,
        llm: LLMProvider,
        hat_config: HatConfig | None = None,
        constitution: str = "",
    ):
        self.llm = llm
        self.hat_config = hat_config
        self.constitution = constitution

    def _get_domain_context(self) -> str:
        if self.hat_config and self.hat_config.prompts.get("system"):
            return f"## Domain Context ({self.hat_config.display_name})\n\n{self.hat_config.prompts['system']}"
        return ""

    def _constitution_with_time(self) -> str | None:
        """Return the constitution text with a time-context line appended, or None."""
        if not self.constitution:
            return None
        bucket, hhmm = _time_bucket()
        return f"{self.constitution}\n\nCurrent time context: It is currently {bucket} ({hhmm})."

    async def generate(
        self,
        user_message: str,
        risk_tier: str,
        action_taken: str,
        action_reasoning: str,
        tool_result_message: str,
        tool_result_data: dict | None = None,
        conversation_history: list[dict] | None = None,
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
        system_prompt = assemble_prompt(
            "response",
            core_prompt,
            self.hat_config,
            constitution=self._constitution_with_time(),
        )

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            conversation_history=conversation_history,
        )
        return response.content.strip()

    async def converse(self, user_message: str, conversation_history: list[dict] | None = None) -> str:
        """Generate a direct conversational response (no tool execution)."""
        core_prompt = CONVERSE_SYSTEM_PROMPT.format(
            domain_context=self._get_domain_context(),
        )
        system_prompt = assemble_prompt(
            "response",
            core_prompt,
            self.hat_config,
            constitution=self._constitution_with_time(),
        )

        response = await self.llm.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            conversation_history=conversation_history,
        )
        return response.content.strip()
