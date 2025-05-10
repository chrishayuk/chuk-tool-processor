# tests/tool_processor/registry/test_interface.py
import inspect
import pytest
from typing import Protocol, runtime_checkable

from chuk_tool_processor.registry.interface import ToolRegistryInterface


@pytest.mark.parametrize(
    "method_name, expected_args, expected_defaults",
    [
        (
            "register_tool",
            ["tool", "name", "namespace", "metadata"],
            {"name": None, "namespace": "default", "metadata": None},
        ),
        ("get_tool", ["name", "namespace"], {"namespace": "default"}),
        ("get_tool_strict", ["name", "namespace"], {"namespace": "default"}),
        ("get_metadata", ["name", "namespace"], {"namespace": "default"}),
        ("list_tools", ["namespace"], {"namespace": None}),
        ("list_namespaces", [], {}),
        ("list_metadata", ["namespace"], {"namespace": None}),
    ],
)
@pytest.mark.asyncio
async def test_method_signature(method_name, expected_args, expected_defaults):
    # Method must exist
    method = getattr(ToolRegistryInterface, method_name, None)
    assert method is not None, f"{method_name} is not defined"

    sig = inspect.signature(method)
    # Skip the implicit 'self'
    params = list(sig.parameters.items())[1:]
    # Check parameter names
    names = [n for n, _ in params]
    assert names == expected_args, (
        f"{method_name} parameters {names} != expected {expected_args}"
    )
    # Each parameter needs a type annotation
    for name, param in params:
        assert param.annotation is not inspect._empty, (
            f"{method_name}.{name} needs a type annotation"
        )
    # Check default values for optional parameters
    for arg, default in expected_defaults.items():
        assert sig.parameters[arg].default == default, (
            f"{method_name}.{arg} default {sig.parameters[arg].default} != {default}"
        )


@pytest.mark.asyncio
async def test_methods_are_async():
    """Verify that all methods are declared with async def."""
    for name in ["register_tool", "get_tool", "get_tool_strict", "get_metadata", 
                "list_tools", "list_namespaces", "list_metadata"]:
        method = getattr(ToolRegistryInterface, name)
        assert inspect.iscoroutinefunction(method), f"{name} should be async"


@pytest.mark.asyncio
async def test_docstrings_describe_return():
    # Check methods that actually return something
    for name in ("get_tool", "get_tool_strict", "get_metadata", "list_tools", 
                "list_namespaces", "list_metadata"):
        method = getattr(ToolRegistryInterface, name)
        doc = inspect.getdoc(method) or ""
        assert (
            "Returns" in doc or "return" in doc.lower()
        ), f"{name} should document its return value"


@pytest.mark.asyncio
async def test_runtime_checkable():
    """Test that the Protocol is runtime-checkable."""
    from typing import runtime_checkable
    import sys
    
    # Define a conforming class
    class ConformingRegistry:
        async def register_tool(self, tool, name=None, namespace="default", metadata=None):
            pass
            
        async def get_tool(self, name, namespace="default"):
            return None
            
        async def get_tool_strict(self, name, namespace="default"):
            return None
            
        async def get_metadata(self, name, namespace="default"):
            return None
            
        async def list_tools(self, namespace=None):
            return []
            
        async def list_namespaces(self):
            return []
            
        async def list_metadata(self, namespace=None):
            return []
    
    # Create an instance to test with isinstance
    conforming_instance = ConformingRegistry()
    
    # Directly test with isinstance (should work if runtime_checkable)
    try:
        is_instance = isinstance(conforming_instance, ToolRegistryInterface)
        # If we got here without exception, the Protocol must be runtime_checkable
        assert is_instance, "ConformingRegistry should be an instance of ToolRegistryInterface"
    except TypeError:
        # If we get a TypeError, the Protocol is not runtime_checkable
        pytest.fail("ToolRegistryInterface is not runtime_checkable")
        
    # For backward compatibility, also check for the marker attributes
    # Python 3.8+: __runtime_checkable__
    # Earlier Python: _is_protocol and _is_runtime_checkable
    assert any([
        hasattr(ToolRegistryInterface, "__runtime_checkable__"),
        hasattr(ToolRegistryInterface, "_is_runtime_checkable") and getattr(ToolRegistryInterface, "_is_runtime_checkable"),
        hasattr(ToolRegistryInterface, "_is_protocol") and getattr(ToolRegistryInterface, "_is_protocol")
    ]), "ToolRegistryInterface should be marked with @runtime_checkable"