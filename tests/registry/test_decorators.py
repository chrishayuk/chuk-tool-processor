# tests/tool_processor/registry/test_decorators.py
import pytest
import asyncio
import inspect
from functools import wraps

from chuk_tool_processor.registry.decorators import register_tool, ensure_registrations, discover_decorated_tools
from chuk_tool_processor.registry.provider import ToolRegistryProvider


class DummyRegistry:
    def __init__(self):
        self.calls = []

    async def register_tool(self, tool, name=None, namespace="default", metadata=None):
        # Capture exactly what was passed in
        self.calls.append({
            "tool": tool,
            "name": name,
            "namespace": namespace,
            "metadata": metadata,
        })
        
    async def get_tool(self, name, namespace="default"):
        # Simple implementation for testing
        return None
        
    async def list_tools(self, namespace=None):
        return []


@pytest.fixture
def use_dummy_registry(monkeypatch):
    dummy = DummyRegistry()
    
    # Create a future that returns our dummy registry
    future = asyncio.Future()
    future.set_result(dummy)
    
    # Monkey-patch the provider to return our future
    monkeypatch.setattr(
        ToolRegistryProvider, 
        "get_registry", 
        staticmethod(lambda: future)
    )
    
    return dummy


@pytest.mark.asyncio
async def test_decorator_registers_with_explicit_name_and_namespace(use_dummy_registry):
    @register_tool(name="custom_tool", namespace="math", description="adds numbers")
    class Adder:
        """Adds two numbers."""
        def __init__(self, x, y):
            self.x = x
            self.y = y

        async def execute(self):
            return self.x + self.y
            
    # Verify the class has registration info attached
    assert hasattr(Adder, '_tool_registration_info')
    info = Adder._tool_registration_info
    assert info['name'] == "custom_tool"
    assert info['namespace'] == "math"
    assert info['metadata'] == {"description": "adds numbers"}
    
    # No actual registration happened yet, need to ensure registrations
    assert len(use_dummy_registry.calls) == 0
    
    # Run the ensure_registrations function
    await ensure_registrations()
    
    # Now registration should have occurred
    assert len(use_dummy_registry.calls) == 1
    call = use_dummy_registry.calls[0]
    
    # The decorator should register the original class
    assert call["tool"] is Adder
    assert call["name"] == "custom_tool"
    assert call["namespace"] == "math"
    assert call["metadata"] == {"description": "adds numbers"}

    # The decorator does not wrap the class anymore
    assert Adder.__name__ == "Adder"
    assert Adder.__doc__ == "Adds two numbers."
    
    # Ensure the execute method is still async
    assert inspect.iscoroutinefunction(Adder.execute)
    
    # Test instance creation and execution
    inst = Adder(2, 3)
    result = await inst.execute()
    assert result == 5


@pytest.mark.asyncio
async def test_decorator_requires_async_execute():
    with pytest.raises(TypeError, match="must have an async execute method"):
        @register_tool()
        class NonAsyncTool:
            def execute(self):  # Not async!
                return "not async"


@pytest.mark.asyncio
async def test_decorator_defaults_name_and_empty_metadata(use_dummy_registry):
    @register_tool()
    class NoMeta:
        async def execute(self):
            return "ok"
            
    # Run registrations
    await ensure_registrations()

    # register_tool called once
    assert len(use_dummy_registry.calls) == 1
    call = use_dummy_registry.calls[0]
    assert call["name"] is None  # Default to class name
    assert call["namespace"] == "default"
    assert call["metadata"] == {}

    # Class is not wrapped
    assert NoMeta.__name__ == "NoMeta"
    obj = NoMeta()
    assert hasattr(obj, "execute")
    assert inspect.iscoroutinefunction(obj.execute)
    result = await obj.execute()
    assert result == "ok"