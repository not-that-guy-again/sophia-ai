import logging
from pathlib import Path

from sophia.hats.loader import discover_hats, load_hat, load_hat_tools
from sophia.hats.schema import HatConfig, HatManifest
from sophia.tools.converse import ConverseTool
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class HatRegistry:
    """Manages hat discovery, loading, and the currently equipped hat."""

    def __init__(self, hats_dir: Path, tool_registry: ToolRegistry):
        self.hats_dir = hats_dir
        self.tool_registry = tool_registry
        self._available: dict[str, HatManifest] = {}
        self._active: HatConfig | None = None
        self._scan()

    def _scan(self) -> None:
        """Scan the hats directory for available hats."""
        manifests = discover_hats(self.hats_dir)
        self._available = {m.name: m for m in manifests}
        logger.info("Found %d available hats: %s", len(self._available), list(self._available))

    def list_available(self) -> list[HatManifest]:
        """Return manifests for all discovered hats."""
        return list(self._available.values())

    def equip(self, hat_name: str) -> HatConfig:
        """Equip a hat: load config, register tools, activate."""
        if hat_name not in self._available:
            raise ValueError(
                f"Hat '{hat_name}' not found. Available: {list(self._available)}"
            )

        # Unequip current hat first
        if self._active:
            self.unequip()

        hat_path = self.hats_dir / hat_name
        hat_config = load_hat(hat_path)

        # Load and register the hat's tools
        tools = load_hat_tools(hat_config)
        for tool in tools:
            self.tool_registry.register(tool)

        # Register framework-level converse tool so the proposer LLM sees it
        # as a structured definition alongside hat tools
        self.tool_registry.register(ConverseTool())

        self._active = hat_config
        logger.info(
            "Equipped hat '%s' with %d tools",
            hat_config.display_name,
            len(tools),
        )
        return hat_config

    def unequip(self) -> None:
        """Remove the current hat: clear tools and domain context."""
        if self._active:
            logger.info("Unequipping hat '%s'", self._active.name)
            self.tool_registry.clear()
            self._active = None

    def get_active(self) -> HatConfig | None:
        """Return the currently equipped hat config, or None."""
        return self._active

    def get_active_or_raise(self) -> HatConfig:
        """Return the active hat, or raise if none equipped."""
        if self._active is None:
            raise RuntimeError("No hat is currently equipped. Equip a hat first.")
        return self._active
