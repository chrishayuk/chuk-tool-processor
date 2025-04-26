# tests/tool_processor/registry/test_provider.py
import pytest
import chuk_tool_processor.registry.provider as provider_module
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class DummyRegistry(ToolRegistryInterface):
    def register_tool(self, *args, **kwargs):
        pass

    def get_tool(self, name, namespace="default"):
        return f"dummy:{namespace}.{name}"

    def get_metadata(self, name, namespace="default"):
        return None

    def list_tools(self, namespace=None):
        return []

    def list_namespaces(self):
        return []


@pytest.fixture(autouse=True)
def clear_registry():
    ToolRegistryProvider._registry = None
    yield
    ToolRegistryProvider._registry = None


def test_get_registry_calls_default_once(monkeypatch):
    calls = []
    def fake_default():
        calls.append(True)
        return DummyRegistry()
    # Patch the name that provider.py actually calls
    monkeypatch.setattr(provider_module, "get_registry", fake_default)

    r1 = ToolRegistryProvider.get_registry()
    assert isinstance(r1, DummyRegistry)
    assert len(calls) == 1

    r2 = ToolRegistryProvider.get_registry()
    assert r2 is r1
    assert len(calls) == 1


def test_set_registry_overrides(monkeypatch):
    # make the default factory blow up if called
    monkeypatch.setattr(provider_module, "get_registry", lambda: (_ for _ in ()).throw(Exception("shouldn't call")))

    custom = DummyRegistry()
    ToolRegistryProvider.set_registry(custom)
    assert ToolRegistryProvider.get_registry() is custom


def test_setting_none_resets_to_default(monkeypatch):
    calls = []
    dummy2 = DummyRegistry()
    monkeypatch.setattr(provider_module, "get_registry", lambda: (calls.append(True), dummy2)[1])

    ToolRegistryProvider.set_registry(None)
    r = ToolRegistryProvider.get_registry()
    assert r is dummy2
    assert calls == [True]


def test_multiple_overrides_work():
    a = DummyRegistry()
    b = DummyRegistry()

    ToolRegistryProvider.set_registry(a)
    assert ToolRegistryProvider.get_registry() is a

    ToolRegistryProvider.set_registry(b)
    assert ToolRegistryProvider.get_registry() is b

