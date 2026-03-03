"""Tests for the memory provider factory function."""

import pytest

from sophia.memory.mock import MockMemoryProvider
from sophia.memory.provider import get_memory_provider


class _MockConfig:
    def __init__(self, provider: str):
        self.memory_provider = provider


def test_factory_returns_mock():
    config = _MockConfig("mock")
    provider = get_memory_provider(config)
    assert isinstance(provider, MockMemoryProvider)


def test_factory_raises_for_unknown():
    config = _MockConfig("redis")
    with pytest.raises(ValueError, match="Unknown memory provider"):
        get_memory_provider(config)


def test_factory_default_is_mock():
    """When memory_provider is not set, defaults to mock."""

    class _EmptyConfig:
        pass

    provider = get_memory_provider(_EmptyConfig())
    assert isinstance(provider, MockMemoryProvider)
