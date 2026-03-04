import logging
from pathlib import Path

from sophia.hats.loader import discover_hats, load_hat, load_hat_tools
from sophia.hats.schema import HatConfig, HatManifest
from sophia.services.registry import ServiceRegistry
from sophia.tools.converse import ConverseTool
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class HatRegistry:
    """Manages hat discovery, loading, and the currently equipped hat."""

    def __init__(self, hats_dir: Path, tool_registry: ToolRegistry):
        self.hats_dir = hats_dir
        self.tool_registry = tool_registry
        self.service_registry = ServiceRegistry()
        self._available: dict[str, HatManifest] = {}
        self._active: HatConfig | None = None
        self.memory = None  # Set by AgentLoop after init
        self.agent_loop = None  # Set by AgentLoop after init
        self._scan()

    def _scan(self) -> None:
        """Scan the hats directory for available hats."""
        manifests = discover_hats(self.hats_dir)
        self._available = {m.name: m for m in manifests}
        logger.info("Found %d available hats: %s", len(self._available), list(self._available))

    def list_available(self) -> list[HatManifest]:
        """Return manifests for all discovered hats."""
        return list(self._available.values())

    async def equip(self, hat_name: str) -> HatConfig:
        """Equip a hat: load config, initialize services, register tools, activate."""
        if hat_name not in self._available:
            raise ValueError(
                f"Hat '{hat_name}' not found. Available: {list(self._available)}"
            )

        # Unequip current hat first
        if self._active:
            await self.unequip()

        hat_path = self.hats_dir / hat_name
        hat_config = load_hat(hat_path)

        # Initialize services from hat backend config
        await self.service_registry.teardown()
        await self.service_registry.initialize(hat_config.manifest.backends)

        # Load and register the hat's tools, injecting services
        tools = load_hat_tools(hat_config)
        for tool in tools:
            tool.inject_services(self.service_registry)
            self.tool_registry.register(tool)

        # Register framework-level converse tool so the proposer LLM sees it
        # as a structured definition alongside hat tools
        self.tool_registry.register(ConverseTool())

        # Build notification service if hat config has notifications block
        notification_service = None
        notifications_cfg = hat_config.manifest.notifications
        if notifications_cfg:
            notification_service = self._build_notification_service(notifications_cfg)

        # Configure webhook routing if hat defines webhooks
        if hat_config.manifest.webhooks:
            from sophia.api.webhook_routes import configure_webhooks

            configure_webhooks(
                hat_config.manifest.webhooks,
                memory=self.memory,
                agent_loop=self.agent_loop,
                notification_service=notification_service,
            )

        self._active = hat_config
        logger.info(
            "Equipped hat '%s' with %d tools",
            hat_config.display_name,
            len(tools),
        )
        return hat_config

    async def unequip(self) -> None:
        """Remove the current hat: tear down services, clear tools and domain context."""
        if self._active:
            logger.info("Unequipping hat '%s'", self._active.name)
            await self.service_registry.teardown()
            self.tool_registry.clear()

            from sophia.api.webhook_routes import teardown_webhooks

            teardown_webhooks()
            self._active = None

    @staticmethod
    def _build_notification_service(notifications_cfg: dict):
        """Construct a notification service from hat config."""
        provider = notifications_cfg.get("provider", "log")
        if provider == "webhook":
            from sophia.notifications.webhook_notifier import WebhookNotificationService
            url = notifications_cfg.get("webhook_url", "")
            return WebhookNotificationService(webhook_url=url)
        else:
            from sophia.notifications.log import LogNotificationService
            return LogNotificationService()

    def get_active(self) -> HatConfig | None:
        """Return the currently equipped hat config, or None."""
        return self._active

    def get_active_or_raise(self) -> HatConfig:
        """Return the active hat, or raise if none equipped."""
        if self._active is None:
            raise RuntimeError("No hat is currently equipped. Equip a hat first.")
        return self._active
