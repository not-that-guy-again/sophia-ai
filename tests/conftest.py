from pathlib import Path

import pytest

from sophia.hats.loader import load_hat, load_hat_tools
from sophia.hats.schema import HatConfig
from sophia.llm.provider import LLMProvider, LLMResponse, TokenUsage
from sophia.tools.registry import ToolRegistry

HATS_DIR = Path(__file__).resolve().parent.parent / "hats"
CS_HAT_DIR = HATS_DIR / "customer-service"


class MockLLMProvider(LLMProvider):
    """Mock LLM that returns pre-configured responses."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or []
        self._call_index = 0
        self.calls: list[dict] = []

    def set_responses(self, responses: list[str]) -> None:
        self._responses = responses
        self._call_index = 0

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        response_format: dict | None = None,
    ) -> LLMResponse:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "response_format": response_format,
        })

        if self._call_index < len(self._responses):
            content = self._responses[self._call_index]
            self._call_index += 1
        else:
            content = "{}"

        return LLMResponse(
            content=content,
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def cs_hat_config() -> HatConfig:
    """Load the customer-service hat config."""
    return load_hat(CS_HAT_DIR)


@pytest.fixture
def tool_registry(cs_hat_config: HatConfig) -> ToolRegistry:
    """Create a tool registry loaded with the customer-service hat's tools."""
    registry = ToolRegistry()
    tools = load_hat_tools(cs_hat_config)
    for tool in tools:
        registry.register(tool)
    return registry
