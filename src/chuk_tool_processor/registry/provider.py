# chuk_tool_processor/registry/provider.py
"""
Global access to the async tool registry instance.

There are two public faces:

1.  **Module helpers**
    • `get_registry()` lazily instantiates a default `InMemoryToolRegistry`
      and memoises it in the module-level variable ``_REGISTRY``.
    • `set_registry()` lets callers replace or reset that singleton.

2.  **`ToolRegistryProvider` class**
    Provides static methods for async-safe access to the registry.

The contract verified by the test-suite is:

* The module-level factory is invoked **exactly once** per fresh cache.
* `await ToolRegistryProvider.set_registry(obj)` overrides subsequent retrievals.
* `await ToolRegistryProvider.set_registry(None)` resets the cache so the next
  `await get_registry()` call invokes (and honours any monkey-patched) factory.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable

# registry
from .interface import ToolRegistryInterface

# --------------------------------------------------------------------------- #
# Module-level singleton used by the helper functions
# --------------------------------------------------------------------------- #
_REGISTRY: ToolRegistryInterface | None = None
_REGISTRY_LOCK = asyncio.Lock()
# --------------------------------------------------------------------------- #


async def _default_registry() -> ToolRegistryInterface:
    """Create the default in-memory registry asynchronously."""
    # Import here to avoid circular import
    from .providers.memory import InMemoryToolRegistry

    return InMemoryToolRegistry()


async def get_registry() -> ToolRegistryInterface:
    """
    Return the process-wide registry asynchronously, creating it on first use.

    This function is thread-safe and will only create the registry once,
    even with concurrent calls.
    """
    global _REGISTRY
    if _REGISTRY is None:
        async with _REGISTRY_LOCK:
            # Double-check pattern: check again after acquiring the lock
            if _REGISTRY is None:
                _REGISTRY = await _default_registry()
    return _REGISTRY


async def set_registry(registry: ToolRegistryInterface | None) -> None:
    """
    Replace or clear the global registry asynchronously.

    Passing ``None`` resets the singleton so that the next `get_registry()`
    call recreates it (useful in tests).
    """
    global _REGISTRY
    async with _REGISTRY_LOCK:
        _REGISTRY = registry


# --------------------------------------------------------------------------- #
# Provider class for consistent access to the registry
# --------------------------------------------------------------------------- #
class ToolRegistryProvider:
    """Async static wrapper for registry access."""

    # Thread-safe singleton management
    _registry: ToolRegistryInterface | None = None
    _lock = asyncio.Lock()

    # ------------------------ public API ------------------------ #
    @staticmethod
    async def get_registry() -> ToolRegistryInterface:
        """
        Return the cached instance or initialize a new one asynchronously.

        This method ensures thread-safety when initializing the registry.
        """
        if ToolRegistryProvider._registry is None:
            async with ToolRegistryProvider._lock:
                # Check again after acquiring the lock
                if ToolRegistryProvider._registry is None:
                    # Dynamically import to get the latest definition
                    module = sys.modules[__name__]
                    get_registry_func: Callable[[], Awaitable[ToolRegistryInterface]] = module.get_registry
                    # Call it to get the registry
                    ToolRegistryProvider._registry = await get_registry_func()

        return ToolRegistryProvider._registry

    @staticmethod
    async def set_registry(registry: ToolRegistryInterface | None) -> None:
        """
        Override the cached registry asynchronously.

        *   If ``registry`` is an object, all subsequent `get_registry()`
            calls return it without touching the factory.
        *   If ``registry`` is ``None``, the cache is cleared so the next
            `get_registry()` call invokes the factory.
        """
        async with ToolRegistryProvider._lock:
            ToolRegistryProvider._registry = registry

    @staticmethod
    async def reset() -> None:
        """
        Reset both the module-level and class-level registry caches.

        This is primarily used in tests to ensure a clean state.
        """
        async with ToolRegistryProvider._lock:
            ToolRegistryProvider._registry = None
            await set_registry(None)

    @staticmethod
    async def get_global_registry() -> ToolRegistryInterface:
        """
        Get the module-level registry directly.

        This bypasses the class-level cache and always returns the module-level registry.
        """
        return await get_registry()
