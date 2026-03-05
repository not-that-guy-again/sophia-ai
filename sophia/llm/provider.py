from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_response: Any = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        response_format: dict | None = None,
        conversation_history: list[dict] | None = None,
    ) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            system_prompt: The system prompt guiding the LLM's behavior.
            user_message: The user's message to respond to.
            response_format: Optional JSON schema hint for structured output.
            conversation_history: Optional prior conversation turns for context.

        Returns:
            LLMResponse with the model's response content and usage stats.
        """


def get_provider(config, model_override: str | None = None) -> LLMProvider:
    """Factory function to create the appropriate LLM provider.

    Args:
        config: Settings instance.
        model_override: If provided, use this model instead of config.llm_model.
    """
    if config.llm_provider == "anthropic":
        from sophia.llm.anthropic import AnthropicProvider

        return AnthropicProvider(config, model_override=model_override)
    elif config.llm_provider == "ollama":
        from sophia.llm.ollama import OllamaProvider

        return OllamaProvider(config, model_override=model_override)
    else:
        raise ValueError(f"Unknown LLM provider: {config.llm_provider}")
