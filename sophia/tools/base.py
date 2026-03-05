from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sophia.services.registry import ServiceRegistry


@dataclass
class ToolResult:
    success: bool
    data: Any
    message: str


_VALID_RISK_FLOORS = {"GREEN", "YELLOW", "ORANGE", "RED", None}


class Tool(ABC):
    """Abstract base class for all tools."""

    name: str
    description: str
    parameters: dict  # JSON schema for tool parameters
    authority_level: str  # "agent", "supervisor", "admin"
    max_financial_impact: float | None = None
    risk_floor: str | None = None  # "GREEN" | "YELLOW" | "ORANGE" | "RED" | None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        floor = getattr(cls, "risk_floor", None)
        if floor not in _VALID_RISK_FLOORS:
            raise ValueError(
                f"Tool '{getattr(cls, 'name', cls.__name__)}' has invalid risk_floor "
                f"'{floor}'. Must be one of {sorted(str(v) for v in _VALID_RISK_FLOORS if v)}."
            )

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Execute the tool with the given parameters."""

    def inject_services(self, services: "ServiceRegistry") -> None:
        """Override to receive service instances. Called during hat equip.
        Default implementation does nothing — tools that don't need
        services are unaffected."""
        pass

    def to_definition(self) -> dict:
        """Return the tool definition as a dict for LLM prompts."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "authority_level": self.authority_level,
            "max_financial_impact": self.max_financial_impact,
            "risk_floor": self.risk_floor,
        }
