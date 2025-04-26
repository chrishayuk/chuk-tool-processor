# chuk_tool_processor/registry/decorators.py
"""
Decorators for registering tools with the registry.
"""

from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from chuk_tool_processor.registry.provider import ToolRegistryProvider

T = TypeVar('T')


def register_tool(name: Optional[str] = None, namespace: str = "default", **metadata):
    """
    Decorator for registering tools with the global registry.
    
    Example:
        @register_tool(name="my_tool", namespace="math", description="Performs math operations")
        class MyTool:
            def execute(self, x: int, y: int) -> int:
                return x + y
    
    Args:
        name: Optional explicit name; if omitted, uses class.__name__.
        namespace: Namespace for the tool (default: "default").
        **metadata: Additional metadata for the tool.
    
    Returns:
        A decorator function that registers the class with the registry.
    """
    def decorator(cls: Type[T]) -> Type[T]:
        registry = ToolRegistryProvider.get_registry()
        registry.register_tool(cls, name=name, namespace=namespace, metadata=metadata)
        
        @wraps(cls)
        def wrapper(*args: Any, **kwargs: Dict[str, Any]) -> T:
            return cls(*args, **kwargs)
        
        return wrapper
    
    return decorator