# chuk_tool_processor/guards/budget.py
"""Budget guard - enforces tool call limits.

Tracks discovery vs execution budgets separately:
- Discovery: search_tools, list_tools, get_tool_schema
- Execution: call_tool (actual work)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class BudgetGuardConfig(BaseModel):
    """Configuration for budget enforcement."""

    discovery_budget: int = Field(default=5)
    execution_budget: int = Field(default=12)
    total_budget: int = Field(default=15)

    # Patterns to classify tools
    discovery_patterns: set[str] = Field(
        default_factory=lambda: {
            "search_",
            "_search",
            "list_",
            "_list",
            "_schema",
            "schema_",
            "_tools",
            "tools_",
            "get_tool",
            "find_tool",
            "discover",
            "browse",
        }
    )
    execution_patterns: set[str] = Field(default_factory=lambda: {"call_", "execute_", "run_", "invoke_"})


class BudgetState(BaseModel):
    """Current budget state."""

    discovery_count: int = Field(default=0)
    execution_count: int = Field(default=0)
    total_count: int = Field(default=0)

    def increment_discovery(self) -> None:
        self.discovery_count += 1
        self.total_count += 1

    def increment_execution(self) -> None:
        self.execution_count += 1
        self.total_count += 1

    def reset(self) -> None:
        self.discovery_count = 0
        self.execution_count = 0
        self.total_count = 0


class BudgetGuard(BaseGuard):
    """Guard that enforces tool call budgets.

    Tracks separate budgets for discovery (tool shopping) and
    execution (actual work). Blocks when budgets are exhausted.
    """

    def __init__(
        self,
        config: BudgetGuardConfig | None = None,
    ):
        self.config = config or BudgetGuardConfig()
        self.state = BudgetState()
        self._discovered_tools: set[str] = set()

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Check if budget allows this call.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool (unused, for protocol compatibility)

        Returns:
            GuardResult - BLOCK if budget exhausted
        """
        # Classify the tool
        is_discovery = self._is_discovery_tool(tool_name)

        if is_discovery:
            if self.state.discovery_count >= self.config.discovery_budget:
                return self.block(
                    reason=self._format_discovery_exhausted(),
                    budget_type="discovery",
                    count=self.state.discovery_count,
                    limit=self.config.discovery_budget,
                )
        else:
            if self.state.execution_count >= self.config.execution_budget:
                return self.block(
                    reason=self._format_execution_exhausted(),
                    budget_type="execution",
                    count=self.state.execution_count,
                    limit=self.config.execution_budget,
                )

        # Check total budget
        if self.state.total_count >= self.config.total_budget:
            return self.block(
                reason=self._format_total_exhausted(),
                budget_type="total",
                count=self.state.total_count,
                limit=self.config.total_budget,
            )

        return self.allow()

    def record_call(self, tool_name: str) -> None:
        """Record a tool call (after execution)."""
        if self._is_discovery_tool(tool_name):
            self.state.increment_discovery()
        else:
            self.state.increment_execution()

    def register_discovered_tool(self, tool_name: str) -> None:
        """Register a tool as discovered."""
        self._discovered_tools.add(tool_name)

    def reset(self) -> None:
        """Reset for new prompt."""
        self.state.reset()
        self._discovered_tools.clear()

    def _is_discovery_tool(self, tool_name: str) -> bool:
        """Check if tool is a discovery tool."""
        name_lower = tool_name.lower()
        return any(pattern in name_lower for pattern in self.config.discovery_patterns)

    def _format_discovery_exhausted(self) -> str:
        """Format message when discovery budget exhausted."""
        tools = sorted(self._discovered_tools)
        lines = [
            f"**Discovery budget exhausted** ({self.state.discovery_count}/{self.config.discovery_budget})",
            "",
            "No more search_tools, list_tools, or get_tool_schema calls allowed.",
            "",
        ]
        if tools:
            lines.append("**Use these discovered tools:**")
            for name in tools[:10]:
                lines.append(f"  - {name}")
            lines.append("")
            lines.append("Call these directly using call_tool.")
        else:
            lines.append("No tools discovered. Provide your best answer without tools.")
        return "\n".join(lines)

    def _format_execution_exhausted(self) -> str:
        """Format message when execution budget exhausted."""
        return (
            f"**Execution budget exhausted** ({self.state.execution_count}/{self.config.execution_budget})\n\n"
            "No more tool executions allowed.\n"
            "Please provide your final answer using computed values."
        )

    def _format_total_exhausted(self) -> str:
        """Format message when total budget exhausted."""
        return (
            f"**Tool budget exhausted** ({self.state.total_count}/{self.config.total_budget})\n\n"
            "You must now provide your final answer.\n"
            "Do not request any more tool calls."
        )

    def get_status(self) -> dict[str, Any]:
        """Get current budget status."""
        return {
            "discovery": {
                "used": self.state.discovery_count,
                "limit": self.config.discovery_budget,
                "remaining": self.config.discovery_budget - self.state.discovery_count,
            },
            "execution": {
                "used": self.state.execution_count,
                "limit": self.config.execution_budget,
                "remaining": self.config.execution_budget - self.state.execution_count,
            },
            "total": {
                "used": self.state.total_count,
                "limit": self.config.total_budget,
                "remaining": self.config.total_budget - self.state.total_count,
            },
            "discovered_tools": list(self._discovered_tools),
        }
