# chuk_tool_processor/guards/base.py
"""Base protocol for tool call guards.

Guards are composable checks that run before/after tool execution.
Each guard focuses on one concern and returns a typed result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class GuardVerdict(str, Enum):
    """Verdict from a guard check."""

    ALLOW = "allow"  # Proceed with execution
    WARN = "warn"  # Proceed but log warning
    BLOCK = "block"  # Do not execute, return error
    REPAIR = "repair"  # Attempt to fix and retry


class GuardResult(BaseModel):
    """Result from a guard check."""

    verdict: GuardVerdict = Field(default=GuardVerdict.ALLOW)
    reason: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)

    # For REPAIR verdict - suggested fixes
    repaired_args: dict[str, Any] | None = Field(default=None)
    fallback_response: str | None = Field(default=None)

    @property
    def allowed(self) -> bool:
        """Check if execution should proceed."""
        return self.verdict in (GuardVerdict.ALLOW, GuardVerdict.WARN)

    @property
    def blocked(self) -> bool:
        """Check if execution is blocked."""
        return self.verdict == GuardVerdict.BLOCK

    def format_message(self) -> str:
        """Format a user-friendly message."""
        if self.verdict == GuardVerdict.ALLOW:
            return ""
        prefix = {
            GuardVerdict.WARN: "Warning",
            GuardVerdict.BLOCK: "Blocked",
            GuardVerdict.REPAIR: "Repairing",
        }.get(self.verdict, "")
        return f"{prefix}: {self.reason}" if self.reason else prefix


@runtime_checkable
class Guard(Protocol):
    """Protocol for tool call guards.

    Guards can check before execution (pre) and after execution (post).
    """

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if a tool call should be allowed.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            GuardResult with verdict and details
        """
        ...


class BaseGuard(ABC):
    """Abstract base class for guards with common functionality."""

    @abstractmethod
    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if a tool call should be allowed (pre-execution)."""
        ...

    def check_output(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
        result: Any,  # noqa: ARG002
    ) -> GuardResult:
        """Check tool output after execution (post-execution).

        Override this method in guards that need to inspect outputs.
        Default implementation allows all outputs.

        Args:
            tool_name: Name of the tool that was called
            arguments: Arguments that were passed to the tool
            result: The result returned by the tool

        Returns:
            GuardResult with verdict and details
        """
        return GuardResult(verdict=GuardVerdict.ALLOW)

    def allow(self, reason: str = "") -> GuardResult:
        """Helper to return ALLOW verdict."""
        return GuardResult(verdict=GuardVerdict.ALLOW, reason=reason)

    def warn(self, reason: str, **details: Any) -> GuardResult:
        """Helper to return WARN verdict."""
        return GuardResult(verdict=GuardVerdict.WARN, reason=reason, details=details)

    def block(self, reason: str, **details: Any) -> GuardResult:
        """Helper to return BLOCK verdict."""
        return GuardResult(verdict=GuardVerdict.BLOCK, reason=reason, details=details)

    def repair(
        self,
        reason: str,
        repaired_args: dict[str, Any] | None = None,
        fallback_response: str | None = None,
    ) -> GuardResult:
        """Helper to return REPAIR verdict."""
        return GuardResult(
            verdict=GuardVerdict.REPAIR,
            reason=reason,
            repaired_args=repaired_args,
            fallback_response=fallback_response,
        )
