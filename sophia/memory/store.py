import logging

from sophia.hats.schema import HatConfig

logger = logging.getLogger(__name__)


class MemoryStore:
    """Unified memory interface. Domain context is loaded from the active hat."""

    def __init__(self):
        self._hat_config: HatConfig | None = None

    def load_from_hat(self, hat_config: HatConfig) -> None:
        """Load domain context from a hat configuration."""
        self._hat_config = hat_config
        logger.info("Memory store loaded from hat '%s'", hat_config.name)

    @property
    def domain_constraints(self) -> dict:
        if self._hat_config is None:
            return {}
        return self._hat_config.constraints

    @property
    def stakeholders(self) -> dict:
        if self._hat_config is None:
            return {}
        return self._hat_config.stakeholders.model_dump()

    def clear(self) -> None:
        """Clear loaded domain context (hat unequipped)."""
        self._hat_config = None
