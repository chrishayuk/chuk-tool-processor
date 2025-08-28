#!/usr/bin/env python
"""
Decorator that handles Pydantic models (StreamingTool) properly.

The issue was that Pydantic models have strict field validation and reject
arbitrary attribute assignment. This fix detects Pydantic models and handles
them appropriately.
"""

import asyncio
import atexit
import functools
import inspect
import sys
import warnings
import weakref
from collections.abc import Awaitable, Callable
from typing import TypeVar

from chuk_tool_processor.registry.provider import ToolRegistryProvider

T = TypeVar("T")

# Global tracking of classes to be registered
_PENDING_REGISTRATIONS: list[Callable[[], Awaitable]] = []
_REGISTERED_CLASSES = weakref.WeakSet()
_SHUTTING_DOWN = False


def _is_pydantic_model(cls: type) -> bool:
    """Check if a class is a Pydantic model."""
    try:
        # Check for Pydantic v2
        return hasattr(cls, "model_fields") or hasattr(cls, "__pydantic_core_schema__")
    except Exception:
        try:
            # Check for Pydantic v1
            return hasattr(cls, "__fields__")
        except Exception:
            return False


def _add_subprocess_serialization_support(cls: type, tool_name: str) -> type:
    """
    Add subprocess serialization support to a tool class.

    FIXED: Now properly handles Pydantic models by using class attributes
    instead of instance attributes where necessary.
    """
    # Store the tool name for serialization at class level
    cls._tool_name = tool_name

    # Check if this is a Pydantic model
    is_pydantic = _is_pydantic_model(cls)

    # Check if the class already has custom serialization methods
    has_custom_getstate = "__getstate__" in cls.__dict__ and callable(cls.__dict__["__getstate__"])
    has_custom_setstate = "__setstate__" in cls.__dict__ and callable(cls.__dict__["__setstate__"])

    if has_custom_getstate and has_custom_setstate:
        # Class already has both custom serialization methods
        original_getstate = cls.__getstate__
        original_setstate = cls.__setstate__

        def enhanced_getstate(self):
            """Enhanced __getstate__ that ensures tool_name is included."""
            state = original_getstate(self)
            if isinstance(state, dict):
                state["tool_name"] = getattr(self, "tool_name", tool_name)
                return state
            else:
                return {"_custom_state": state, "tool_name": getattr(self, "tool_name", tool_name)}

        def enhanced_setstate(self, state):
            """Enhanced __setstate__ that handles tool_name."""
            if isinstance(state, dict) and "_custom_state" in state:
                # FIXED: For Pydantic models, set as class attribute
                if is_pydantic:
                    self.__class__._tool_name = state.get("tool_name", tool_name)
                else:
                    self.tool_name = state.get("tool_name", tool_name)
                original_setstate(self, state["_custom_state"])
            else:
                if isinstance(state, dict):
                    if is_pydantic:
                        self.__class__._tool_name = state.get("tool_name", tool_name)
                    else:
                        self.tool_name = state.get("tool_name", tool_name)
                original_setstate(self, state)

        cls.__getstate__ = enhanced_getstate
        cls.__setstate__ = enhanced_setstate

    elif not has_custom_getstate and not has_custom_setstate:
        # No custom serialization methods - add default implementation

        if is_pydantic:
            # FIXED: Special handling for Pydantic models
            def __getstate__(self):
                """Pydantic-compatible serialization method."""
                try:
                    # Try Pydantic v2 first
                    if hasattr(self, "model_dump"):
                        state = self.model_dump()
                    elif hasattr(self, "dict"):
                        # Pydantic v1
                        state = self.dict()
                    else:
                        # Fallback to __dict__
                        state = self.__dict__.copy()
                except Exception:
                    # Fallback to __dict__
                    state = self.__dict__.copy()

                # Always include tool_name
                state["tool_name"] = getattr(self, "tool_name", getattr(self.__class__, "_tool_name", tool_name))
                return state

            def __setstate__(self, state):
                """Pydantic-compatible deserialization method."""
                if isinstance(state, dict):
                    # Extract tool_name and store at class level for Pydantic
                    tool_name_value = state.get("tool_name", tool_name)
                    self.__class__._tool_name = tool_name_value

                    # For Pydantic models, we need to be careful about restoration
                    try:
                        # Remove tool_name from state since it's not a Pydantic field
                        state_copy = state.copy()
                        state_copy.pop("tool_name", None)

                        # Update the object's fields
                        if hasattr(self, "__dict__"):
                            self.__dict__.update(state_copy)
                    except Exception:
                        # Fallback - just update __dict__
                        if hasattr(self, "__dict__"):
                            self.__dict__.update(state)
                else:
                    # Non-dict state
                    self.__class__._tool_name = tool_name

        else:
            # Regular class handling (same as before)
            def __getstate__(self):
                """Default serialization method for subprocess execution."""
                state = self.__dict__.copy()
                state["tool_name"] = getattr(self, "tool_name", tool_name)

                # Remove non-serializable attributes
                non_serializable_attrs = []
                for key, value in list(state.items()):
                    if key == "tool_name":
                        continue
                    try:
                        import pickle

                        pickle.dumps(value)
                    except (TypeError, AttributeError, pickle.PicklingError):
                        non_serializable_attrs.append(key)

                for key in non_serializable_attrs:
                    if key in state:
                        del state[key]

                return state

            def __setstate__(self, state):
                """Default deserialization method for subprocess execution."""
                if isinstance(state, dict):
                    self.__dict__.update(state)
                    if not hasattr(self, "tool_name") or not self.tool_name:
                        self.tool_name = state.get("tool_name", tool_name)
                else:
                    self.tool_name = tool_name

        cls.__getstate__ = __getstate__
        cls.__setstate__ = __setstate__

    # FIXED: Enhanced __init__ wrapper that handles Pydantic models
    if hasattr(cls, "__init__"):
        original_init = cls.__init__

        @functools.wraps(original_init)
        def enhanced_init(self, *args, **kwargs):
            # Call original __init__
            original_init(self, *args, **kwargs)

            # FIXED: Handle tool_name setting based on model type
            if is_pydantic:
                # For Pydantic models, store at class level and add property
                self.__class__._tool_name = tool_name

                # Add a property to access tool_name if it doesn't exist
                if not hasattr(self.__class__, "tool_name"):

                    def tool_name_property(self):
                        return getattr(self.__class__, "_tool_name", tool_name)

                    # Add as a property
                    self.__class__.tool_name = property(tool_name_property)
            else:
                # For regular classes, set as instance attribute
                if not hasattr(self, "tool_name"):
                    self.tool_name = tool_name

        cls.__init__ = enhanced_init
    else:
        # FIXED: Add appropriate __init__ based on model type
        if is_pydantic:

            def __init__(self, *args, **kwargs):
                super(cls, self).__init__(*args, **kwargs)
                self.__class__._tool_name = tool_name
        else:

            def __init__(self):
                self.tool_name = tool_name

        cls.__init__ = __init__

    # FIXED: Add tool_name property for Pydantic models
    if is_pydantic and not hasattr(cls, "tool_name"):

        def tool_name_property(self):
            return getattr(self.__class__, "_tool_name", tool_name)

        # Add as a property so it can be accessed but not set directly
        cls.tool_name = property(tool_name_property)

    return cls


def register_tool(name: str | None = None, namespace: str = "default", **metadata):
    """
    Decorator for registering tools with the global registry.

    FIXED: Now properly handles Pydantic models (like StreamingTool).

    This decorator automatically adds subprocess serialization support,
    making tools compatible with both InProcessStrategy and SubprocessStrategy.
    """

    def decorator(cls: type[T]) -> type[T]:
        # Skip if already registered
        if cls in _REGISTERED_CLASSES:
            return cls

        # Skip if shutting down
        if _SHUTTING_DOWN:
            return cls

        # Ensure execute method is async
        if hasattr(cls, "execute") and not inspect.iscoroutinefunction(cls.execute):
            raise TypeError(f"Tool {cls.__name__} must have an async execute method")

        # Determine the tool name
        tool_name = name or cls.__name__

        # FIXED: Add subprocess serialization support with Pydantic handling
        enhanced_cls = _add_subprocess_serialization_support(cls, tool_name)

        # Create registration function
        async def do_register():
            registry = await ToolRegistryProvider.get_registry()
            await registry.register_tool(enhanced_cls, name=tool_name, namespace=namespace, metadata=metadata)

        _PENDING_REGISTRATIONS.append(do_register)
        _REGISTERED_CLASSES.add(enhanced_cls)

        # Add class attribute for identification
        enhanced_cls._tool_registration_info = {"name": tool_name, "namespace": namespace, "metadata": metadata}

        return enhanced_cls

    return decorator


# Alternative approach: A helper function for Pydantic compatibility
def make_pydantic_tool_compatible(cls: type, tool_name: str) -> type:
    """
    Alternative helper function to make Pydantic tools subprocess-compatible.

    This can be used as a manual alternative if the decorator approach
    doesn't work for your specific use case.
    """
    # Store tool name at class level
    cls._tool_name = tool_name

    # Add property access
    if not hasattr(cls, "tool_name"):

        def tool_name_getter(self):
            return getattr(self.__class__, "_tool_name", tool_name)

        cls.tool_name = property(tool_name_getter)

    # Add serialization methods
    if not hasattr(cls, "__getstate__"):

        def __getstate__(self):
            try:
                if hasattr(self, "model_dump"):
                    state = self.model_dump()
                elif hasattr(self, "dict"):
                    state = self.dict()
                else:
                    state = self.__dict__.copy()
            except Exception:
                state = self.__dict__.copy()

            state["tool_name"] = getattr(self.__class__, "_tool_name", tool_name)
            return state

        cls.__getstate__ = __getstate__

    if not hasattr(cls, "__setstate__"):

        def __setstate__(self, state):
            if isinstance(state, dict):
                self.__class__._tool_name = state.get("tool_name", tool_name)
                state_copy = state.copy()
                state_copy.pop("tool_name", None)
                if hasattr(self, "__dict__"):
                    self.__dict__.update(state_copy)

        cls.__setstate__ = __setstate__

    return cls


async def ensure_registrations() -> None:
    """Process all pending tool registrations."""
    global _PENDING_REGISTRATIONS

    if not _PENDING_REGISTRATIONS:
        return

    tasks = []
    for registration_fn in _PENDING_REGISTRATIONS:
        tasks.append(asyncio.create_task(registration_fn()))

    _PENDING_REGISTRATIONS.clear()

    if tasks:
        await asyncio.gather(*tasks)


def discover_decorated_tools() -> list[type]:
    """Discover all tool classes decorated with @register_tool."""
    tools = []

    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("chuk_tool_processor"):
            continue

        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
                if hasattr(attr, "_tool_registration_info"):
                    tools.append(attr)
            except (AttributeError, ImportError):
                pass

    return tools


# Shutdown handling
def _handle_shutdown():
    """Handle shutdown by clearing pending registrations."""
    global _SHUTTING_DOWN, _PENDING_REGISTRATIONS
    _SHUTTING_DOWN = True
    _PENDING_REGISTRATIONS = []


atexit.register(_handle_shutdown)
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")
