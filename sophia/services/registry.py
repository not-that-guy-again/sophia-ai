import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Maps (service_name, provider_name) -> class.
# Mock providers are registered here by default.
# Backend modules append to this dict when imported.


def _default_providers() -> dict[tuple[str, str], type]:
    from sophia.services.mock import (
        MockCompensationService,
        MockCustomerService,
        MockInventoryService,
        MockOrderService,
        MockShippingService,
    )

    return {
        ("order", "mock"): MockOrderService,
        ("customer", "mock"): MockCustomerService,
        ("shipping", "mock"): MockShippingService,
        ("inventory", "mock"): MockInventoryService,
        ("compensation", "mock"): MockCompensationService,
    }


PROVIDER_REGISTRY: dict[tuple[str, str], type] = _default_providers()

# MCP service adapter classes keyed by service name
_MCP_SERVICE_CLASSES: dict[str, type] = {}

# Platform mapping modules keyed by platform name
PLATFORM_MAPPINGS: dict[str, str] = {
    "shopify": "sophia.services.mcp.shopify_mapping",
}

# Mapping function name convention per service
_MAPPING_FUNCTIONS: dict[str, str] = {
    "order": "{platform}_order_mapping",
    "customer": "{platform}_customer_mapping",
    "shipping": "{platform}_shipping_mapping",
    "inventory": "{platform}_inventory_mapping",
    "compensation": "{platform}_compensation_mapping",
}


def _get_mcp_service_classes() -> dict[str, type]:
    """Lazy-load MCP service adapter classes."""
    global _MCP_SERVICE_CLASSES
    if not _MCP_SERVICE_CLASSES:
        from sophia.services.mcp.compensation_service import MCPCompensationService
        from sophia.services.mcp.customer_service import MCPCustomerService
        from sophia.services.mcp.inventory_service import MCPInventoryService
        from sophia.services.mcp.order_service import MCPOrderService
        from sophia.services.mcp.shipping_service import MCPShippingService

        _MCP_SERVICE_CLASSES = {
            "order": MCPOrderService,
            "customer": MCPCustomerService,
            "shipping": MCPShippingService,
            "inventory": MCPInventoryService,
            "compensation": MCPCompensationService,
        }
    return _MCP_SERVICE_CLASSES


class ServiceRegistry:
    """Constructs, holds, and tears down service instances for the active hat."""

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._mcp_clients: dict[tuple[str, str], Any] = {}  # (url, name) -> MCPClient

    async def initialize(self, backends_config: dict) -> None:
        service_names = ["order", "customer", "shipping", "inventory", "compensation"]
        for service_name in service_names:
            backend = backends_config.get(service_name, {})
            provider_name = backend.get("provider", "mock") if backend else "mock"
            raw_config = backend.get("config", {}) if backend else {}

            # Resolve _env values from environment
            resolved_config = _resolve_env_config(raw_config)

            if provider_name == "mcp":
                instance = await self._initialize_mcp_service(
                    service_name, resolved_config
                )
            else:
                key = (service_name, provider_name)
                cls = PROVIDER_REGISTRY.get(key)
                if cls is None:
                    raise ValueError(
                        f"No provider registered for ({service_name!r}, {provider_name!r}). "
                        f"Available: {[k for k in PROVIDER_REGISTRY if k[0] == service_name]}"
                    )
                instance = cls(**resolved_config) if resolved_config else cls()

            self._services[service_name] = instance
            logger.info("Initialized %s service: %s", service_name, provider_name)

    async def _initialize_mcp_service(self, service_name: str, config: dict) -> Any:
        """Initialize an MCP-backed service instance."""
        from sophia.services.mcp import client as _mcp_client_mod

        MCPClient = _mcp_client_mod.MCPClient  # noqa: N806

        server_url = config.get("server_url")
        server_name = config.get("server_name", "mcp-server")
        auth_token = config.get("auth_token")
        platform = config.get("platform")

        if not server_url:
            raise ValueError(
                f"MCP provider for {service_name!r} requires 'server_url' in config"
            )
        if not platform:
            raise ValueError(
                f"MCP provider for {service_name!r} requires 'platform' in config"
            )

        if platform not in PLATFORM_MAPPINGS:
            raise ValueError(
                f"Unknown MCP platform {platform!r}. "
                f"Available: {sorted(PLATFORM_MAPPINGS.keys())}"
            )

        # Connection dedup: reuse client for same (url, name)
        client_key = (server_url, server_name)
        if client_key not in self._mcp_clients:
            auth_headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
            client = MCPClient(
                server_url=server_url,
                server_name=server_name,
                auth_headers=auth_headers,
            )
            await client.connect()
            self._mcp_clients[client_key] = client
            logger.info("Connected MCP client to %s (%s)", server_name, server_url)
        else:
            logger.info(
                "Reusing MCP client for %s (%s)", server_name, server_url
            )

        client = self._mcp_clients[client_key]

        # Load platform mapping module
        mapping_module_name = PLATFORM_MAPPINGS[platform]
        mapping_module = importlib.import_module(mapping_module_name)

        # Get the mapping function for this service
        func_name_template = _MAPPING_FUNCTIONS.get(service_name)
        if not func_name_template:
            raise ValueError(f"No MCP mapping function defined for service {service_name!r}")
        func_name = func_name_template.format(platform=platform)

        mapping_func = getattr(mapping_module, func_name, None)
        if mapping_func is None:
            raise ValueError(
                f"Platform mapping module {mapping_module_name!r} has no "
                f"function {func_name!r}"
            )

        tool_mapping = mapping_func()

        # Construct the MCP service adapter
        mcp_classes = _get_mcp_service_classes()
        service_cls = mcp_classes.get(service_name)
        if service_cls is None:
            raise ValueError(f"No MCP adapter class for service {service_name!r}")

        instance = service_cls(client=client, tool_mapping=tool_mapping)

        # Validate mapping — log warnings for missing tools
        adapter = instance.adapter
        missing = adapter.validate_mapping()
        if missing:
            logger.warning(
                "MCP service %s: tools not found on server: %s",
                service_name,
                missing,
            )

        return instance

    def get(self, service_name: str) -> Any:
        if service_name not in self._services:
            raise KeyError(
                f"Service {service_name!r} not found. "
                f"Available: {list(self._services)}"
            )
        return self._services[service_name]

    async def teardown(self) -> None:
        for name, service in self._services.items():
            if hasattr(service, "close") and callable(service.close):
                logger.info("Closing service: %s", name)
                await service.close()
        self._services.clear()

        for (url, name), client in self._mcp_clients.items():
            logger.info("Closing MCP client: %s (%s)", name, url)
            await client.close()
        self._mcp_clients.clear()


def _resolve_env_config(config: dict) -> dict:
    """Replace config values ending in '_env' with the corresponding env var."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str) and key.endswith("_env"):
            env_var = value
            env_value = os.environ.get(env_var)
            if env_value is None:
                raise EnvironmentError(
                    f"Environment variable {env_var!r} required by config key "
                    f"{key!r} is not set"
                )
            # Strip the _env suffix for the resolved key
            resolved_key = key[: -len("_env")]
            resolved[resolved_key] = env_value
        else:
            resolved[key] = value
    return resolved
