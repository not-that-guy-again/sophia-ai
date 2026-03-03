import json
import logging

import httpx

from sophia.llm.provider import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local model implementation using Ollama's HTTP API."""

    def __init__(self, config):
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model = config.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        response_format: dict | None = None,
    ) -> LLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if response_format:
            payload["format"] = "json"

        logger.debug("Calling Ollama model=%s at %s", self.model, self.base_url)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["message"]["content"]
        usage = TokenUsage(
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

        return LLMResponse(content=content, usage=usage, raw_response=data)
