# chuk_tool_processor/registry/decorators.py
"""
Decorators for registering tools with the registry asynchronously.
"""

import asyncio
import functools
import inspect
import sys
import weakref
import atexit
import warnings
from typing import Any, Callable, Dict, Optional, Type, TypeVar, cast, Set, List, Awaitable

from chuk_tool_processor.registry.provider import ToolRegistryProvider

T = TypeVar('T')

# Global tracking of classes to be registered
# Store coroutines rather than awaitables to avoid warnings
_PENDING_REGISTRATIONS: List[Callable[[], Awaitable]] = []
_REGISTERED_CLASSES = weakref.WeakSet()

# Keep track of whether we're shutting down
_SHUTTING_DOWN = False


def register_tool(name: Optional[str] = None, namespace: str = "default", **metadata):
    """
    Decorator for registering tools with the global registry.
    
    This decorator will queue the registration to happen asynchronously.
    You must call `await ensure_registrations()` in your application startup
    to complete all registrations.
    
    Example:
        @register_tool(name="my_tool", namespace="math", description="Performs math operations")
        class MyTool:
            async def execute(self, x: int, y: int) -> int:
                return x + y
    
    Args:
        name: Optional explicit name; if omitted, uses class.__name__.
        namespace: Namespace for the tool (default: "default").
        **metadata: Additional metadata for the tool.
    
    Returns:
        A decorator function that registers the class with the registry.
    """
    def decorator(cls: Type[T]) -> Type[T]:
        # Skip if already registered
        if cls in _REGISTERED_CLASSES:
            return cls
            
        # Skip if shutting down
        if _SHUTTING_DOWN:
            return cls

        # Ensure execute method is async
        if hasattr(cls, 'execute') and not inspect.iscoroutinefunction(cls.execute):
            raise TypeError(f"Tool {cls.__name__} must have an async execute method")
            
        # Create registration function (not coroutine)
        async def do_register():
            registry = await ToolRegistryProvider.get_registry()
            await registry.register_tool(
                cls, 
                name=name, 
                namespace=namespace, 
                metadata=metadata
            )
        
        # Store the function, not the coroutine
        _PENDING_REGISTRATIONS.append(do_register)
        _REGISTERED_CLASSES.add(cls)
        
        # Add class attribute so we can identify decorated classes
        cls._tool_registration_info = {
            'name': name or cls.__name__,
            'namespace': namespace,
            'metadata': metadata
        }
        
        # Don't modify the original class
        return cls
    
    return decorator


async def ensure_registrations() -> None:
    """
    Process all pending tool registrations.
    
    This must be called during application startup to register
    all tools decorated with @register_tool.
    
    Returns:
        None
    """
    global _PENDING_REGISTRATIONS
    
    if not _PENDING_REGISTRATIONS:
        return
        
    # Create tasks from the stored functions
    tasks = []
    for registration_fn in _PENDING_REGISTRATIONS:
        # Now we await the function to get the coroutine, then create a task
        tasks.append(asyncio.create_task(registration_fn()))
    
    # Clear the pending list
    _PENDING_REGISTRATIONS.clear()
    
    # Wait for all registrations to complete
    if tasks:
        await asyncio.gather(*tasks)


def discover_decorated_tools() -> List[Type]:
    """
    Discover all tool classes decorated with @register_tool.
    
    This can be used to inspect what tools have been registered
    without awaiting ensure_registrations().
    
    Returns:
        List of tool classes that have been decorated
    """
    tools = []
    
    # Search all loaded modules
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith('chuk_tool_processor'):
            continue
            
        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
                if hasattr(attr, '_tool_registration_info'):
                    tools.append(attr)
            except (AttributeError, ImportError):
                pass
                
    return tools


# Register atexit handler to prevent warnings at shutdown
def _handle_shutdown():
    """
    Handle shutdown by marking shutdown flag and clearing pending registrations.
    This prevents warnings about unawaited coroutines.
    """
    global _SHUTTING_DOWN, _PENDING_REGISTRATIONS
    
    # Set the shutdown flag
    _SHUTTING_DOWN = True
    
    # Clear without creating any coroutines
    _PENDING_REGISTRATIONS = []

# Register the shutdown handler
atexit.register(_handle_shutdown)

# Filter the coroutine never awaited warning
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")