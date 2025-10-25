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
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from chuk_tool_processor.core.exceptions import ToolValidationError

__all__ = [
    "ValidatedTool",
    "with_validation",
]

T_Validated = TypeVar("T_Validated", bound="ValidatedTool")


# --------------------------------------------------------------------------- #
# Helper mix-in - serialise a *class* into assorted formats
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
    ) -> dict[str, Any]:
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
                "parameters": cls.Arguments.model_json_schema(),
            },
        }

    # ------------------------------------------------------------------ #
    # Plain JSON schema (arguments only)
    # ------------------------------------------------------------------ #
    @classmethod
    def to_json_schema(cls: type[T_Validated]) -> dict[str, Any]:
        return cls.Arguments.model_json_schema()

    # ------------------------------------------------------------------ #
    # Tiny XML tag - handy for unit-tests / demos
    # ------------------------------------------------------------------ #
    @classmethod
    def to_xml_tag(cls: type[T_Validated], **arguments: Any) -> str:  # type: ignore[misc]
        return f"<tool name=\"{html.escape(cls.__name__)}\" args='{html.escape(json.dumps(arguments))}'/>"


# --------------------------------------------------------------------------- #
# The public validated base-class
# --------------------------------------------------------------------------- #
class ValidatedTool(_ExportMixin, BaseModel):
    """Pydantic-validated base for new async-native tools."""

    # ------------------------------------------------------------------ #
    # Inner models - override in subclasses
    # ------------------------------------------------------------------ #
    class Arguments(BaseModel):  # noqa: D401 - acts as a namespace
        """Input model with LLM-friendly coercion defaults."""

        model_config = ConfigDict(
            # Coerce string numbers to actual numbers
            coerce_numbers_to_str=False,
            # Strip whitespace from strings
            str_strip_whitespace=True,
            # Validate default values
            validate_default=True,
            # Be lenient with extra fields (ignore them)
            extra="ignore",
            # Use enum values instead of enum objects
            use_enum_values=True,
        )

    class Result(BaseModel):  # noqa: D401
        """Output model"""

        model_config = ConfigDict(
            # Validate default values in results too
            validate_default=True,
            # Use enum values in outputs
            use_enum_values=True,
        )

    # ------------------------------------------------------------------ #
    # Public entry-point called by the processor
    # ------------------------------------------------------------------ #
    async def execute(self: T_Validated, **kwargs: Any) -> BaseModel:
        """Validate *kwargs*, run `_execute`, validate the result."""
        try:
            args = self.Arguments(**kwargs)
            res = await self._execute(**args.model_dump())

            return (
                res
                if isinstance(res, self.Result)
                else self.Result(**(res if isinstance(res, dict) else {"value": res}))
            )
        except ValidationError as exc:
            raise ToolValidationError(self.__class__.__name__, {"errors": exc.errors()}) from exc

    # ------------------------------------------------------------------ #
    # Sub-classes must implement this
    # ------------------------------------------------------------------ #
    async def _execute(self, **_kwargs: Any):  # noqa: D401 - expected override
        raise NotImplementedError("Tool must implement async _execute()")


# --------------------------------------------------------------------------- #
# Decorator to retrofit validation onto classic "imperative" tools
# --------------------------------------------------------------------------- #
def with_validation(cls):  # noqa: D401 - factory
    """
    Decorator that wraps an existing async ``execute`` method with:

    * argument validation (based on type hints)
    * result validation (based on return annotation)
    """
    from chuk_tool_processor.utils.validation import (
        validate_arguments,
        validate_result,
    )

    original = cls.execute
    if not inspect.iscoroutinefunction(original):
        raise TypeError(f"Tool {cls.__name__} must have an async execute method")

    async def _async_wrapper(self, **kwargs):
        tool_name = cls.__name__
        validated = validate_arguments(tool_name, original, kwargs)
        result = await original(self, **validated)
        return validate_result(tool_name, original, result)

    cls.execute = _async_wrapper
    return cls
