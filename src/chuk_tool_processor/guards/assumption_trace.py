# chuk_tool_processor/guards/assumption_trace.py
"""Assumption-Trace Consistency Guard.

Detects when the model states an assumption in natural language but then
computes something inconsistent with that assumption in the tool trace.

Example failure mode:
- Model says: "I'll assume CV=0.3, so σ_daily = 11.1"
- Model computes: multiply(37, sqrt(18)) → uses μ instead of σ_daily
- Guard flags: "You said σ_daily=11.1 but used 37 in σ_LT computation"

This guard is high-leverage because LLMs frequently "say X, compute Y"
under tool pressure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


@dataclass
class Assumption:
    """A stated assumption extracted from model text."""

    name: str  # e.g., "sigma_daily", "cv", "mean"
    value: float  # The numeric value
    source_text: str  # The original text snippet
    confidence: float = 1.0  # How confident we are in the extraction


@dataclass
class ToolCall:
    """A recorded tool call from the trace."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    result_binding: str | None = None  # e.g., "$v3"


@dataclass
class TraceViolation:
    """A detected inconsistency between assumption and trace."""

    assumption: Assumption
    tool_call: ToolCall
    expected_value: float
    actual_value: float
    message: str


class AssumptionTraceGuardConfig(BaseModel):
    """Configuration for the assumption-trace consistency guard."""

    # Tolerance for numeric comparison (relative)
    relative_tolerance: float = Field(default=0.01)

    # Tolerance for numeric comparison (absolute)
    absolute_tolerance: float = Field(default=1e-9)

    # Block vs warn on violation
    block_on_violation: bool = Field(default=False)

    # Patterns to extract assumptions from text
    # Maps pattern name to (regex, value_group_index)
    # Must be explicitly configured - no defaults
    assumption_patterns: dict[str, str] = Field(default_factory=dict)

    # Tool patterns that should use specific assumptions
    # Maps (tool_name, arg_name) to assumption_name
    # e.g., {("multiply", "a"): "sigma_daily"} means multiply's 'a' arg
    # should match the sigma_daily assumption when computing sigma_LT
    # Must be explicitly configured - no defaults
    tool_arg_constraints: dict[tuple[str, str], str] = Field(default_factory=dict)

    # Context patterns - what computation context triggers constraint checking
    # e.g., "sigma_lt" context means we're computing σ_LT
    # Must be explicitly configured - no defaults
    context_triggers: dict[str, set[str]] = Field(default_factory=dict)


class AssumptionTraceGuard(BaseGuard):
    """Guard that detects assumption-trace inconsistencies.

    This guard tracks:
    1. Assumptions stated in model text (via register_assumption or auto-extraction)
    2. Tool calls made by the model
    3. Whether tool arguments match stated assumptions

    When the model says "σ_daily = 11.1" but then calls multiply(37, sqrt(18)),
    this guard flags the inconsistency.

    Usage:
        guard = AssumptionTraceGuard(config)

        # Register assumptions from model text
        guard.extract_assumptions("I'll assume CV=0.3, so σ_daily = 11.1")

        # Or register directly
        guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        # Check tool calls for consistency
        result = guard.check("multiply", {"a": 37, "b": 4.24})
        # → WARN: "You stated σ_daily=11.1 but used 37 in computation"
    """

    def __init__(self, config: AssumptionTraceGuardConfig | None = None):
        self.config = config or AssumptionTraceGuardConfig()
        self._assumptions: dict[str, Assumption] = {}
        self._tool_trace: list[ToolCall] = []
        self._current_context: str | None = None
        self._violations: list[TraceViolation] = []

    def register_assumption(
        self,
        name: str,
        value: float,
        source_text: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Register an assumption stated by the model.

        Args:
            name: Assumption identifier (e.g., "sigma_daily", "cv")
            value: The numeric value
            source_text: Original text where assumption was stated
            confidence: Confidence in the extraction (0-1)
        """
        self._assumptions[name] = Assumption(
            name=name,
            value=value,
            source_text=source_text,
            confidence=confidence,
        )

    def extract_assumptions(self, text: str) -> list[Assumption]:
        """Extract assumptions from model-generated text.

        Uses configured patterns to find stated assumptions.

        Args:
            text: Model-generated text to scan

        Returns:
            List of extracted assumptions (also registered internally)
        """
        extracted = []

        for name, pattern in self.config.assumption_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Try to extract numeric value from the match
                    value_str = match.group(1) if match.groups() else match.group(0)
                    value = float(value_str)

                    assumption = Assumption(
                        name=name,
                        value=value,
                        source_text=match.group(0),
                        confidence=0.8,  # Lower confidence for auto-extraction
                    )
                    self._assumptions[name] = assumption
                    extracted.append(assumption)
                except (ValueError, IndexError):
                    continue

        return extracted

    def set_context(self, context: str) -> None:
        """Set the current computation context.

        Context determines which constraints to check.
        e.g., "sigma_lt" context checks that σ_daily (not μ) is used.

        Args:
            context: Context identifier
        """
        self._current_context = context

    def infer_context(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """Infer computation context from tool call pattern.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Returns:
            Inferred context name, or None
        """
        for context, triggers in self.config.context_triggers.items():
            # Check if tool name matches any trigger
            if tool_name.lower() in triggers:
                return context

            # Check if argument values suggest this context
            # (e.g., sqrt(18) suggests lead_time computation)
            for arg_value in arguments.values():
                if isinstance(arg_value, str) and arg_value.lower() in triggers:
                    return context

        return None

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if tool call is consistent with stated assumptions.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            GuardResult - WARN or BLOCK if inconsistency detected
        """
        # Record the tool call
        tool_call = ToolCall(tool_name=tool_name, arguments=arguments)
        self._tool_trace.append(tool_call)

        # Infer context if not explicitly set
        context = self._current_context or self.infer_context(tool_name, arguments)

        # Check for constraint violations
        violations = self._check_constraints(tool_call, context)

        if violations:
            self._violations.extend(violations)

            # Format violation message
            messages = []
            for v in violations:
                messages.append(
                    f"ASSUMPTION_VIOLATION: {v.message} (expected {v.expected_value}, got {v.actual_value})"
                )

            reason = "; ".join(messages)

            if self.config.block_on_violation:
                return self.block(
                    reason=reason,
                    tool_name=tool_name,
                    violations=[
                        {
                            "assumption": v.assumption.name,
                            "expected": v.expected_value,
                            "actual": v.actual_value,
                        }
                        for v in violations
                    ],
                )

            return self.warn(
                reason=reason,
                tool_name=tool_name,
                violations=[
                    {
                        "assumption": v.assumption.name,
                        "expected": v.expected_value,
                        "actual": v.actual_value,
                    }
                    for v in violations
                ],
            )

        return self.allow()

    def _check_constraints(
        self,
        tool_call: ToolCall,
        context: str | None,  # noqa: ARG002
    ) -> list[TraceViolation]:
        """Check tool call against configured constraints.

        Args:
            tool_call: The tool call to check
            context: Current computation context

        Returns:
            List of detected violations
        """
        violations = []

        for (tool_pattern, arg_name), assumption_name in self.config.tool_arg_constraints.items():
            # Check if this constraint applies
            if not self._tool_matches(tool_call.tool_name, tool_pattern):
                continue

            # Check if assumption exists
            if assumption_name not in self._assumptions:
                continue

            assumption = self._assumptions[assumption_name]

            # Check if argument exists and violates assumption
            if arg_name in tool_call.arguments:
                arg_value = tool_call.arguments[arg_name]

                try:
                    actual = float(arg_value)
                except (ValueError, TypeError):
                    continue

                if not self._values_match(assumption.value, actual):
                    violations.append(
                        TraceViolation(
                            assumption=assumption,
                            tool_call=tool_call,
                            expected_value=assumption.value,
                            actual_value=actual,
                            message=(
                                f"You stated {assumption_name}={assumption.value} "
                                f"but used {actual} in {tool_call.tool_name}({arg_name}=...)"
                            ),
                        )
                    )

        return violations

    def _tool_matches(self, tool_name: str, pattern: str) -> bool:
        """Check if tool name matches pattern."""
        tool_lower = tool_name.lower()
        pattern_lower = pattern.lower()

        # Exact match
        if tool_lower == pattern_lower:
            return True

        # Namespace match (e.g., "math.multiply" matches "multiply")
        if "." in tool_lower:
            base_name = tool_lower.split(".")[-1]
            if base_name == pattern_lower:
                return True

        return False

    def _values_match(self, expected: float, actual: float) -> bool:
        """Check if two values match within tolerance."""
        if expected == actual:
            return True

        # Absolute tolerance check
        if abs(expected - actual) <= self.config.absolute_tolerance:
            return True

        # Relative tolerance check
        if expected != 0:
            relative_diff = abs(expected - actual) / abs(expected)
            if relative_diff <= self.config.relative_tolerance:
                return True

        return False

    def check_output(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
        result: Any,
    ) -> GuardResult:
        """Record tool output and check for consistency.

        Args:
            tool_name: Name of the tool that was called
            arguments: Arguments passed to the tool
            result: The tool's output

        Returns:
            GuardResult - always ALLOW (output checking is passive)
        """
        # Update the last tool call with its result
        if self._tool_trace:
            self._tool_trace[-1].result = result

        return self.allow()

    def reset(self) -> None:
        """Reset guard state for a new prompt."""
        self._assumptions.clear()
        self._tool_trace.clear()
        self._current_context = None
        self._violations.clear()

    def get_assumptions(self) -> dict[str, Assumption]:
        """Get all registered assumptions."""
        return dict(self._assumptions)

    def get_trace(self) -> list[ToolCall]:
        """Get the recorded tool trace."""
        return list(self._tool_trace)

    def get_violations(self) -> list[TraceViolation]:
        """Get all detected violations."""
        return list(self._violations)

    def get_status(self) -> dict[str, Any]:
        """Get current guard status."""
        return {
            "assumptions": {name: {"value": a.value, "source": a.source_text} for name, a in self._assumptions.items()},
            "trace_length": len(self._tool_trace),
            "violations": len(self._violations),
            "current_context": self._current_context,
        }


# ============================================================================
# Pre-built Constraint Sets
# ============================================================================


def inventory_sigma_constraints() -> AssumptionTraceGuardConfig:
    """Pre-built config for inventory σ_LT computation checks.

    Catches the common error where model says "σ_daily = X" but then
    uses μ_daily in the σ_LT = σ_daily × √LT computation.

    Returns:
        Configured guard config for inventory problems
    """
    return AssumptionTraceGuardConfig(
        assumption_patterns={
            # Match patterns like "σ_daily = 11.1" or "sigma_daily = 11.1"
            "sigma_daily": r"(?:σ_daily|sigma_daily|daily.*(?:std|deviation))\s*[=:]\s*(\d+\.?\d*)",
            # Match CV patterns like "CV = 0.3" or "CV=0.3"
            "cv": r"(?:CV|coefficient.*variation)\s*[=:]\s*(\d+\.?\d*)",
            # Match mu patterns
            "mu_daily": r"(?:μ_daily|mu_daily|daily.*(?:mean|demand))\s*[=:]\s*(\d+\.?\d*)",
        },
        tool_arg_constraints={
            # When computing σ_LT, the first arg to multiply should be σ_daily, not μ
            # This is checked when context suggests σ_LT computation
            ("multiply", "a"): "sigma_daily",
        },
        context_triggers={
            # These tool calls / argument patterns suggest σ_LT computation
            "sigma_lt": {"sqrt", "lead_time", "sigma"},
        },
        block_on_violation=False,
    )
