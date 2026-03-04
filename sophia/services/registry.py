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


class ServiceRegistry:
    """Constructs, holds, and tears down service instances for the active hat."""

    def __init__(self):
        self._services: dict[str, Any] = {}

    async def initialize(self, backends_config: dict) -> None:
        service_names = ["order", "customer", "shipping", "inventory", "compensation"]
        for service_name in service_names:
            backend = backends_config.get(service_name, {})
            provider_name = backend.get("provider", "mock") if backend else "mock"
            raw_config = backend.get("config", {}) if backend else {}

            # Resolve _env values from environment
            resolved_config = _resolve_env_config(raw_config)

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
