# chuk_tool_processor/guards/precondition.py
"""Precondition guard - blocks premature tool calls.

This guard enforces that parameterized tools (like normal_cdf) can only
be called with values that were computed by prior tool calls. Prevents the
model from inventing arguments (e.g., fabricating σ values for statistics).

Key insight: It's not enough that *some* bindings exist - the actual numeric
arguments must match bound values, otherwise the model is making up inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class PreconditionGuardConfig(BaseModel):
    """Configuration for the precondition guard."""

    # Tools that require computed values before calling
    # Must be explicitly configured - no defaults
    parameterized_tools: set[str] = Field(default_factory=set)

    # If True, only require *some* bindings exist (lenient - original behavior)
    # If False, require that numeric args actually match bound values (strict)
    lenient_mode: bool = Field(default=False)

    # Tolerance for floating point comparison when matching values
    float_tolerance: float = Field(default=1e-9)

    # Values that are always allowed without being computed or user-provided
    # Must be explicitly configured - no defaults
    safe_values: set[float] = Field(default_factory=set)


class PreconditionGuard(BaseGuard):
    """Guard that blocks parameterized tool calls with ungrounded arguments.

    In strict mode (default), this guard requires that numeric arguments to
    parameterized tools actually match values that were computed by prior
    tool calls. This prevents the model from inventing values mid-calculation.

    The caller must configure which tools are parameterized and what values
    are safe (allowed without grounding).
    """

    def __init__(
        self,
        config: PreconditionGuardConfig | None = None,
        get_binding_count: Callable[[], int] | None = None,
        get_binding_values: Callable[[], set[float]] | None = None,
        get_user_literals: Callable[[], set[float]] | None = None,
    ):
        self.config = config or PreconditionGuardConfig()
        self._get_binding_count = get_binding_count
        self._get_binding_values = get_binding_values
        self._get_user_literals = get_user_literals

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if tool call preconditions are met.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            GuardResult - BLOCK if preconditions not met
        """
        # Extract base tool name (handle namespaced names)
        base_name = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()

        # Only check parameterized tools
        if base_name not in self.config.parameterized_tools:
            return self.allow()

        # Find numeric arguments (excluding skipped ones like mean/std)
        numeric_args = self._find_checkable_numeric_args(arguments)
        if not numeric_args:
            # No numeric args to check - allow (might be a schema check)
            return self.allow()

        # Get binding count
        binding_count = self._get_binding_count() if self._get_binding_count else 0

        if binding_count == 0:
            # No bindings at all - block if there are numeric args
            return self.block(
                reason=(
                    f"PRECONDITION_FAILED: `{tool_name}` called with {numeric_args} "
                    f"but no intermediate values have been computed yet. "
                    f"Please compute the required input values first."
                ),
                tool_name=tool_name,
                numeric_args=numeric_args,
            )

        # In lenient mode, just check that *some* bindings exist
        if self.config.lenient_mode:
            return self.allow()

        # STRICT MODE: Check that numeric args actually match bound values
        return self._check_args_grounded(tool_name, numeric_args)

    def _find_checkable_numeric_args(self, arguments: dict[str, Any]) -> dict[str, float]:
        """Find numeric arguments that need to be checked.

        Excludes:
        - tool_name argument
        - Boolean values
        - Values in configured safe_values

        All other numeric arguments must be grounded in prior tool
        results or user-provided values.
        """
        numeric = {}
        for key, value in arguments.items():
            if key == "tool_name":
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                # Skip safe values (0, 1, etc.)
                if float(value) in self.config.safe_values:
                    continue
                numeric[key] = float(value)
        return numeric

    def _check_args_grounded(
        self,
        tool_name: str,
        numeric_args: dict[str, float],
    ) -> GuardResult:
        """Check that numeric arguments are grounded in computed or user values."""
        # Get all allowed values: bindings + user literals
        allowed_values: set[float] = set()

        if self._get_binding_values:
            allowed_values.update(self._get_binding_values())

        if self._get_user_literals:
            allowed_values.update(self._get_user_literals())

        # Check each numeric argument
        ungrounded: dict[str, float] = {}
        for arg_name, arg_value in numeric_args.items():
            if not self._value_is_grounded(arg_value, allowed_values):
                ungrounded[arg_name] = arg_value

        if not ungrounded:
            return self.allow()

        # Some arguments are ungrounded - block
        grounded_list = sorted(allowed_values)[:10]  # Show first 10 for context
        return self.block(
            reason=(
                f"PRECONDITION_FAILED: `{tool_name}` called with ungrounded values: "
                f"{ungrounded}. These values were not computed by prior tools "
                f"or provided by the user. Available computed values: {grounded_list}. "
                f"Please either compute these values first, or ask the user to provide them."
            ),
            tool_name=tool_name,
            ungrounded_args=ungrounded,
            available_values=grounded_list,
        )

    def _value_is_grounded(self, value: float, allowed: set[float]) -> bool:
        """Check if a value matches any allowed value within tolerance."""
        return any(abs(value - allowed_val) < self.config.float_tolerance for allowed_val in allowed)
