# chuk_tool_processor/registry/providers/__init__.py
"""
Async registry provider implementations and factory functions.
"""

import os
import asyncio
from typing import Optional, Dict, Any

from chuk_tool_processor.registry.interface import ToolRegistryInterface

# Cache for initialized registries
_REGISTRY_CACHE: Dict[str, ToolRegistryInterface] = {}
_REGISTRY_LOCKS: Dict[str, asyncio.Lock] = {}


async def get_registry(
    provider_type: Optional[str] = None, 
    **kwargs
) -> ToolRegistryInterface:
    """
    Factory function to get a registry implementation asynchronously.
    
    This function caches registry instances by provider_type to avoid
    creating multiple instances unnecessarily. The cache is protected
    by locks to ensure thread safety.
    
    Args:
        provider_type: Type of registry provider to use. Options:
            - "memory" (default): In-memory implementation
            - "redis": Redis-backed implementation (if available)
            - "sqlalchemy": Database-backed implementation (if available)
        **kwargs: Additional configuration for the provider.
    
    Returns:
        A registry implementation.
    
    Raises:
        ImportError: If the requested provider is not available.
        ValueError: If the provider type is not recognized.
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
        if provider_type == "memory":
            # Import here to avoid circular imports
            from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
            registry = InMemoryToolRegistry()
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