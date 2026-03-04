import json
import logging

import anthropic

from sophia.llm.provider import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Claude implementation using the Anthropic SDK."""

    def __init__(self, config):
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self.model = config.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        response_format: dict | None = None,
        conversation_history: list[dict] | None = None,
    ) -> LLMResponse:
        messages = [*(conversation_history or []), {"role": "user", "content": user_message}]

        # If a structured JSON response is requested, append instruction to the system prompt
        effective_system = system_prompt
        if response_format:
            effective_system += (
                "\n\nYou MUST respond with valid JSON only, no other text. "
                f"Follow this schema: {json.dumps(response_format)}"
            )

        logger.debug("Calling Anthropic model=%s", self.model)
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=effective_system,
            messages=messages,
        )

        content = response.content[0].text
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return LLMResponse(content=content, usage=usage, raw_response=response)
