from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class HatManifest(BaseModel):
    """Validated structure of a hat.json manifest file."""

    name: str
    version: str = "0.1.0"
    display_name: str = ""
    description: str = ""
    author: str = ""
    license: str = "Apache-2.0"
    sophia_version: str = ">=0.1.0"
    tools: list[str] = Field(default_factory=list)
    default_evaluator_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "tribal": 0.40,
            "domain": 0.25,
            "self_interest": 0.20,
            "authority": 0.15,
        }
    )
    risk_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "green": -0.1,
            "yellow": -0.4,
            "orange": -0.7,
        }
    )
    placeholder_patterns: list[str] = Field(default_factory=list)


class EvaluatorConfig(BaseModel):
    """Hat-specific evaluator configuration."""

    weight_overrides: dict[str, float] = Field(default_factory=dict)
    custom_flags: dict[str, list[str]] = Field(default_factory=dict)
    risk_thresholds: dict[str, float] = Field(default_factory=dict)


class Stakeholder(BaseModel):
    """A stakeholder defined by a hat."""

    id: str
    name: str
    interests: list[str] = Field(default_factory=list)
    harm_sensitivity: str = "medium"
    weight: float = 0.25


class StakeholderRegistry(BaseModel):
    """Collection of stakeholders from a hat."""

    stakeholders: list[Stakeholder] = Field(default_factory=list)


class HatConfig(BaseModel):
    """Fully loaded hat configuration with all components."""

    manifest: HatManifest
    hat_path: str  # Stored as string for serialization
    constraints: dict[str, Any] = Field(default_factory=dict)
    stakeholders: StakeholderRegistry = Field(default_factory=StakeholderRegistry)
    evaluator_config: EvaluatorConfig = Field(default_factory=EvaluatorConfig)
    prompts: dict[str, str] = Field(default_factory=dict)

    @property
    def path(self) -> Path:
        return Path(self.hat_path)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def display_name(self) -> str:
        return self.manifest.display_name or self.manifest.name

    @property
    def tools_module_path(self) -> Path:
        return self.path / "tools"
