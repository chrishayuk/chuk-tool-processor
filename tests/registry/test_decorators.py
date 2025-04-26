# tests/tool_processor/registry/test_decorators.py
# tests/tool_processor/registry/test_decorators.py
import pytest
from functools import wraps

import chuk_tool_processor.registry.decorators as deco_mod
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.registry.provider import ToolRegistryProvider


class DummyRegistry:
    def __init__(self):
        self.calls = []

    def register_tool(self, tool, name=None, namespace="default", metadata=None):
        # capture exactly what was passed in
        self.calls.append({
            "tool": tool,
            "name": name,
            "namespace": namespace,
            "metadata": metadata,
        })


@pytest.fixture(autouse=True)
def use_dummy_registry(monkeypatch):
    dummy = DummyRegistry()
    # Monkey-patch the provider to return our dummy registry
    monkeypatch.setattr(ToolRegistryProvider, "get_registry", classmethod(lambda cls: dummy))
    return dummy


def test_decorator_registers_with_explicit_name_and_namespace(use_dummy_registry):
    @register_tool(name="custom_tool", namespace="math", description="adds numbers")
    class Adder:
        """Adds two numbers."""
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def execute(self):
            return self.x + self.y

    # After decoration, register_tool should have been called exactly once
    assert len(use_dummy_registry.calls) == 1
    call = use_dummy_registry.calls[0]
    # The decorator should register the original class
    original = Adder.__wrapped__
    assert call["tool"] is original
    assert call["name"] == "custom_tool"
    assert call["namespace"] == "math"
    assert call["metadata"] == {"description": "adds numbers"}

    # The decorator returns a wrapper function
    assert callable(Adder)
    inst = Adder(2, 3)
    # wrapper should produce an instance of the original class
    assert isinstance(inst, original)
    assert inst.execute() == 5

    # @wraps should preserve metadata
    assert Adder.__name__ == "Adder"
    assert Adder.__doc__ == "Adds two numbers."


def test_decorator_defaults_name_and_empty_metadata(use_dummy_registry):
    @register_tool()
    class NoMeta:
        def execute(self):
            return "ok"

    # register_tool called once
    assert len(use_dummy_registry.calls) == 1
    call = use_dummy_registry.calls[0]
    assert call["name"] is None
    assert call["namespace"] == "default"
    assert call["metadata"] == {}

    # wrapper still returns correct instance
    obj = NoMeta()
    assert hasattr(obj, "execute")
    assert obj.execute() == "ok"


def test_multiple_metadata_fields_and_order(use_dummy_registry):
    @register_tool(version="2.0", requires_auth=True, tags=["a", "b"])
    class MultiMeta:
        def execute(self):
            return True

    call = use_dummy_registry.calls[-1]
    original = MultiMeta.__wrapped__
    assert call["tool"] is original
    assert call["name"] is None
    assert call["namespace"] == "default"
    assert call["metadata"] == {
        "version": "2.0",
        "requires_auth": True,
        "tags": ["a", "b"],
    }
