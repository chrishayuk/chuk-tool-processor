# chuk_tool_processor/guards/per_tool.py
"""Per-tool limit guard - prevents thrashing on single tools.

Limits how many times the same tool can be called in one turn.
Prevents loops where the model keeps calling the same tool.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import ToolClassification


class PerToolGuardConfig(BaseModel):
    """Configuration for per-tool limits."""

    # Default max calls per tool per turn
    default_limit: int = Field(default=3)

    # Per-tool overrides (tool_name -> limit)
    tool_limits: dict[str, int] = Field(default_factory=dict)

    # Tools exempt from limits - defaults to idempotent math tools AND discovery tools
    # Both are safe to call repeatedly without thrashing concerns
    # Pass an empty set to disable exemptions
    exempt_tools: set[str] = Field(
        default_factory=lambda: set(ToolClassification.IDEMPOTENT_MATH_TOOLS) | set(ToolClassification.DISCOVERY_TOOLS)
    )


class PerToolGuard(BaseGuard):
    """Guard that limits calls per tool per turn.

    Prevents the model from thrashing on a single tool.
    Exempt tools (math and discovery) can be called without limit.
    """

    def __init__(self, config: PerToolGuardConfig | None = None):
        self.config = config or PerToolGuardConfig()
        self._call_counts: dict[str, int] = {}

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Check if tool has exceeded its per-turn limit.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool (unused, for protocol compatibility)

        Returns:
            GuardResult - WARN if at limit, BLOCK if over
        """
        # Get base name for checking exemptions
        base_name = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()

        # Check if exempt
        if base_name in self.config.exempt_tools:
            return self.allow()

        # Get current count
        count = self._call_counts.get(tool_name, 0)

        # Get limit for this tool
        limit = self.config.tool_limits.get(tool_name, self.config.default_limit)

        if count >= limit:
            return self.block(
                reason=self._format_limit_message(tool_name, count, limit),
                tool_name=tool_name,
                call_count=count,
                limit=limit,
            )

        if count >= limit - 1:
            return self.warn(
                reason=f"Tool `{tool_name}` at limit ({count + 1}/{limit}). Next call may be blocked.",
                tool_name=tool_name,
                call_count=count + 1,
                limit=limit,
            )

        return self.allow()

    def record_call(self, tool_name: str) -> int:
        """Record a tool call and return new count."""
        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1
        return self._call_counts[tool_name]

    def get_call_count(self, tool_name: str) -> int:
        """Get current call count for a tool."""
        return self._call_counts.get(tool_name, 0)

    def reset(self) -> None:
        """Reset for new prompt."""
        self._call_counts.clear()

    def _format_limit_message(self, tool_name: str, count: int, limit: int) -> str:
        """Format message when limit is reached."""
        return (
            f"**Tool call limit reached**: `{tool_name}` called {count} times (limit: {limit})\n\n"
            "Either:\n"
            "  (a) Use existing results to answer, or\n"
            "  (b) Explain why another call is necessary."
        )

    def get_status(self) -> dict[str, Any]:
        """Get current per-tool status."""
        return {
            tool: {
                "count": count,
                "limit": self.config.tool_limits.get(tool, self.config.default_limit),
            }
            for tool, count in self._call_counts.items()
        }
