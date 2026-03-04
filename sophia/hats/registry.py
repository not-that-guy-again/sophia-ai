import logging
from pathlib import Path

from sophia.hats.loader import discover_hats, load_hat, load_hat_tools
from sophia.hats.schema import HatConfig, HatManifest
from sophia.services.communication import CommunicationContact, CommunicationService
from sophia.services.registry import ServiceRegistry, _resolve_env_config
from sophia.tools.communication import (
    EscalateToHumanTool,
    NotifyManagerTool,
    RequestApprovalTool,
)
from sophia.tools.converse import ConverseTool
from sophia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

FRAMEWORK_COMMUNICATION_TOOLS: dict[str, type] = {
    "notify_manager": NotifyManagerTool,
    "request_approval": RequestApprovalTool,
    "escalate_to_human": EscalateToHumanTool,
}


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
        # Skip tools that are framework-provided (they get registered below)
        tools = load_hat_tools(hat_config)
        for tool in tools:
            if tool.name in FRAMEWORK_COMMUNICATION_TOOLS:
                continue
            tool.inject_services(self.service_registry)
            self.tool_registry.register(tool)

        # Register framework-level converse tool so the proposer LLM sees it
        # as a structured definition alongside hat tools
        self.tool_registry.register(ConverseTool())

        # Build communication service from hat config
        communication_service = None
        communications_cfg = hat_config.manifest.communications
        if communications_cfg:
            communication_service = self._build_communication_service(
                communications_cfg,
                hat_config.constraints,
            )

        if communication_service is None:
            from sophia.services.mock.communication import MockCommunicationService

            communication_service = MockCommunicationService()

        # Register framework communication tools if named in hat's tools list
        for tool_name, tool_cls in FRAMEWORK_COMMUNICATION_TOOLS.items():
            if tool_name in hat_config.manifest.tools:
                tool = tool_cls()
                tool.inject_communication(communication_service)
                self.tool_registry.register(tool)

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
            len(self.tool_registry.get_definitions()),
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
        elif provider == "mcp":
            from sophia.notifications.mcp_notifier import MCPNotificationService

            config = notifications_cfg.get("config", {})
            resolved = _resolve_env_config(config)
            return MCPNotificationService.from_config(resolved)
        else:
            from sophia.notifications.log import LogNotificationService

            return LogNotificationService()

    @staticmethod
    def _build_communication_service(
        communications_cfg: dict,
        constraints: dict,
    ) -> CommunicationService:
        """Build a communication service from hat config and policy constraints."""
        # Load routing policy from constraints
        policy_cfg = constraints.get("communications_policy", {})
        contacts_cfg = policy_cfg.get("contacts", {})
        policy = {
            role: CommunicationContact(
                role=role,
                channel=cfg["channel"],
                address=cfg.get("address", ""),
            )
            for role, cfg in contacts_cfg.items()
        }

        channels = communications_cfg.get("channels", {})

        if not channels:
            from sophia.services.mock.communication import MockCommunicationService

            return MockCommunicationService(policy=policy)

        from sophia.services.mcp.client import MCPClient
        from sophia.services.mcp.communication_service import MCPCommunicationService

        # Build Slack client if configured and env vars are set
        slack_client = None
        if "slack" in channels:
            try:
                cfg = _resolve_env_config(channels["slack"])
                slack_client = MCPClient(
                    server_url=cfg["server_url"],
                    server_name=cfg.get("server_name", "slack-mcp"),
                    auth_headers={"Authorization": f"Bearer {cfg['auth_token']}"}
                    if cfg.get("auth_token")
                    else None,
                )
            except (EnvironmentError, KeyError):
                logger.info("Slack MCP channel configured but env vars not set; skipping")

        # Build Gmail client if configured and env vars are set
        gmail_client = None
        if "email" in channels:
            try:
                cfg = _resolve_env_config(channels["email"])
                gmail_client = MCPClient(
                    server_url=cfg["server_url"],
                    server_name=cfg.get("server_name", "gmail-mcp"),
                    auth_headers={"Authorization": f"Bearer {cfg['auth_token']}"}
                    if cfg.get("auth_token")
                    else None,
                )
            except (EnvironmentError, KeyError):
                logger.info("Gmail MCP channel configured but env vars not set; skipping")

        return MCPCommunicationService(
            slack_client=slack_client,
            gmail_client=gmail_client,
            policy=policy,
        )

    def get_active(self) -> HatConfig | None:
        """Return the currently equipped hat config, or None."""
        return self._active

    def get_active_or_raise(self) -> HatConfig:
        """Return the active hat, or raise if none equipped."""
        if self._active is None:
            raise RuntimeError("No hat is currently equipped. Equip a hat first.")
        return self._active
