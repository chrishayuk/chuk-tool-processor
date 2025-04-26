# chuk_tool_processor/registry/auto_register.py
"""
Tiny “auto-register” helpers so you can do

    register_fn_tool(my_function)
    register_langchain_tool(my_langchain_tool)

and they immediately show up in the global registry.
"""

from __future__ import annotations

import asyncio
import inspect
import types
from typing import Callable, ForwardRef, Type, get_type_hints

import anyio
from pydantic import BaseModel, create_model

try:  # optional dependency
    from langchain.tools.base import BaseTool  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    BaseTool = None  # noqa: N816  – keep the name for isinstance() checks

from chuk_tool_processor.registry.decorators import register_tool


# ────────────────────────────────────────────────────────────────────────────
# internals – build a Pydantic schema from an arbitrary callable
# ────────────────────────────────────────────────────────────────────────────


def _auto_schema(func: Callable) -> Type[BaseModel]:
    """
    Turn a function signature into a `pydantic.BaseModel` subclass.

    *Unknown* or *un-imported* annotations (common with third-party libs that
    use forward-refs without importing the target – e.g. ``uuid.UUID`` in
    LangChain’s `CallbackManagerForToolRun`) default to ``str`` instead of
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
        # couldn’t resolve the type.
        hint: type = (
            raw_hint
            if raw_hint not in (inspect._empty, None, str)
            and not isinstance(raw_hint, (str, ForwardRef))
            else str
        )
        fields[param.name] = (hint, ...)  # “...”  → required

    return create_model(f"{func.__name__.title()}Args", **fields)  # type: ignore


# ────────────────────────────────────────────────────────────────────────────
# 1️⃣  plain Python function  (sync **or** async)
# ────────────────────────────────────────────────────────────────────────────


def register_fn_tool(
    func: Callable,
    *,
    name: str | None = None,
    description: str | None = None,
) -> None:
    """Register a plain function as a tool – one line is all you need."""

    schema = _auto_schema(func)
    name = name or func.__name__
    description = (description or func.__doc__ or "").strip()

    @register_tool(name=name, description=description, arg_schema=schema)
    class _Tool:  # noqa: D401, N801 – internal auto-wrapper
        async def _execute(self, **kwargs):
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            # off-load blocking sync work
            return await anyio.to_thread.run_sync(func, **kwargs)


# ────────────────────────────────────────────────────────────────────────────
# 2️⃣  LangChain BaseTool (or anything that quacks like it)
# ────────────────────────────────────────────────────────────────────────────


def register_langchain_tool(
    tool,
    *,
    name: str | None = None,
    description: str | None = None,
) -> None:
    """
    Register a **LangChain** `BaseTool` instance (or anything exposing
    ``.run`` / ``.arun``).

    If LangChain isn’t installed you’ll get a clear error instead of an import
    failure deep in the stack.
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

    fn = tool.arun if hasattr(tool, "arun") else tool.run  # prefer async
    register_fn_tool(
        fn,
        name=name or tool.name or tool.__class__.__name__,
        description=description or tool.description or (tool.__doc__ or ""),
    )
