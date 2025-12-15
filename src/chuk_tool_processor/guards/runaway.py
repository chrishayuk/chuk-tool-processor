# chuk_tool_processor/guards/runaway.py
"""Runaway detection guard - stops degenerate/saturated loops.

Detects patterns that indicate the model is stuck:
- Degenerate values (0.0, 1.0)
- Repeating values (same result N times)
- Numeric saturation (values below machine precision)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class RunawayGuardConfig(BaseModel):
    """Configuration for runaway detection."""

    # Values that indicate saturation
    degenerate_values: set[float] = Field(default_factory=lambda: {0.0, 1.0})

    # How many times same value repeats before stopping
    repeat_threshold: int = Field(default=3)

    # Values below this are "effectively zero"
    saturation_threshold: float = Field(default=1e-12)

    # How many recent results to track
    history_window: int = Field(default=5)


class RunawayGuard(BaseGuard):
    """Guard that detects runaway/stuck patterns.

    Monitors recent numeric results and blocks when:
    - Degenerate values appear repeatedly (0.0, 1.0)
    - Same value repeats too many times
    - Values saturate to machine precision limits
    """

    def __init__(self, config: RunawayGuardConfig | None = None):
        self.config = config or RunawayGuardConfig()
        self._recent_values: list[float] = []
        self._degenerate_count = 0

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Check for runaway patterns.

        Args:
            tool_name: Name of the tool (unused, for protocol compatibility)
            arguments: Arguments passed to the tool (unused, for protocol compatibility)

        Note: This guard checks AFTER recording a result.
        Call record_result() first, then check().
        """
        if not self._recent_values:
            return self.allow()

        last_value = self._recent_values[-1]

        # Check for degenerate values
        if last_value in self.config.degenerate_values:
            self._degenerate_count += 1
            if self._degenerate_count >= 2:
                return self.block(
                    reason=f"Repeated degenerate value: {last_value}",
                    pattern="degenerate",
                    value=last_value,
                    count=self._degenerate_count,
                )

        # Check for saturation (very small non-zero values)
        if isinstance(last_value, float) and 0 < abs(last_value) < self.config.saturation_threshold:
            return self.block(
                reason=f"Numeric saturation: {last_value:.2e} (effectively zero)",
                pattern="saturation",
                value=last_value,
            )

        # Check for repeating values
        if len(self._recent_values) >= self.config.repeat_threshold:
            recent = self._recent_values[-self.config.repeat_threshold :]
            if len(set(recent)) == 1:
                return self.block(
                    reason=f"Repeating value: {recent[0]} ({self.config.repeat_threshold}x)",
                    pattern="repeat",
                    value=recent[0],
                    count=self.config.repeat_threshold,
                )

        return self.allow()

    def record_result(self, value: Any) -> None:
        """Record a numeric result for pattern detection."""
        if isinstance(value, (int, float)):
            self._recent_values.append(float(value))
            # Keep only recent window
            if len(self._recent_values) > self.config.history_window:
                self._recent_values.pop(0)

    def reset(self) -> None:
        """Reset for new prompt."""
        self._recent_values.clear()
        self._degenerate_count = 0

    def format_saturation_message(self, value: float) -> str:
        """Format message when saturation is detected."""
        if abs(value) < self.config.saturation_threshold:
            interpretation = "effectively zero (< 1e-12)"
        elif value == 0.0:
            interpretation = "exactly zero"
        elif value == 1.0:
            interpretation = "exactly 1.0 (certainty)"
        else:
            interpretation = f"{value:.2e}"

        return (
            f"**Numeric saturation detected**: Result is {interpretation}\n\n"
            "Further tool calls would not provide additional precision.\n"
            "This is the limit of floating-point accuracy for this calculation.\n\n"
            "Please provide your final answer using these values."
        )
