"""
Tool registry package for managing and accessing tool implementations.
"""
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.registry.provider import get_registry

# Create and expose the default registry
default_registry = get_registry()

__all__ = [
    'ToolRegistryInterface',
    'ToolMetadata',
    'ToolRegistryProvider',
    'register_tool',
    'default_registry',
    'get_registry',
]