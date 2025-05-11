# chuk_tool_processor/models/validated_tool.py
"""
Self-contained base-class for *declarative* async-native tools.

Subclass it like so:

    class Add(ValidatedTool):
        class Arguments(BaseModel):
            x: int
            y: int

        class Result(BaseModel):
            sum: int

        async def _execute(self, *, x: int, y: int) -> Result:
            return self.Result(sum=x + y)
"""
from __future__ import annotations

import html
import inspect
import json
from typing import Any, Dict, TypeVar, Callable

from pydantic import BaseModel, ValidationError

from chuk_tool_processor.core.exceptions import ToolValidationError

__all__ = [
    "ValidatedTool",
    "with_validation",
]

T_Validated = TypeVar("T_Validated", bound="ValidatedTool")


# --------------------------------------------------------------------------- #
# Helper mix-in – serialise a *class* into assorted formats
# --------------------------------------------------------------------------- #
class _ExportMixin:
    """Static helpers that expose a tool class in other specs."""

    # ------------------------------------------------------------------ #
    # OpenAI Chat-Completions `tools=[…]`
    # ------------------------------------------------------------------ #
    @classmethod
    def to_openai(
        cls: type[T_Validated],
        *,
        registry_name: str | None = None,
    ) -> Dict[str, Any]:
        """
        Build the structure expected by `tools=[…]`.

        Parameters
        ----------
        registry_name
            When the registry has stored the tool under a *different* key
            (e.g. ``"weather"`` vs class ``WeatherTool``) pass that key so
            `function.name` and later look-ups line up.
        """
        fn_name = registry_name or cls.__name__
        description = (cls.__doc__ or f"{fn_name} tool").strip()

        return {
            "type": "function",
            "function": {
                "name": fn_name,
                "description": description,
                "parameters": cls.Arguments.model_json_schema(),  # type: ignore[attr-defined]
            },
        }

    # ------------------------------------------------------------------ #
    # Plain JSON schema (arguments only)
    # ------------------------------------------------------------------ #
    @classmethod
    def to_json_schema(cls: type[T_Validated]) -> Dict[str, Any]:
        return cls.Arguments.model_json_schema()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Tiny XML tag – handy for unit-tests / demos
    # ------------------------------------------------------------------ #
    @classmethod
    def to_xml_tag(cls: type[T_Validated], **arguments: Any) -> str:
        return (
            f'<tool name="{html.escape(cls.__name__)}" '
            f"args='{html.escape(json.dumps(arguments))}'/>"
        )


# --------------------------------------------------------------------------- #
# The public validated base-class
# --------------------------------------------------------------------------- #
class ValidatedTool(_ExportMixin, BaseModel):
    """Pydantic-validated base for new async-native tools."""

    # ------------------------------------------------------------------ #
    # Inner models – override in subclasses
    # ------------------------------------------------------------------ #
    class Arguments(BaseModel):  # noqa: D401 – acts as a namespace
        """Input model"""

    class Result(BaseModel):  # noqa: D401
        """Output model"""

    # ------------------------------------------------------------------ #
    # Public entry-point called by the processor
    # ------------------------------------------------------------------ #
    async def execute(self: T_Validated, **kwargs: Any) -> BaseModel:
        """Validate *kwargs*, run `_execute`, validate the result."""
        try:
            args = self.Arguments(**kwargs)  # type: ignore[arg-type]
            res = await self._execute(**args.model_dump())  # type: ignore[arg-type]

            return (
                res
                if isinstance(res, self.Result)
                else self.Result(**(res if isinstance(res, dict) else {"value": res}))
            )
        except ValidationError as exc:
            raise ToolValidationError(self.__class__.__name__, exc.errors()) from exc

    # ------------------------------------------------------------------ #
    # Sub-classes must implement this
    # ------------------------------------------------------------------ #
    async def _execute(self, **_kwargs: Any):  # noqa: D401 – expected override
        raise NotImplementedError("Tool must implement async _execute()")


# --------------------------------------------------------------------------- #
# Decorator to retrofit validation onto classic "imperative" tools
# --------------------------------------------------------------------------- #
def with_validation(cls):  # noqa: D401 – factory
    """
    Decorator that wraps an existing async ``execute`` method with:

    * argument validation (based on type hints)
    * result validation (based on return annotation)
    """
    from chuk_tool_processor.utils.validation import (
        validate_arguments,
        validate_result,
    )

    original = cls.execute  # type: ignore[attr-defined]
    if not inspect.iscoroutinefunction(original):
        raise TypeError(f"Tool {cls.__name__} must have an async execute method")

    async def _async_wrapper(self, **kwargs):  # type: ignore[override]
        tool_name = cls.__name__
        validated = validate_arguments(tool_name, original, kwargs)
        result = await original(self, **validated)
        return validate_result(tool_name, original, result)

    cls.execute = _async_wrapper  # type: ignore[assignment]
    return cls
