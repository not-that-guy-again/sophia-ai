import pytest

from sophia.services.registry import PROVIDER_REGISTRY, ServiceRegistry


# Minimal mock services for registry tests
class _StubOrderService:
    pass


class _StubCustomerService:
    pass


class _StubShippingService:
    pass


class _StubInventoryService:
    pass


class _StubCompensationService:
    pass


class _StubCloseable:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _register_stubs():
    """Register stub providers before each test, clean up after."""
    stubs = {
        ("order", "mock"): _StubOrderService,
        ("customer", "mock"): _StubCustomerService,
        ("shipping", "mock"): _StubShippingService,
        ("inventory", "mock"): _StubInventoryService,
        ("compensation", "mock"): _StubCompensationService,
    }
    original = dict(PROVIDER_REGISTRY)
    PROVIDER_REGISTRY.update(stubs)
    yield
    PROVIDER_REGISTRY.clear()
    PROVIDER_REGISTRY.update(original)


async def test_initialize_with_empty_config_defaults_to_mock():
    reg = ServiceRegistry()
    await reg.initialize({})
    assert isinstance(reg.get("order"), _StubOrderService)
    assert isinstance(reg.get("customer"), _StubCustomerService)
    await reg.teardown()


async def test_get_returns_correct_service():
    reg = ServiceRegistry()
    await reg.initialize({})
    svc = reg.get("order")
    assert isinstance(svc, _StubOrderService)
    await reg.teardown()


async def test_get_raises_key_error_for_unknown():
    reg = ServiceRegistry()
    await reg.initialize({})
    with pytest.raises(KeyError, match="nonexistent"):
        reg.get("nonexistent")
    await reg.teardown()


async def test_teardown_clears_services():
    reg = ServiceRegistry()
    await reg.initialize({})
    assert reg.get("order") is not None
    await reg.teardown()
    with pytest.raises(KeyError):
        reg.get("order")


async def test_teardown_calls_close():
    reg = ServiceRegistry()
    await reg.initialize({})
    closeable = _StubCloseable()
    reg._services["order"] = closeable
    await reg.teardown()
    assert closeable.closed is True


async def test_env_resolution(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "secret123")
    PROVIDER_REGISTRY[("order", "custom")] = type(
        "_Custom", (), {"__init__": lambda self, **kw: setattr(self, "config", kw)}
    )
    reg = ServiceRegistry()
    await reg.initialize({
        "order": {
            "provider": "custom",
            "config": {"api_key_env": "MY_API_KEY", "base_url": "https://example.com"},
        }
    })
    svc = reg.get("order")
    assert svc.config["api_key"] == "secret123"
    assert svc.config["base_url"] == "https://example.com"
    await reg.teardown()


async def test_missing_env_var_raises_clear_error():
    PROVIDER_REGISTRY[("order", "custom")] = _StubOrderService
    reg = ServiceRegistry()
    with pytest.raises(EnvironmentError, match="MISSING_VAR"):
        await reg.initialize({
            "order": {
                "provider": "custom",
                "config": {"token_env": "MISSING_VAR"},
            }
        })
