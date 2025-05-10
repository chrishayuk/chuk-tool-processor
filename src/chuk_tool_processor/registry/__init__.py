# chuk_tool_processor/registry/__init__.py
"""
Async-native tool registry package for managing and accessing tool implementations.
"""

import asyncio
from typing import Optional

from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata, StreamingToolMetadata
from chuk_tool_processor.registry.provider import ToolRegistryProvider, get_registry
from chuk_tool_processor.registry.decorators import register_tool, ensure_registrations, discover_decorated_tools

# --------------------------------------------------------------------------- #
# The default_registry is now an async function instead of direct property access
# --------------------------------------------------------------------------- #
async def get_default_registry() -> ToolRegistryInterface:
    """
    Get the default registry instance.
    
    This is a convenience function that calls ToolRegistryProvider.get_registry()
    
    Returns:
        The default tool registry
    """
    return await ToolRegistryProvider.get_registry()

__all__ = [
    "ToolRegistryInterface",
    "ToolMetadata",
    "StreamingToolMetadata",
    "ToolRegistryProvider",
    "register_tool",
    "ensure_registrations",
    "discover_decorated_tools",
    "get_default_registry",
    "get_registry",
]

# --------------------------------------------------------------------------- #
# Initialization helper that should be called at application startup
# --------------------------------------------------------------------------- #
async def initialize():
    """
    Initialize the registry system.
    
    This function should be called during application startup to:
    1. Ensure the registry is created
    2. Register all tools decorated with @register_tool
    
    Returns:
        The initialized registry
    """
    # Initialize registry
    registry = await get_default_registry()
    
    # Process all pending tool registrations
    await ensure_registrations()
    
    return registry