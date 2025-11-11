# chuk_tool_processor/registry/__init__.py
"""
Async-native tool registry package for managing and accessing tool implementations.
"""

import asyncio

from chuk_tool_processor.registry.decorators import discover_decorated_tools, ensure_registrations, register_tool, tool
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import StreamingToolMetadata, ToolInfo, ToolMetadata
from chuk_tool_processor.registry.provider import ToolRegistryProvider, get_registry

# Track whether initialization has occurred
_INITIALIZED = False
_INIT_LOCK = asyncio.Lock()


# --------------------------------------------------------------------------- #
# The default_registry is now an async function instead of direct property access
# --------------------------------------------------------------------------- #
async def get_default_registry(auto_initialize: bool = True) -> ToolRegistryInterface:
    """
    Get the default registry instance with optional auto-initialization.

    This function automatically ensures the registry is initialized with all
    @register_tool decorated classes unless auto_initialize=False.

    Args:
        auto_initialize: If True (default), automatically call ensure_registrations()
                        if it hasn't been called yet. Set to False to skip initialization.

    Returns:
        The default tool registry

    Example:
        >>> # Auto-initialization (recommended for most use cases)
        >>> registry = await get_default_registry()
        >>> # All @register_tool decorated tools are now available
        >>>
        >>> # Manual control (for advanced use cases)
        >>> registry = await get_default_registry(auto_initialize=False)
        >>> # You must call initialize() yourself
    """
    global _INITIALIZED

    # Get the registry first
    registry = await ToolRegistryProvider.get_registry()

    # Auto-initialize if requested and not already done
    if auto_initialize and not _INITIALIZED:
        async with _INIT_LOCK:
            # Double-check after acquiring lock
            if not _INITIALIZED:
                await ensure_registrations()
                _INITIALIZED = True

    return registry


__all__ = [
    "ToolRegistryInterface",
    "ToolInfo",
    "ToolMetadata",
    "StreamingToolMetadata",
    "ToolRegistryProvider",
    "register_tool",
    "tool",
    "ensure_registrations",
    "discover_decorated_tools",
    "get_default_registry",
    "get_registry",
]


# --------------------------------------------------------------------------- #
# Initialization helper that should be called at application startup
# --------------------------------------------------------------------------- #
async def initialize() -> ToolRegistryInterface:
    """
    Initialize the registry system.

    This function explicitly initializes the registry and processes all
    @register_tool decorated classes. It's now optional since get_default_registry()
    auto-initializes by default.

    NOTE: You can now skip calling initialize() and just use get_default_registry()
    directly, which will auto-initialize on first access.

    Returns:
        The initialized registry

    Example:
        >>> # Old pattern (still works)
        >>> await initialize()
        >>> registry = await get_default_registry()
        >>>
        >>> # New pattern (simpler)
        >>> registry = await get_default_registry()  # Auto-initializes!
    """
    global _INITIALIZED

    # Get registry (without auto-init to avoid redundant work)
    registry = await get_default_registry(auto_initialize=False)

    # Always process registrations when explicitly called
    async with _INIT_LOCK:
        await ensure_registrations()
        _INITIALIZED = True

    return registry
