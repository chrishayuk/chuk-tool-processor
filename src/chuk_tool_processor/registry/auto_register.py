# chuk_tool_processor/registry/auto_register.py
"""
Async auto-register helpers for registering functions and LangChain tools.

Usage:
    await register_fn_tool(my_function)
    await register_langchain_tool(my_langchain_tool)

These tools will immediately show up in the global registry.
"""

from __future__ import annotations

import asyncio
import inspect
import types
from typing import Callable, ForwardRef, Type, get_type_hints, Any, Optional, Dict, Union

import anyio
from pydantic import BaseModel, create_model

try:  # optional dependency
    from langchain.tools.base import BaseTool  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    BaseTool = None  # noqa: N816  – keep the name for isinstance() checks

# registry
from .decorators import register_tool
from .provider import ToolRegistryProvider


# ────────────────────────────────────────────────────────────────────────────
# internals – build a Pydantic schema from an arbitrary callable
# ────────────────────────────────────────────────────────────────────────────


def _auto_schema(func: Callable) -> Type[BaseModel]:
    """
    Turn a function signature into a `pydantic.BaseModel` subclass.

    *Unknown* or *un-imported* annotations (common with third-party libs that
    use forward-refs without importing the target – e.g. ``uuid.UUID`` in
    LangChain's `CallbackManagerForToolRun`) default to ``str`` instead of
    crashing `get_type_hints()`.
    """
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    fields: dict[str, tuple[type, object]] = {}
    for param in inspect.signature(func).parameters.values():
        raw_hint = hints.get(param.name, param.annotation)
        # Default to ``str`` for ForwardRef / string annotations or if we
        # couldn't resolve the type.
        hint: type = (
            raw_hint
            if raw_hint not in (inspect._empty, None, str)
            and not isinstance(raw_hint, (str, ForwardRef))
            else str
        )
        fields[param.name] = (hint, ...)  # "..."  → required

    return create_model(f"{func.__name__.title()}Args", **fields)  # type: ignore


# ────────────────────────────────────────────────────────────────────────────
# 1️⃣  plain Python function  (sync **or** async)
# ────────────────────────────────────────────────────────────────────────────


async def register_fn_tool(
    func: Callable,
    *,
    name: str | None = None,
    description: str | None = None,
    namespace: str = "default",
) -> None:
    """
    Register a plain function as a tool asynchronously.
    
    Args:
        func: The function to register (can be sync or async)
        name: Optional name for the tool (defaults to function name)
        description: Optional description (defaults to function docstring)
        namespace: Registry namespace (defaults to "default")
    """
    schema = _auto_schema(func)
    tool_name = name or func.__name__
    tool_description = (description or func.__doc__ or "").strip()
    
    # Create the tool wrapper class
    class _Tool:  # noqa: D401, N801 – internal auto-wrapper
        """Auto-generated tool wrapper for function."""
        
        async def execute(self, **kwargs: Any) -> Any:
            """Execute the wrapped function."""
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            # off-load blocking sync work
            return await anyio.to_thread.run_sync(func, **kwargs)
    
    # Set the docstring
    _Tool.__doc__ = tool_description
    
    # Get the registry and register directly
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(
        _Tool(),
        name=tool_name,
        namespace=namespace,
        metadata={
            "description": tool_description,
            "is_async": True,
            "argument_schema": schema.model_json_schema(),
            "source": "function",
            "source_name": func.__qualname__,
        }
    )


# ────────────────────────────────────────────────────────────────────────────
# 2️⃣  LangChain BaseTool (or anything that quacks like it)
# ────────────────────────────────────────────────────────────────────────────


async def register_langchain_tool(
    tool: Any,
    *,
    name: str | None = None,
    description: str | None = None,
    namespace: str = "default",
) -> None:
    """
    Register a **LangChain** `BaseTool` instance asynchronously.
    
    Works with any object exposing `.run` / `.arun` methods.

    Args:
        tool: The LangChain tool to register
        name: Optional name for the tool (defaults to tool.name)
        description: Optional description (defaults to tool.description)
        namespace: Registry namespace (defaults to "default")
        
    Raises:
        RuntimeError: If LangChain isn't installed
        TypeError: If the object isn't a LangChain BaseTool
    """
    if BaseTool is None:
        raise RuntimeError(
            "register_langchain_tool() requires LangChain - "
            "install with `pip install langchain`"
        )

    if not isinstance(tool, BaseTool):  # pragma: no cover
        raise TypeError(
            "Expected a langchain.tools.base.BaseTool instance – got "
            f"{type(tool).__name__}"
        )

    # Prefer async implementation if available
    fn = tool.arun if hasattr(tool, "arun") else tool.run
    
    tool_name = name or tool.name or tool.__class__.__name__
    tool_description = description or tool.description or (tool.__doc__ or "")
    
    await register_fn_tool(
        fn,
        name=tool_name,
        description=tool_description,
        namespace=namespace,
    )
    
    # Update the metadata to include LangChain info
    registry = await ToolRegistryProvider.get_registry()
    metadata = await registry.get_metadata(tool_name, namespace)
    
    if metadata:
        updated_metadata = metadata.model_copy()
        # Update source info
        updated_metadata.tags.add("langchain")
        
        # Re-register with updated metadata
        await registry.register_tool(
            await registry.get_tool(tool_name, namespace),
            name=tool_name,
            namespace=namespace,
            metadata=updated_metadata.model_dump(),
        )
