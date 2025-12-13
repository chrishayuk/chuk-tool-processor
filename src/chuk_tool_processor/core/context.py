# chuk_tool_processor/core/context.py
"""
First-class ExecutionContext for request-scoped data propagation.

This module provides a unified context object that flows through the entire
tool execution pipeline, carrying:
- Request identification (request_id, correlation_id)
- User/tenant information (user_id, tenant_id)
- Resource constraints (deadline, budget)
- Tracing data (traceparent, span_id)
- Custom metadata

The context integrates with:
- Logging (automatic injection into log records)
- Metrics (automatic tagging)
- Tracing (span attributes)
- MCP headers (propagation to remote tools)
"""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContextHeader(str, Enum):
    """Standard HTTP headers for context propagation."""

    REQUEST_ID = "X-Request-ID"
    CORRELATION_ID = "X-Correlation-ID"
    USER_ID = "X-User-ID"
    TENANT_ID = "X-Tenant-ID"
    TRACEPARENT = "traceparent"
    TRACESTATE = "tracestate"
    DEADLINE_SECONDS = "X-Deadline-Seconds"
    BUDGET = "X-Budget"


class ContextKey(str, Enum):
    """Standard keys for context dictionary representation."""

    REQUEST_ID = "request_id"
    CORRELATION_ID = "correlation_id"
    USER_ID = "user_id"
    TENANT_ID = "tenant_id"
    TRACEPARENT = "traceparent"
    TRACESTATE = "tracestate"
    SPAN_ID = "span_id"
    DEADLINE = "deadline"
    REMAINING_TIME = "remaining_time"
    BUDGET = "budget"
    METADATA = "metadata"


class ExecutionContext(BaseModel):
    """
    Immutable context object for request-scoped execution data.

    This context flows through the entire tool execution pipeline and
    provides consistent access to request metadata, user info, and
    resource constraints.

    Examples:
        Basic usage:

        >>> ctx = ExecutionContext(
        ...     request_id="req-123",
        ...     user_id="user-456",
        ...     tenant_id="tenant-789",
        ... )
        >>> async with ToolProcessor() as processor:
        ...     results = await processor.process(data, context=ctx)

        With deadline:

        >>> ctx = ExecutionContext.with_deadline(seconds=30)
        >>> # Context will track remaining time budget

        With tracing:

        >>> ctx = ExecutionContext(
        ...     traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        ...     span_id="b7ad6b7169203331",
        ... )

    Attributes:
        request_id: Unique identifier for this request/execution
        correlation_id: ID for correlating related requests across services
        user_id: Identifier of the user making the request
        tenant_id: Identifier of the tenant/organization
        traceparent: W3C Trace Context traceparent header
        tracestate: W3C Trace Context tracestate header
        span_id: Current span ID for distributed tracing
        deadline: Absolute deadline for execution completion
        budget: Remaining budget/quota for this request
        metadata: Additional custom key-value pairs
    """

    model_config = ConfigDict(
        frozen=True,  # Immutable
        extra="forbid",  # No unknown fields
        validate_default=True,
    )

    # Request identification
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this request/execution",
    )
    correlation_id: str | None = Field(
        default=None,
        description="ID for correlating related requests across services",
    )

    # User/tenant information
    user_id: str | None = Field(
        default=None,
        description="Identifier of the user making the request",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Identifier of the tenant/organization",
    )

    # Distributed tracing (W3C Trace Context)
    traceparent: str | None = Field(
        default=None,
        description="W3C Trace Context traceparent header",
    )
    tracestate: str | None = Field(
        default=None,
        description="W3C Trace Context tracestate header",
    )
    span_id: str | None = Field(
        default=None,
        description="Current span ID for distributed tracing",
    )

    # Resource constraints
    deadline: datetime | None = Field(
        default=None,
        description="Absolute deadline for execution completion",
    )
    budget: float | None = Field(
        default=None,
        ge=0,
        description="Remaining budget/quota for this request (abstract units)",
    )

    # Custom metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom key-value pairs",
    )

    # Internal: creation time for duration tracking
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Context creation timestamp",
    )

    @field_validator("traceparent")
    @classmethod
    def validate_traceparent(cls, v: str | None) -> str | None:
        """Validate W3C traceparent format if provided."""
        if v is None:
            return None
        # Basic format check: version-traceid-parentid-flags
        parts = v.split("-")
        if len(parts) != 4:
            raise ValueError("traceparent must have format: version-traceid-parentid-flags")
        return v

    @classmethod
    def with_deadline(
        cls,
        seconds: float,
        **kwargs: Any,
    ) -> ExecutionContext:
        """
        Create a context with a deadline set from now.

        Args:
            seconds: Number of seconds until deadline
            **kwargs: Additional context fields

        Returns:
            ExecutionContext with deadline set

        Example:
            >>> ctx = ExecutionContext.with_deadline(30, user_id="user-123")
            >>> ctx.remaining_time  # ~30.0
        """
        deadline = datetime.now(UTC) + timedelta(seconds=seconds)
        return cls(deadline=deadline, **kwargs)

    @classmethod
    def with_timeout(
        cls,
        timeout: float,
        **kwargs: Any,
    ) -> ExecutionContext:
        """Alias for with_deadline() for semantic clarity."""
        return cls.with_deadline(timeout, **kwargs)

    @classmethod
    def from_headers(cls, headers: dict[str, str], **kwargs: Any) -> ExecutionContext:
        """
        Create a context from HTTP headers.

        Args:
            headers: HTTP headers dictionary
            **kwargs: Additional context fields (override headers)

        Returns:
            ExecutionContext populated from headers
        """
        ctx_kwargs: dict[str, Any] = {}

        if ContextHeader.REQUEST_ID.value in headers:
            ctx_kwargs["request_id"] = headers[ContextHeader.REQUEST_ID.value]
        if ContextHeader.CORRELATION_ID.value in headers:
            ctx_kwargs["correlation_id"] = headers[ContextHeader.CORRELATION_ID.value]
        if ContextHeader.USER_ID.value in headers:
            ctx_kwargs["user_id"] = headers[ContextHeader.USER_ID.value]
        if ContextHeader.TENANT_ID.value in headers:
            ctx_kwargs["tenant_id"] = headers[ContextHeader.TENANT_ID.value]
        if ContextHeader.TRACEPARENT.value in headers:
            ctx_kwargs["traceparent"] = headers[ContextHeader.TRACEPARENT.value]
        if ContextHeader.TRACESTATE.value in headers:
            ctx_kwargs["tracestate"] = headers[ContextHeader.TRACESTATE.value]
        if ContextHeader.DEADLINE_SECONDS.value in headers:
            with contextlib.suppress(ValueError):
                seconds = float(headers[ContextHeader.DEADLINE_SECONDS.value])
                ctx_kwargs["deadline"] = datetime.now(UTC) + timedelta(seconds=seconds)
        if ContextHeader.BUDGET.value in headers:
            with contextlib.suppress(ValueError):
                ctx_kwargs["budget"] = float(headers[ContextHeader.BUDGET.value])

        # Override with explicit kwargs
        ctx_kwargs.update(kwargs)

        return cls(**ctx_kwargs)

    @property
    def remaining_time(self) -> float | None:
        """
        Get remaining time until deadline in seconds.

        Returns:
            Seconds remaining, or None if no deadline set.
            Returns 0.0 if deadline has passed.
        """
        if self.deadline is None:
            return None
        remaining = (self.deadline - datetime.now(UTC)).total_seconds()
        return max(0.0, remaining)

    @property
    def is_expired(self) -> bool:
        """Check if the deadline has passed."""
        if self.deadline is None:
            return False
        return datetime.now(UTC) >= self.deadline

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since context creation in seconds."""
        return (datetime.now(UTC) - self.created_at).total_seconds()

    def with_span(self, span_id: str) -> Self:
        """
        Create a child context with a new span ID.

        Args:
            span_id: New span ID for the child context

        Returns:
            New ExecutionContext with updated span_id
        """
        return self.model_copy(update={"span_id": span_id})

    def with_metadata(self, **kwargs: Any) -> Self:
        """
        Create a new context with additional metadata.

        Args:
            **kwargs: Metadata key-value pairs to add

        Returns:
            New ExecutionContext with merged metadata
        """
        new_metadata = {**self.metadata, **kwargs}
        return self.model_copy(update={"metadata": new_metadata})

    def with_budget(self, budget: float) -> Self:
        """
        Create a new context with updated budget.

        Args:
            budget: New budget value

        Returns:
            New ExecutionContext with updated budget
        """
        return self.model_copy(update={"budget": budget})

    def to_dict(self) -> dict[str, Any]:
        """
        Convert context to dictionary for logging/tracing.

        Returns:
            Dictionary with all non-None context values using ContextKey enums
        """
        result: dict[str, Any] = {ContextKey.REQUEST_ID.value: self.request_id}

        if self.correlation_id:
            result[ContextKey.CORRELATION_ID.value] = self.correlation_id
        if self.user_id:
            result[ContextKey.USER_ID.value] = self.user_id
        if self.tenant_id:
            result[ContextKey.TENANT_ID.value] = self.tenant_id
        if self.traceparent:
            result[ContextKey.TRACEPARENT.value] = self.traceparent
        if self.tracestate:
            result[ContextKey.TRACESTATE.value] = self.tracestate
        if self.span_id:
            result[ContextKey.SPAN_ID.value] = self.span_id
        if self.deadline:
            result[ContextKey.DEADLINE.value] = self.deadline.isoformat()
            result[ContextKey.REMAINING_TIME.value] = self.remaining_time
        if self.budget is not None:
            result[ContextKey.BUDGET.value] = self.budget
        if self.metadata:
            result[ContextKey.METADATA.value] = self.metadata

        return result

    def to_headers(self) -> dict[str, str]:
        """
        Convert context to HTTP headers for MCP propagation.

        Returns:
            Dictionary of header name -> value pairs using ContextHeader enums
        """
        headers: dict[str, str] = {
            ContextHeader.REQUEST_ID.value: self.request_id,
        }

        if self.correlation_id:
            headers[ContextHeader.CORRELATION_ID.value] = self.correlation_id
        if self.user_id:
            headers[ContextHeader.USER_ID.value] = self.user_id
        if self.tenant_id:
            headers[ContextHeader.TENANT_ID.value] = self.tenant_id
        if self.traceparent:
            headers[ContextHeader.TRACEPARENT.value] = self.traceparent
        if self.tracestate:
            headers[ContextHeader.TRACESTATE.value] = self.tracestate
        if self.deadline:
            remaining = self.remaining_time
            if remaining is not None:
                headers[ContextHeader.DEADLINE_SECONDS.value] = str(int(remaining))
        if self.budget is not None:
            headers[ContextHeader.BUDGET.value] = str(self.budget)

        return headers


# --------------------------------------------------------------------------- #
# Context variable for async-safe context propagation
# --------------------------------------------------------------------------- #

_execution_context: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar(
    "execution_context",
    default=None,
)


def get_current_context() -> ExecutionContext | None:
    """
    Get the current execution context for this async task.

    Returns:
        Current ExecutionContext or None if not set
    """
    return _execution_context.get()


def set_current_context(ctx: ExecutionContext | None) -> contextvars.Token[ExecutionContext | None]:
    """
    Set the current execution context.

    Args:
        ctx: Context to set, or None to clear

    Returns:
        Token that can be used to restore previous context
    """
    return _execution_context.set(ctx)


class execution_scope:
    """
    Context manager for scoped execution context.

    Example:
        >>> ctx = ExecutionContext(user_id="user-123")
        >>> async with execution_scope(ctx):
        ...     # Context is available via get_current_context()
        ...     current = get_current_context()
        ...     assert current.user_id == "user-123"
    """

    def __init__(self, ctx: ExecutionContext):
        self.ctx = ctx
        self._token: contextvars.Token[ExecutionContext | None] | None = None

    async def __aenter__(self) -> ExecutionContext:
        self._token = set_current_context(self.ctx)
        return self.ctx

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _execution_context.reset(self._token)

    def __enter__(self) -> ExecutionContext:
        self._token = set_current_context(self.ctx)
        return self.ctx

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _execution_context.reset(self._token)
