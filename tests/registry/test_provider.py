# tests/tool_processor/registry/test_provider.py
import asyncio

import pytest
import pytest_asyncio

from chuk_tool_processor.registry import provider as provider_module
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.provider import ToolRegistryProvider


class DummyRegistry(ToolRegistryInterface):
    async def register_tool(self, *args, **kwargs):
        pass

    async def get_tool(self, name, namespace="default"):
        return f"dummy:{namespace}.{name}"

    async def get_tool_strict(self, name, namespace="default"):
        tool = await self.get_tool(name, namespace)
        if not tool:
            raise KeyError(f"Tool {namespace}.{name} not found")
        return tool

    async def get_metadata(self, name, namespace="default"):
        return None

    async def list_tools(self, namespace=None):
        return []

    async def list_namespaces(self):
        return []

    async def list_metadata(self, namespace=None):
        return []


@pytest_asyncio.fixture(autouse=True)
async def clear_registry():
    # Reset both the module-level and class-level registry
    await ToolRegistryProvider.reset()
    yield
    await ToolRegistryProvider.reset()


@pytest.mark.asyncio
async def test_get_registry_calls_default_once(monkeypatch):
    calls = []

    async def fake_default():
        calls.append(True)
        return DummyRegistry()

    # Patch the async get_registry function
    monkeypatch.setattr(provider_module, "get_registry", fake_default)

    r1 = await ToolRegistryProvider.get_registry()
    assert isinstance(r1, DummyRegistry)
    assert len(calls) == 1

    r2 = await ToolRegistryProvider.get_registry()
    assert r2 is r1
    assert len(calls) == 1  # Should not be called again


@pytest.mark.asyncio
async def test_set_registry_overrides(monkeypatch):
    # Make the default factory blow up if called
    async def failing_default():
        raise Exception("shouldn't call")

    monkeypatch.setattr(provider_module, "get_registry", failing_default)

    # Set a custom registry
    custom = DummyRegistry()
    await ToolRegistryProvider.set_registry(custom)

    # Verify it's used
    result = await ToolRegistryProvider.get_registry()
    assert result is custom


@pytest.mark.asyncio
async def test_setting_none_resets_to_default(monkeypatch):
    calls = []
    dummy2 = DummyRegistry()

    async def patched_default():
        calls.append(True)
        return dummy2

    monkeypatch.setattr(provider_module, "get_registry", patched_default)

    # Reset registry to None
    await ToolRegistryProvider.set_registry(None)

    # Should use the factory function
    r = await ToolRegistryProvider.get_registry()
    assert r is dummy2
    assert calls == [True]


@pytest.mark.asyncio
async def test_multiple_overrides_work():
    a = DummyRegistry()
    b = DummyRegistry()

    await ToolRegistryProvider.set_registry(a)
    result_a = await ToolRegistryProvider.get_registry()
    assert result_a is a

    await ToolRegistryProvider.set_registry(b)
    result_b = await ToolRegistryProvider.get_registry()
    assert result_b is b


@pytest.mark.asyncio
async def test_thread_safety():
    """Test that concurrent access doesn't cause issues."""
    # Set up a slow registry factory
    calls = []

    async def slow_factory():
        await asyncio.sleep(0.05)  # Short delay
        calls.append(True)
        return DummyRegistry()

    # Clear and patch registry
    await ToolRegistryProvider.reset()
    provider_module._default_registry = slow_factory

    # Create multiple concurrent requests
    tasks = [ToolRegistryProvider.get_registry() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    # All results should be the same instance
    assert all(r is results[0] for r in results)
    # Factory should only be called once
    assert len(calls) == 1
