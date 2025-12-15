# chuk_tool_processor/guards/retry_safety.py
"""Retry safety guard for controlling retry behavior.

Enforces idempotency keys, backoff policies, and retry limits.
"""

from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class ErrorClass(str, Enum):
    """Classification of errors for retry decisions."""

    VALIDATION = "validation"
    AUTH = "auth"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NETWORK = "network"
    UNKNOWN = "unknown"


class RetryState(BaseModel):
    """State for tracking retries."""

    signature: str
    tool_name: str
    attempt_count: int = 0
    first_attempt_ms: int
    last_attempt_ms: int
    last_error_class: ErrorClass | None = None


class RetrySafetyConfig(BaseModel):
    """Configuration for RetrySafetyGuard."""

    require_idempotency_key: bool = Field(
        default=False,
        description="Require idempotency key for non-idempotent tools",
    )
    idempotency_key_arg: str = Field(
        default="_idempotency_key",
        description="Argument name for idempotency key",
    )
    non_retryable_errors: set[ErrorClass] = Field(
        default_factory=lambda: {
            ErrorClass.VALIDATION,
            ErrorClass.AUTH,
            ErrorClass.PERMISSION,
            ErrorClass.NOT_FOUND,
        },
        description="Error classes that should not be retried",
    )
    max_same_signature_retries: int = Field(
        default=3,
        description="Maximum retries for same (tool, args) signature",
    )
    enforce_backoff: bool = Field(
        default=True,
        description="Enforce exponential backoff between retries",
    )
    min_backoff_ms: int = Field(
        default=100,
        description="Minimum backoff time in milliseconds",
    )
    max_backoff_ms: int = Field(
        default=30_000,
        description="Maximum backoff time in milliseconds",
    )
    backoff_multiplier: float = Field(
        default=2.0,
        description="Multiplier for exponential backoff",
    )
    idempotent_tools: set[str] = Field(
        default_factory=set,
        description="Tools known to be idempotent (safe to retry)",
    )
    non_idempotent_tools: set[str] = Field(
        default_factory=set,
        description="Tools known to be non-idempotent",
    )
    enforcement_level: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level for violations",
    )


class RetrySafetyGuard(BaseGuard):
    """Guard that controls retry behavior.

    Features:
    - Idempotency key requirement for non-idempotent tools
    - Block retries on certain error classes
    - Track same-signature retry counts
    - Enforce exponential backoff timing
    """

    def __init__(self, config: RetrySafetyConfig | None = None) -> None:
        self.config = config or RetrySafetyConfig()
        self._retry_state: dict[str, RetryState] = {}

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if retry is allowed."""
        signature = self._compute_signature(tool_name, arguments)
        state = self._retry_state.get(signature)

        if state is None:
            # First attempt - always allowed
            return self.allow()

        # Check idempotency key requirement
        idempotency_violation = self._check_idempotency_key(tool_name, arguments)
        if idempotency_violation:
            return idempotency_violation

        # Check retry count
        count_violation = self._check_retry_count(state)
        if count_violation:
            return count_violation

        # Check backoff timing
        backoff_violation = self._check_backoff(state)
        if backoff_violation:
            return backoff_violation

        return self.allow()

    def check_retry_after_error(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        error_class: ErrorClass,
    ) -> GuardResult:
        """Check if retry is allowed after a specific error."""
        # Check if error class is non-retryable
        if error_class in self.config.non_retryable_errors:
            message = f"Error class '{error_class.value}' is non-retryable for tool '{tool_name}'"
            return self._enforcement_result(message, tool_name, error_class)

        # Run standard checks
        return self.check(tool_name, arguments)

    def record_attempt(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        error_class: ErrorClass | None = None,
    ) -> RetryState:
        """Record an execution attempt."""
        signature = self._compute_signature(tool_name, arguments)
        now_ms = self._now_ms()

        if signature in self._retry_state:
            state = self._retry_state[signature]
            state.attempt_count += 1
            state.last_attempt_ms = now_ms
            state.last_error_class = error_class
        else:
            state = RetryState(
                signature=signature,
                tool_name=tool_name,
                attempt_count=1,
                first_attempt_ms=now_ms,
                last_attempt_ms=now_ms,
                last_error_class=error_class,
            )
            self._retry_state[signature] = state

        return state

    def record_success(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Record successful execution (clears retry state)."""
        signature = self._compute_signature(tool_name, arguments)
        self._retry_state.pop(signature, None)

    def get_retry_count(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> int:
        """Get current retry count for a call signature."""
        signature = self._compute_signature(tool_name, arguments)
        state = self._retry_state.get(signature)
        return state.attempt_count if state else 0

    def get_required_backoff_ms(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> int:
        """Get required backoff time before next retry."""
        signature = self._compute_signature(tool_name, arguments)
        state = self._retry_state.get(signature)

        if state is None:
            return 0

        return self._calculate_backoff_ms(state.attempt_count)

    def reset(self) -> None:
        """Reset all retry state."""
        self._retry_state.clear()

    def reset_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Reset retry state for specific call signature."""
        signature = self._compute_signature(tool_name, arguments)
        self._retry_state.pop(signature, None)

    def _check_idempotency_key(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult | None:
        """Check if idempotency key is required and present."""
        if not self.config.require_idempotency_key:
            return None

        # Skip check for known idempotent tools
        if self._is_idempotent_tool(tool_name):
            return None

        # Require key for non-idempotent tools
        if self._is_non_idempotent_tool(tool_name):
            key = arguments.get(self.config.idempotency_key_arg)
            if not key:
                message = f"Idempotency key required for non-idempotent tool '{tool_name}'"
                return self._enforcement_result(message, tool_name, None)

        return None

    def _check_retry_count(self, state: RetryState) -> GuardResult | None:
        """Check if retry count limit is exceeded."""
        if state.attempt_count >= self.config.max_same_signature_retries:
            message = (
                f"Maximum retries exceeded for tool '{state.tool_name}': "
                f"{state.attempt_count} >= {self.config.max_same_signature_retries}"
            )
            return self._enforcement_result(message, state.tool_name, state.last_error_class)

        return None

    def _check_backoff(self, state: RetryState) -> GuardResult | None:
        """Check if backoff time has elapsed."""
        if not self.config.enforce_backoff:
            return None

        now_ms = self._now_ms()
        required_backoff = self._calculate_backoff_ms(state.attempt_count)
        elapsed_since_last = now_ms - state.last_attempt_ms

        if elapsed_since_last < required_backoff:
            remaining_ms = required_backoff - elapsed_since_last
            message = f"Backoff required before retry: {remaining_ms}ms remaining (attempt {state.attempt_count + 1})"
            return self.warn(
                reason=message,
                required_backoff_ms=required_backoff,
                elapsed_ms=elapsed_since_last,
                remaining_ms=remaining_ms,
            )

        return None

    def _calculate_backoff_ms(self, attempt_count: int) -> int:
        """Calculate required backoff time for given attempt count."""
        if attempt_count <= 1:
            return 0

        backoff = self.config.min_backoff_ms * (self.config.backoff_multiplier ** (attempt_count - 1))
        return min(int(backoff), self.config.max_backoff_ms)

    def _is_idempotent_tool(self, tool_name: str) -> bool:
        """Check if tool is known to be idempotent."""
        base_name = tool_name.split(".")[-1].lower()
        return tool_name in self.config.idempotent_tools or base_name in self.config.idempotent_tools

    def _is_non_idempotent_tool(self, tool_name: str) -> bool:
        """Check if tool is known to be non-idempotent."""
        base_name = tool_name.split(".")[-1].lower()
        return tool_name in self.config.non_idempotent_tools or base_name in self.config.non_idempotent_tools

    def _compute_signature(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Compute unique signature for (tool, args) pair."""
        # Exclude idempotency key from signature
        args_copy = {k: v for k, v in arguments.items() if k != self.config.idempotency_key_arg}

        # Create stable hash
        content = f"{tool_name}:{sorted(args_copy.items())}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _enforcement_result(
        self,
        message: str,
        tool_name: str,
        error_class: ErrorClass | None,
    ) -> GuardResult:
        """Create enforcement result based on config."""
        details: dict[str, Any] = {"tool": tool_name}
        if error_class:
            details["error_class"] = error_class.value

        if self.config.enforcement_level == EnforcementLevel.WARN:
            return self.warn(reason=message, **details)

        return self.block(reason=message, **details)

    def _now_ms(self) -> int:
        """Get current time in milliseconds."""
        return int(time.time() * 1000)
