# tests/registry/test_decorators.py
"""
FIXED: Tests for the @register_tool decorator with proper test isolation.
"""
import pytest
import asyncio
import inspect
from functools import wraps

from chuk_tool_processor.registry.decorators import register_tool, ensure_registrations, discover_decorated_tools
from chuk_tool_processor.registry.provider import ToolRegistryProvider


class DummyRegistry:
    """Mock registry for testing decorator behavior."""
    
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
    """FIXED: Fixture with proper test isolation."""
    # Clear global state before each test
    from chuk_tool_processor.registry.decorators import _PENDING_REGISTRATIONS, _REGISTERED_CLASSES
    _PENDING_REGISTRATIONS.clear()
    _REGISTERED_CLASSES.clear()
    
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
    
    yield dummy
    
    # Clean up after test
    _PENDING_REGISTRATIONS.clear()
    _REGISTERED_CLASSES.clear()


@pytest.mark.asyncio
async def test_decorator_registers_with_explicit_name_and_namespace(use_dummy_registry):
    """Test decorator with explicit name, namespace, and metadata."""
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
    """Test that decorator requires async execute method."""
    with pytest.raises(TypeError, match="must have an async execute method"):
        @register_tool()
        class NonAsyncTool:
            def execute(self):  # Not async!
                return "not async"


@pytest.mark.asyncio
async def test_decorator_defaults_name_and_empty_metadata(use_dummy_registry):
    """FIXED: Test decorator with default name and empty metadata."""
    @register_tool()
    class NoMeta:
        async def execute(self):
            return "ok"
            
    # Run registrations
    await ensure_registrations()

    # register_tool called once
    assert len(use_dummy_registry.calls) == 1
    call = use_dummy_registry.calls[0]
    
    # FIXED: Decorator now uses class name when no explicit name provided
    assert call["name"] == "NoMeta"  # Changed from None to "NoMeta"
    assert call["namespace"] == "default"
    assert call["metadata"] == {}

    # Class is not wrapped
    assert NoMeta.__name__ == "NoMeta"
    obj = NoMeta()
    assert hasattr(obj, "execute")
    assert inspect.iscoroutinefunction(obj.execute)
    result = await obj.execute()
    assert result == "ok"


@pytest.mark.asyncio
async def test_decorator_with_namespace_only(use_dummy_registry):
    """Test decorator with only namespace specified."""
    @register_tool(namespace="custom")
    class NamespaceOnly:
        async def execute(self):
            return "namespace_test"
            
    await ensure_registrations()
    
    call = use_dummy_registry.calls[0]
    assert call["name"] == "NamespaceOnly"  # Uses class name
    assert call["namespace"] == "custom"
    assert call["metadata"] == {}


@pytest.mark.asyncio
async def test_decorator_with_metadata_only(use_dummy_registry):
    """Test decorator with only metadata specified."""
    @register_tool(description="test tool", version="1.0")
    class MetadataOnly:
        async def execute(self):
            return "metadata_test"
            
    await ensure_registrations()
    
    call = use_dummy_registry.calls[0]
    assert call["name"] == "MetadataOnly"
    assert call["namespace"] == "default"
    assert call["metadata"] == {"description": "test tool", "version": "1.0"}


@pytest.mark.asyncio
async def test_multiple_tools_registration(use_dummy_registry):
    """Test registering multiple tools."""
    @register_tool(name="tool1")
    class Tool1:
        async def execute(self):
            return "tool1"
    
    @register_tool(name="tool2", namespace="custom")
    class Tool2:
        async def execute(self):
            return "tool2"
    
    @register_tool(description="tool3 desc")
    class Tool3:
        async def execute(self):
            return "tool3"
    
    await ensure_registrations()
    
    # Should have 3 registrations
    assert len(use_dummy_registry.calls) == 3
    
    # Check each registration
    calls_by_name = {call["name"]: call for call in use_dummy_registry.calls}
    
    assert "tool1" in calls_by_name
    assert calls_by_name["tool1"]["namespace"] == "default"
    assert calls_by_name["tool1"]["metadata"] == {}
    
    assert "tool2" in calls_by_name
    assert calls_by_name["tool2"]["namespace"] == "custom"
    
    assert "Tool3" in calls_by_name
    assert calls_by_name["Tool3"]["metadata"] == {"description": "tool3 desc"}


@pytest.mark.asyncio
async def test_tool_with_init_params(use_dummy_registry):
    """Test tool that requires initialization parameters."""
    @register_tool(name="param_tool")
    class ParameterizedTool:
        def __init__(self, multiplier=2):
            self.multiplier = multiplier
        
        async def execute(self, value):
            return value * self.multiplier
    
    await ensure_registrations()
    
    # Should register successfully
    assert len(use_dummy_registry.calls) == 1
    
    # Test the actual tool functionality
    tool = ParameterizedTool(3)
    result = await tool.execute(5)
    assert result == 15


@pytest.mark.asyncio
async def test_discover_decorated_tools():
    """Test discovery of decorated tools."""
    @register_tool(name="discoverable")
    class DiscoverableTool:
        async def execute(self):
            return "discovered"
    
    # Note: discover_decorated_tools may not find tools in test modules
    # This test mainly checks that the function doesn't crash
    tools = discover_decorated_tools()
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_ensure_registrations_multiple_calls(use_dummy_registry):
    """FIXED: Test that calling ensure_registrations multiple times doesn't duplicate."""
    @register_tool(name="once_only")
    class OnceOnlyTool:
        async def execute(self):
            return "once"
    
    # Call ensure_registrations multiple times
    await ensure_registrations()
    await ensure_registrations()
    await ensure_registrations()
    
    # FIXED: Should only have one registration (with proper test isolation)
    assert len(use_dummy_registry.calls) == 1
    assert use_dummy_registry.calls[0]["name"] == "once_only"


@pytest.mark.asyncio
async def test_decorator_serialization_support(use_dummy_registry):
    """Test that decorated tools have serialization support added."""
    @register_tool(name="serializable")
    class SerializableTool:
        def __init__(self, value=42):
            self.value = value
        
        async def execute(self):
            return self.value
    
    await ensure_registrations()
    
    # Test that the class has serialization methods
    tool = SerializableTool(100)
    
    # Should have __getstate__ and __setstate__ methods
    assert hasattr(tool, '__getstate__')
    assert hasattr(tool, '__setstate__')
    assert callable(tool.__getstate__)
    assert callable(tool.__setstate__)
    
    # Test serialization
    state = tool.__getstate__()
    assert isinstance(state, dict)
    assert 'tool_name' in state
    assert state['tool_name'] == 'serializable'
    
    # Test deserialization
    new_tool = SerializableTool()
    new_tool.__setstate__(state)
    assert hasattr(new_tool, 'tool_name')
    result = await new_tool.execute()
    assert result == 100


@pytest.mark.asyncio
async def test_decorator_tool_name_attribute(use_dummy_registry):
    """Test that decorated tools have tool_name attribute."""
    @register_tool(name="named_tool")
    class NamedTool:
        async def execute(self):
            return "named"
    
    await ensure_registrations()
    
    # Create instance and check tool_name
    tool = NamedTool()
    assert hasattr(tool, 'tool_name')
    assert tool.tool_name == 'named_tool'


@pytest.mark.asyncio
async def test_class_already_registered_skip(use_dummy_registry):
    """Test that already registered classes are skipped."""
    @register_tool(name="skip_test")
    class SkipTest:
        async def execute(self):
            return "skip"
    
    # Apply decorator again (simulating import/reload)
    register_tool(name="skip_test_2")(SkipTest)
    
    await ensure_registrations()
    
    # Should only register once (the first time)
    registrations = [call for call in use_dummy_registry.calls if call["tool"] is SkipTest]
    assert len(registrations) == 1
    assert registrations[0]["name"] == "skip_test"


@pytest.mark.asyncio
async def test_isolated_registrations(use_dummy_registry):
    """Test that registrations are properly isolated between tests."""
    @register_tool(name="isolated_test")
    class IsolatedTool:
        async def execute(self):
            return "isolated"
    
    await ensure_registrations()
    
    # Should only have this test's registration
    assert len(use_dummy_registry.calls) == 1
    assert use_dummy_registry.calls[0]["name"] == "isolated_test"


@pytest.mark.asyncio
async def test_tool_name_property_access(use_dummy_registry):
    """Test that tool_name can be accessed as property."""
    @register_tool(name="property_test")
    class PropertyTool:
        async def execute(self):
            return "property"
    
    await ensure_registrations()
    
    tool = PropertyTool()
    
    # Test both attribute and property access
    assert hasattr(tool, 'tool_name')
    assert tool.tool_name == 'property_test'
    
    # Test that it's preserved during serialization
    state = tool.__getstate__()
    assert state['tool_name'] == 'property_test'


@pytest.mark.asyncio  
async def test_empty_metadata_handling(use_dummy_registry):
    """Test handling of empty metadata."""
    @register_tool(name="empty_meta")
    class EmptyMetaTool:
        async def execute(self):
            return "empty"
    
    await ensure_registrations()
    
    call = use_dummy_registry.calls[0]
    assert call["name"] == "empty_meta"
    assert call["metadata"] == {}
    assert isinstance(call["metadata"], dict)


@pytest.mark.asyncio
async def test_complex_metadata_handling(use_dummy_registry):
    """Test handling of complex metadata."""
    @register_tool(
        name="complex_meta",
        description="Complex tool",
        version="2.0",
        tags=["test", "complex"],
        config={"max_retries": 3, "timeout": 30}
    )
    class ComplexMetaTool:
        async def execute(self):
            return "complex"
    
    await ensure_registrations()
    
    call = use_dummy_registry.calls[0]
    assert call["name"] == "complex_meta"
    assert call["metadata"]["description"] == "Complex tool"
    assert call["metadata"]["version"] == "2.0"
    assert call["metadata"]["tags"] == ["test", "complex"]
    assert call["metadata"]["config"]["max_retries"] == 3


@pytest.mark.asyncio
async def test_tool_inheritance(use_dummy_registry):
    """Test that tool inheritance works with decorator."""
    class BaseTool:
        def __init__(self, base_value=10):
            self.base_value = base_value
    
    @register_tool(name="inherited_tool")
    class InheritedTool(BaseTool):
        async def execute(self, multiplier=2):
            return self.base_value * multiplier
    
    await ensure_registrations()
    
    # Should register successfully
    assert len(use_dummy_registry.calls) == 1
    
    # Test functionality
    tool = InheritedTool(5)
    result = await tool.execute(3)
    assert result == 15
    
    # Test tool_name is preserved
    assert tool.tool_name == 'inherited_tool'