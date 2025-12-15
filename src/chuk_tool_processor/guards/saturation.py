# chuk_tool_processor/guards/saturation.py
"""Saturation sanity guard - detects degenerate statistical outputs.

This guard catches common model errors in statistical calculations:
- CDF inputs that are too extreme (|Z| > threshold means result is 0/1)
- Repeated degenerate outputs (0.0, 1.0) that indicate saturated results
- Extreme Z-scores that suggest calculation errors

These patterns typically indicate the model made a math error upstream.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class SaturationGuardConfig(BaseModel):
    """Configuration for the saturation sanity guard."""

    # CDF tools that produce probability outputs
    # Must be explicitly configured - no defaults
    cdf_tools: set[str] = Field(default_factory=set)

    # Maximum |Z| value before warning (8σ is essentially 0/1)
    z_threshold: float = Field(default=8.0)

    # Warn vs block on extreme inputs
    block_on_extreme: bool = Field(default=False)

    # Track consecutive degenerate outputs
    max_consecutive_degenerate: int = Field(default=3)

    # Values considered degenerate (saturated)
    # Must be explicitly configured - no defaults
    degenerate_values: set[float] = Field(default_factory=set)

    # Tolerance for degenerate value matching
    tolerance: float = Field(default=1e-9)


class SaturationGuard(BaseGuard):
    """Guard that detects degenerate/saturated statistical outputs.

    This is a POST-execution guard that checks tool results for signs
    of calculation errors:

    1. CDF inputs with |x| > z_threshold (result will be 0 or 1)
    2. Repeated degenerate outputs suggesting model is stuck
    3. Extreme Z-scores that indicate upstream calculation errors

    When detected, the guard warns or blocks to prevent the model
    from continuing with garbage values.
    """

    def __init__(self, config: SaturationGuardConfig | None = None):
        self.config = config or SaturationGuardConfig()
        self._consecutive_degenerate = 0
        self._last_results: list[float] = []

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check CDF inputs for extreme values (pre-execution check).

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            GuardResult - WARN if extreme input detected
        """
        base_name = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()

        # Only check configured CDF tools
        if base_name not in self.config.cdf_tools:
            return self.allow()

        # Check for extreme x value in CDF call
        x_value = arguments.get("x")
        if x_value is None:
            return self.allow()

        try:
            x = float(x_value)
        except (ValueError, TypeError):
            return self.allow()

        # Check for standard normal CDF (mean=0, std=1)
        mean = float(arguments.get("mean", 0))
        std = float(arguments.get("std", 1))

        # Compute effective Z-score
        z = abs(x - mean) / std if std > 0 else float("inf")

        if z > self.config.z_threshold:
            reason = (
                f"SATURATION_WARNING: `{tool_name}` called with extreme Z-score "
                f"|Z|={z:.2f} > {self.config.z_threshold}. "
                f"This will return essentially 0 or 1, suggesting a calculation error. "
                f"Please verify the input computation (x={x}, mean={mean}, std={std})."
            )

            if self.config.block_on_extreme:
                return self.block(
                    reason=reason,
                    tool_name=tool_name,
                    z_score=z,
                    x=x,
                    mean=mean,
                    std=std,
                )
            return self.warn(
                reason=reason,
                tool_name=tool_name,
                z_score=z,
                x=x,
                mean=mean,
                std=std,
            )

        return self.allow()

    def check_output(
        self,
        tool_name: str,
        arguments: dict[str, Any],  # noqa: ARG002
        result: Any,
    ) -> GuardResult:
        """Check tool output for degenerate values (post-execution check).

        Args:
            tool_name: Name of the tool that was called
            arguments: Arguments passed to the tool (not used)
            result: The tool's output

        Returns:
            GuardResult - WARN if degenerate output detected
        """
        base_name = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()

        # Only check configured CDF tools
        if base_name not in self.config.cdf_tools:
            self._consecutive_degenerate = 0
            return self.allow()

        # Try to extract numeric result
        try:
            value = self._extract_numeric(result)
            if value is None:
                return self.allow()
        except (ValueError, TypeError):
            return self.allow()

        # Check if value is degenerate (0 or 1)
        is_degenerate = any(abs(value - degen) < self.config.tolerance for degen in self.config.degenerate_values)

        if is_degenerate:
            self._consecutive_degenerate += 1
            self._last_results.append(value)

            if self._consecutive_degenerate >= self.config.max_consecutive_degenerate:
                return self.warn(
                    reason=(
                        f"DEGENERATE_OUTPUT: {self._consecutive_degenerate} consecutive "
                        f"saturated results detected ({self._last_results[-3:]}). "
                        f"This indicates calculation errors upstream. "
                        f"Please re-verify the Z-score computation."
                    ),
                    tool_name=tool_name,
                    consecutive_count=self._consecutive_degenerate,
                    recent_results=self._last_results[-5:],
                )
        else:
            # Non-degenerate result, reset counter
            self._consecutive_degenerate = 0
            self._last_results.clear()

        return self.allow()

    def _extract_numeric(self, result: Any) -> float | None:
        """Extract numeric value from various result formats."""
        if isinstance(result, (int, float)):
            return float(result)

        if isinstance(result, str):
            try:
                return float(result)
            except ValueError:
                return None

        if isinstance(result, dict):
            # Try common keys
            for key in ("result", "value", "output"):
                if key in result:
                    return self._extract_numeric(result[key])

        return None

    def reset(self) -> None:
        """Reset state for new prompt."""
        self._consecutive_degenerate = 0
        self._last_results.clear()

    def get_status(self) -> dict[str, Any]:
        """Get current guard status."""
        return {
            "consecutive_degenerate": self._consecutive_degenerate,
            "recent_results": self._last_results[-5:],
        }
