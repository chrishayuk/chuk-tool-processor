# chuk_tool_processor/registry/providers/__init__.py
"""
Async registry provider implementations and factory functions.
"""

import asyncio
import os
from typing import Any

from chuk_tool_processor.registry.interface import ToolRegistryInterface

# Cache for initialized registries
_REGISTRY_CACHE: dict[str, ToolRegistryInterface] = {}
_REGISTRY_LOCKS: dict[str, asyncio.Lock] = {}


async def get_registry(provider_type: str | None = None, **kwargs: Any) -> ToolRegistryInterface:
    """
    Factory function to get a registry implementation asynchronously.

    This function caches registry instances by provider_type to avoid
    creating multiple instances unnecessarily. The cache is protected
    by locks to ensure thread safety.

    Args:
        provider_type: Type of registry provider to use. Options:
            - "memory" (default): In-memory implementation
            - "redis": Redis-backed implementation (requires redis package)
        **kwargs: Additional configuration for the provider.
            For "redis":
                - redis_url: Redis connection URL (default: redis://localhost:6379/0)
                - key_prefix: Prefix for Redis keys (default: "chuk")
                - local_cache_ttl: Local cache TTL in seconds (default: 60.0)

    Returns:
        A registry implementation.

    Raises:
        ImportError: If the requested provider is not available.
        ValueError: If the provider type is not recognized.

    Example:
        >>> # Memory provider (default)
        >>> registry = await get_registry()
        >>>
        >>> # Redis provider
        >>> registry = await get_registry("redis", redis_url="redis://localhost:6379/0")
    """
    # Use environment variable if not specified
    if provider_type is None:
        provider_type = os.environ.get("CHUK_TOOL_REGISTRY_PROVIDER", "memory")

    # Check cache first
    cache_key = f"{provider_type}:{hash(frozenset(kwargs.items()))}"
    if cache_key in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[cache_key]

    # Create lock if needed
    if cache_key not in _REGISTRY_LOCKS:
        _REGISTRY_LOCKS[cache_key] = asyncio.Lock()

    # Acquire lock to ensure only one registry is created
    async with _REGISTRY_LOCKS[cache_key]:
        # Double-check pattern: check cache again after acquiring lock
        if cache_key in _REGISTRY_CACHE:
            return _REGISTRY_CACHE[cache_key]

        # Create the appropriate provider
        registry: ToolRegistryInterface
        if provider_type == "memory":
            from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry

            registry = InMemoryToolRegistry()
        elif provider_type == "redis":
            from chuk_tool_processor.registry.providers.redis import create_redis_registry

            redis_url = kwargs.get("redis_url", "redis://localhost:6379/0")
            key_prefix = kwargs.get("key_prefix", "chuk")
            local_cache_ttl = kwargs.get("local_cache_ttl", 60.0)
            registry = await create_redis_registry(
                redis_url=redis_url,
                key_prefix=key_prefix,
                local_cache_ttl=local_cache_ttl,
            )
        else:
            raise ValueError(f"Unknown registry provider type: {provider_type}")

        # Cache the registry
        _REGISTRY_CACHE[cache_key] = registry
        return registry


async def clear_registry_cache() -> None:
    """
    Clear the registry cache.

    This is useful in tests or when configuration changes.
    """
    _REGISTRY_CACHE.clear()
