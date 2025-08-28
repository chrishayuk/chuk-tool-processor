# chuk_tool_processor/utils/validation.py
"""
Async runtime helpers for validating tool inputs / outputs with Pydantic.

Public API
----------
validate_arguments(tool_name, fn, args) -> dict
validate_result(tool_name, fn, result)  -> Any
@with_validation                        -> class decorator
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

# exception
from chuk_tool_processor.core.exceptions import ToolValidationError

__all__ = [
    "validate_arguments",
    "validate_result",
    "with_validation",
]

# --------------------------------------------------------------------------- #
# helpers - create & cache ad-hoc pydantic models
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=256)
def _arg_model(tool_name: str, fn: Callable) -> type[BaseModel]:
    """Return (and memoise) a pydantic model derived from *fn*'s signature."""
    hints = get_type_hints(fn)
    hints.pop("return", None)

    sig = inspect.signature(fn)
    fields: dict[str, tuple[Any, Any]] = {}
    for name, hint in hints.items():
        param = sig.parameters[name]
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[name] = (hint, default)

    return create_model(  # type: ignore[call-overload, no-any-return]
        f"{tool_name}Args",
        __config__=ConfigDict(extra="forbid"),  # disallow unknown keys
        **fields,
    )


@lru_cache(maxsize=256)
def _result_model(tool_name: str, fn: Callable) -> type[BaseModel] | None:
    """Return a pydantic model for the annotated return type (or None)."""
    return_hint = get_type_hints(fn).get("return")
    if return_hint is None or return_hint is type(None):  # noqa: E721
        return None

    return create_model(
        f"{tool_name}Result",
        result=(return_hint, ...),
    )


# --------------------------------------------------------------------------- #
# public validation helpers - synced with async patterns
# --------------------------------------------------------------------------- #


def validate_arguments(tool_name: str, fn: Callable, args: dict[str, Any]) -> dict[str, Any]:
    """Validate function arguments against type hints."""
    try:
        model = _arg_model(tool_name, fn)
        return model(**args).model_dump()
    except ValidationError as exc:
        raise ToolValidationError(tool_name, {"errors": exc.errors()}) from exc


def validate_result(tool_name: str, fn: Callable, result: Any) -> Any:
    """Validate function return value against return type hint."""
    model = _result_model(tool_name, fn)
    if model is None:  # no annotation ⇒ no validation
        return result
    try:
        return model(result=result).result  # type: ignore[attr-defined]
    except ValidationError as exc:
        raise ToolValidationError(tool_name, {"errors": exc.errors()}) from exc


# --------------------------------------------------------------------------- #
# decorator for classic "imperative" tools - now requires async
# --------------------------------------------------------------------------- #


def with_validation(cls):
    """
    Wrap an async *execute* method with argument & result validation.

    ```
    @with_validation
    class MyTool:
        async def execute(self, x: int, y: int) -> int:
            return x + y
    ```
    """
    # Which method did the user provide?
    fn_name = "_execute" if hasattr(cls, "_execute") else "execute"
    original = getattr(cls, fn_name)

    # Ensure the method is async
    if not inspect.iscoroutinefunction(original):
        raise TypeError(f"Tool {cls.__name__} must have an async {fn_name} method")

    @wraps(original)
    async def _validated(self, **kwargs):
        name = cls.__name__
        kwargs = validate_arguments(name, original, kwargs)
        res = await original(self, **kwargs)
        return validate_result(name, original, res)

    setattr(cls, fn_name, _validated)
    return cls
