from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    data: Any
    message: str


class Tool(ABC):
    """Abstract base class for all tools."""

    name: str
    description: str
    parameters: dict  # JSON schema for tool parameters
    authority_level: str  # "agent", "supervisor", "admin"
    max_financial_impact: float | None = None

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Execute the tool with the given parameters."""

    def to_definition(self) -> dict:
        """Return the tool definition as a dict for LLM prompts."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "authority_level": self.authority_level,
            "max_financial_impact": self.max_financial_impact,
        }
