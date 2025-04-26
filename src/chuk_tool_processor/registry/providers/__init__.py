"""
Registry provider implementations and factory functions.
"""

import os
from typing import Optional

from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry


def get_registry(
    provider_type: Optional[str] = None, 
    **kwargs
) -> ToolRegistryInterface:
    """
    Factory function to get a registry implementation.
    
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
    
    # Create the appropriate provider
    if provider_type == "memory":
        return InMemoryToolRegistry()
    else:
        raise ValueError(f"Unknown registry provider type: {provider_type}")