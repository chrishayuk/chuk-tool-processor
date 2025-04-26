# chuk_tool_processor/registry/provider.py
"""
Registry provider that maintains a global tool registry.
"""
from typing import Optional

# imports
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.providers import get_registry


class ToolRegistryProvider:
    """
    Global provider for a ToolRegistryInterface implementation.
    Use `set_registry` to override (e.g., for testing).
    
    This class provides a singleton-like access to a registry implementation,
    allowing components throughout the application to access the same registry
    without having to pass it explicitly.
    """
    # Initialize with default registry
    _registry: Optional[ToolRegistryInterface] = None

    @classmethod
    def get_registry(cls) -> ToolRegistryInterface:
        """
        Get the current registry instance.
        
        Returns:
            The current registry instance.
        """
        if cls._registry is None:
            cls._registry = get_registry()
        return cls._registry

    @classmethod
    def set_registry(cls, registry: ToolRegistryInterface) -> None:
        """
        Set the global registry instance.
        
        Args:
            registry: The registry instance to use.
        """
        cls._registry = registry