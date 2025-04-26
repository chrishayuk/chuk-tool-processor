"""
Tool registry package for managing and accessing tool implementations.
"""

from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.registry.decorators import register_tool

# --------------------------------------------------------------------------- #
# Expose the *singleton* registry that every part of the library should use
# --------------------------------------------------------------------------- #
default_registry = ToolRegistryProvider.get_registry()

__all__ = [
    "ToolRegistryInterface",
    "ToolMetadata",
    "ToolRegistryProvider",
    "register_tool",
    "default_registry",
]
