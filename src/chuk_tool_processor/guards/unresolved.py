# chuk_tool_processor/guards/unresolved.py
"""Unresolved reference guard - detects unsubstituted placeholders.

This is a generic guard that blocks tool calls containing unresolved
placeholder/reference patterns. The actual resolution logic belongs
in the calling layer (e.g., mcp-cli's reference resolver).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel

# Common placeholder patterns
DEFAULT_PLACEHOLDER_PATTERNS: list[str] = [
    r"\$\{[^}]+\}",  # ${var} style
    r"\$[a-zA-Z_][a-zA-Z0-9_]*",  # $var style
    r"\{\{[^}]+\}\}",  # {{var}} mustache style
    r"<[A-Z_]+>",  # <PLACEHOLDER> style
]


class UnresolvedReferenceGuardConfig(BaseModel):
    """Configuration for unresolved reference detection."""

    # Regex patterns that indicate unresolved placeholders
    placeholder_patterns: list[str] = Field(default_factory=lambda: DEFAULT_PLACEHOLDER_PATTERNS.copy())

    # How many unresolved calls before blocking
    grace_calls: int = Field(default=1)

    # Enforcement level
    mode: EnforcementLevel = Field(default=EnforcementLevel.WARN)


class UnresolvedReferenceGuard(BaseGuard):
    """Guard that detects unresolved placeholder arguments.

    An unresolved call is when arguments contain placeholder patterns
    that should have been substituted by a resolver layer before execution.

    This is a generic implementation - specific placeholder semantics
    (like $vN for transcript variables) should be handled by the caller's
    reference resolver before calling the tool processor.
    """

    def __init__(
        self,
        config: UnresolvedReferenceGuardConfig | None = None,
        get_allowed_patterns: Callable[[], set[str]] | None = None,
    ):
        self.config = config or UnresolvedReferenceGuardConfig()
        self._get_allowed_patterns = get_allowed_patterns
        self._unresolved_count = 0
        self._compiled_patterns: list[re.Pattern[str]] = [re.compile(p) for p in self.config.placeholder_patterns]

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if tool call has unresolved placeholder arguments.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool

        Returns:
            GuardResult - WARN or BLOCK if unresolved placeholders found
        """
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        # Find any unresolved placeholders
        unresolved = self._find_unresolved(arguments)
        if not unresolved:
            return self.allow()

        # Unresolved placeholders detected
        self._unresolved_count += 1

        # Build message
        placeholders_str = ", ".join(f"`{p}`" for p in unresolved[:5])
        if len(unresolved) > 5:
            placeholders_str += f" (+{len(unresolved) - 5} more)"

        message = (
            f"Unresolved placeholders in `{tool_name}`: {placeholders_str}. These should be resolved before execution."
        )

        # Check enforcement level
        if self.config.mode == EnforcementLevel.BLOCK and self._unresolved_count > self.config.grace_calls:
            return self.block(
                reason=message,
                unresolved_count=self._unresolved_count,
                placeholders=unresolved,
            )
        else:
            return self.warn(
                reason=message,
                unresolved_count=self._unresolved_count,
                grace_remaining=max(0, self.config.grace_calls - self._unresolved_count + 1),
                placeholders=unresolved,
            )

    def reset(self) -> None:
        """Reset for new prompt."""
        self._unresolved_count = 0

    def _find_unresolved(self, arguments: dict[str, Any]) -> list[str]:
        """Find unresolved placeholder patterns in arguments."""
        unresolved: list[str] = []

        # Get any patterns that are explicitly allowed
        allowed = self._get_allowed_patterns() if self._get_allowed_patterns else set()

        def check_value(value: Any) -> None:
            if isinstance(value, str):
                for pattern in self._compiled_patterns:
                    for match in pattern.findall(value):
                        if match not in allowed:
                            unresolved.append(match)
            elif isinstance(value, dict):
                for v in value.values():
                    check_value(v)
            elif isinstance(value, list):
                for item in value:
                    check_value(item)

        for _key, value in arguments.items():
            check_value(value)

        return unresolved
