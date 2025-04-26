# chuk_tool_processor/utils/validation.py
"""
Runtime helpers for validating tool inputs / outputs with Pydantic.

Public API
----------
validate_arguments(tool_name, fn, args) -> dict
validate_result(tool_name, fn, result)  -> Any
@with_validation                        -> class decorator
"""
from __future__ import annotations
import inspect
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, get_type_hints
from pydantic import BaseModel, ValidationError, create_model, Extra

# excpetion
from chuk_tool_processor.core.exceptions import ToolValidationError

__all__ = [
    "validate_arguments",
    "validate_result",
    "with_validation",
]

# --------------------------------------------------------------------------- #
# helpers – create & cache ad-hoc pydantic models
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=256)
def _arg_model(tool_name: str, fn: Callable) -> type[BaseModel]:
    """Return (and memoise) a pydantic model derived from *fn*'s signature."""
    hints = get_type_hints(fn)
    hints.pop("return", None)

    sig = inspect.signature(fn)
    fields: Dict[str, tuple[Any, Any]] = {}
    for name, hint in hints.items():
        param = sig.parameters[name]
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[name] = (hint, default)

    return create_model(
        f"{tool_name}Args",
        __config__=type(
            "Cfg",
            (),
            {"extra": Extra.forbid},  # disallow unknown keys
        ),
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
# public validation helpers
# --------------------------------------------------------------------------- #


def validate_arguments(tool_name: str, fn: Callable, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        model = _arg_model(tool_name, fn)
        return model(**args).dict()
    except ValidationError as exc:
        raise ToolValidationError(tool_name, exc.errors()) from exc


def validate_result(tool_name: str, fn: Callable, result: Any) -> Any:
    model = _result_model(tool_name, fn)
    if model is None:  # no annotation ⇒ no validation
        return result
    try:
        return model(result=result).result
    except ValidationError as exc:
        raise ToolValidationError(tool_name, exc.errors()) from exc


# --------------------------------------------------------------------------- #
# decorator for classic “imperative” tools
# --------------------------------------------------------------------------- #


def with_validation(cls):
    """
    Wrap *execute* / *_execute* so that their arguments & return values
    are type-checked each call.

    ```
    @with_validation
    class MyTool:
        def execute(self, x: int, y: int) -> int:
            return x + y
    ```
    """

    # Which method did the user provide?
    fn_name = "_execute" if hasattr(cls, "_execute") else "execute"
    original = getattr(cls, fn_name)

    @wraps(original)
    def _validated(self, **kwargs):
        name = cls.__name__
        kwargs = validate_arguments(name, original, kwargs)
        res = original(self, **kwargs)
        return validate_result(name, original, res)

    setattr(cls, fn_name, _validated)
    return cls
