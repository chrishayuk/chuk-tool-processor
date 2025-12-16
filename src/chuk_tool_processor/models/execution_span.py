# chuk_tool_processor/models/execution_span.py
"""
ExecutionSpan: The observable unit of tool execution.

This module provides a complete record of a single tool execution,
capturing everything needed for:
- Debugging and observability
- Deterministic replay
- Training data generation
- Performance profiling
- Guard decision auditing

ExecutionSpan is the bridge between "tool was called" and
"here's exactly what happened, why, and how".
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExecutionOutcome(str, Enum):
    """Outcome of a tool execution attempt."""

    SUCCESS = "success"  # Tool executed and returned result
    BLOCKED = "blocked"  # Guards blocked execution
    FAILED = "failed"  # Tool raised an exception
    TIMEOUT = "timeout"  # Execution exceeded deadline
    SKIPPED = "skipped"  # Skipped due to dependency failure
    REPAIRED = "repaired"  # Executed with repaired arguments


class SandboxType(str, Enum):
    """Type of sandbox used for execution."""

    NONE = "none"  # Direct in-process execution
    THREAD = "thread"  # Thread isolation only
    PROCESS = "process"  # Subprocess isolation
    CONTAINER = "container"  # Container isolation
    MCP = "mcp"  # Remote MCP server


class ExecutionStrategy(str, Enum):
    """Strategy used to execute the tool."""

    INPROCESS = "inprocess"  # InProcessStrategy
    SUBPROCESS = "subprocess"  # SubprocessStrategy
    MCP_STDIO = "mcp_stdio"  # MCP over stdio
    MCP_SSE = "mcp_sse"  # MCP over SSE
    MCP_HTTP = "mcp_http"  # MCP over HTTP
    CODE_SANDBOX = "code_sandbox"  # CodeSandbox execution


class GuardDecision(BaseModel):
    """Record of a single guard's decision."""

    model_config = ConfigDict(frozen=True)

    guard_name: str = Field(..., description="Name/type of the guard")
    guard_class: str = Field(..., description="Fully qualified class name")
    verdict: str = Field(..., description="ALLOW, WARN, BLOCK, or REPAIR")
    reason: str = Field(default="", description="Human-readable reason")
    details: dict[str, Any] = Field(default_factory=dict, description="Guard-specific details")
    duration_ms: float = Field(default=0.0, description="Time spent in this guard")

    # For REPAIR verdicts
    repaired_args: dict[str, Any] | None = Field(
        default=None,
        description="Arguments after repair (if REPAIR verdict)",
    )


class ErrorInfo(BaseModel):
    """Structured error information for failed executions."""

    model_config = ConfigDict(frozen=True)

    error_type: str = Field(..., description="Exception class name")
    message: str = Field(..., description="Error message")
    traceback: str | None = Field(default=None, description="Full traceback if available")
    retryable: bool = Field(default=False, description="Whether this error is retryable")
    error_code: str | None = Field(default=None, description="Structured error code")

    @classmethod
    def from_exception(cls, exc: Exception, include_traceback: bool = True) -> ErrorInfo:
        """Create ErrorInfo from an exception."""
        import traceback as tb

        return cls(
            error_type=type(exc).__name__,
            message=str(exc),
            traceback=tb.format_exc() if include_traceback else None,
            retryable=_is_retryable(exc),
        )


def _is_retryable(exc: Exception) -> bool:
    """Determine if an exception is retryable."""
    # Common retryable exceptions
    retryable_types = (
        TimeoutError,
        ConnectionError,
        OSError,
    )
    retryable_messages = (
        "timeout",
        "connection",
        "temporarily",
        "rate limit",
        "too many requests",
    )

    if isinstance(exc, retryable_types):
        return True

    msg = str(exc).lower()
    return any(pattern in msg for pattern in retryable_messages)


class ExecutionSpan(BaseModel):
    """
    Complete record of a single tool execution for observability and replay.

    This is the fundamental observable unit in chuk-tool-processor.
    Every tool execution produces an ExecutionSpan that captures:

    - What was called (tool, arguments, namespace)
    - What guards decided (and why)
    - How it was executed (sandbox, strategy)
    - What happened (outcome, result, timing)
    - Enough information to replay deterministically

    Example:
        >>> span = ExecutionSpan(
        ...     tool_name="calculator.add",
        ...     namespace="math",
        ...     arguments={"a": 5, "b": 3},
        ...     outcome=ExecutionOutcome.SUCCESS,
        ...     result=8,
        ... )
        >>> print(span.duration_ms)
        12.5
        >>> print(span.guard_decisions)
        [GuardDecision(guard_name="SchemaGuard", verdict="ALLOW")]

    The span can be:
    - Exported to OpenTelemetry
    - Written to a TraceSink for querying
    - Used for deterministic replay
    - Analyzed for performance profiling
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    span_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this execution span",
    )
    parent_span_id: str | None = Field(
        default=None,
        description="Parent span ID (for nested/chained executions)",
    )
    trace_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Trace ID for correlating related spans",
    )
    request_id: str | None = Field(
        default=None,
        description="Request ID from ExecutionContext",
    )

    # ------------------------------------------------------------------ #
    # What was called
    # ------------------------------------------------------------------ #
    tool_name: str = Field(..., description="Name of the tool that was called")
    namespace: str = Field(default="default", description="Namespace the tool belongs to")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Original arguments passed to the tool",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="ID from the original ToolCall",
    )

    # ------------------------------------------------------------------ #
    # Guard decisions (the key observability addition)
    # ------------------------------------------------------------------ #
    guard_decisions: list[GuardDecision] = Field(
        default_factory=list,
        description="Ordered list of guard decisions",
    )
    final_verdict: str = Field(
        default="ALLOW",
        description="Final verdict after all guards (ALLOW, WARN, BLOCK, REPAIR)",
    )
    repaired_arguments: dict[str, Any] | None = Field(
        default=None,
        description="Arguments after repair (if any guard returned REPAIR)",
    )
    effective_arguments: dict[str, Any] | None = Field(
        default=None,
        description="Actual arguments used for execution (repaired or original)",
    )

    # ------------------------------------------------------------------ #
    # Execution details
    # ------------------------------------------------------------------ #
    sandbox_type: SandboxType = Field(
        default=SandboxType.NONE,
        description="Type of sandbox used for isolation",
    )
    execution_strategy: ExecutionStrategy = Field(
        default=ExecutionStrategy.INPROCESS,
        description="Strategy used to execute the tool",
    )
    retry_attempt: int = Field(
        default=0,
        description="Current retry attempt (0 = first attempt)",
    )
    max_retries: int = Field(
        default=0,
        description="Maximum retries configured",
    )
    from_cache: bool = Field(
        default=False,
        description="Whether result was served from cache",
    )
    cache_key: str | None = Field(
        default=None,
        description="Cache key used (if caching enabled)",
    )

    # ------------------------------------------------------------------ #
    # Timing
    # ------------------------------------------------------------------ #
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the span was created",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When execution actually started",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="When execution completed",
    )
    guard_duration_ms: float = Field(
        default=0.0,
        description="Time spent in guard checks (milliseconds)",
    )
    execution_duration_ms: float = Field(
        default=0.0,
        description="Time spent in actual execution (milliseconds)",
    )

    # ------------------------------------------------------------------ #
    # Outcome
    # ------------------------------------------------------------------ #
    outcome: ExecutionOutcome = Field(
        default=ExecutionOutcome.SUCCESS,
        description="Final outcome of the execution",
    )
    result: Any | None = Field(
        default=None,
        description="Result value (if successful)",
    )
    result_type: str | None = Field(
        default=None,
        description="Type name of the result",
    )
    error: ErrorInfo | None = Field(
        default=None,
        description="Error information (if failed)",
    )

    # ------------------------------------------------------------------ #
    # Replay support
    # ------------------------------------------------------------------ #
    input_hash: str | None = Field(
        default=None,
        description="Hash of inputs for replay matching",
    )
    deterministic: bool = Field(
        default=False,
        description="Whether this tool is marked as deterministic/pure",
    )
    random_seed: int | None = Field(
        default=None,
        description="Random seed used (if seeded execution)",
    )

    # ------------------------------------------------------------------ #
    # Resource usage
    # ------------------------------------------------------------------ #
    memory_bytes: int | None = Field(
        default=None,
        description="Peak memory usage in bytes",
    )
    cpu_time_ms: float | None = Field(
        default=None,
        description="CPU time consumed in milliseconds",
    )

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #
    @property
    def duration_ms(self) -> float:
        """Total duration from creation to completion."""
        if self.ended_at is None:
            return 0.0
        return (self.ended_at - self.created_at).total_seconds() * 1000

    @property
    def full_tool_name(self) -> str:
        """Full tool name including namespace."""
        if self.namespace and self.namespace != "default":
            return f"{self.namespace}.{self.tool_name}"
        return self.tool_name

    @property
    def blocked(self) -> bool:
        """Whether execution was blocked by guards."""
        return self.outcome == ExecutionOutcome.BLOCKED

    @property
    def successful(self) -> bool:
        """Whether execution completed successfully."""
        return self.outcome in (ExecutionOutcome.SUCCESS, ExecutionOutcome.REPAIRED)

    @property
    def guard_warnings(self) -> list[GuardDecision]:
        """Guards that returned WARN verdict."""
        return [g for g in self.guard_decisions if g.verdict == "WARN"]

    @property
    def blocking_guard(self) -> GuardDecision | None:
        """The guard that blocked execution (if any)."""
        for g in self.guard_decisions:
            if g.verdict == "BLOCK":
                return g
        return None

    # ------------------------------------------------------------------ #
    # Methods
    # ------------------------------------------------------------------ #
    def compute_input_hash(self) -> str:
        """Compute a stable hash of the inputs for replay matching."""
        payload = {
            "tool": self.tool_name,
            "namespace": self.namespace,
            "arguments": self.effective_arguments or self.arguments,
        }
        json_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode(), usedforsecurity=False).hexdigest()[:16]

    def to_otel_attributes(self) -> dict[str, str | int | float | bool]:
        """Convert to OpenTelemetry span attributes."""
        attrs: dict[str, str | int | float | bool] = {
            "tool.name": self.tool_name,
            "tool.namespace": self.namespace,
            "tool.full_name": self.full_tool_name,
            "execution.outcome": self.outcome.value,
            "execution.sandbox": self.sandbox_type.value,
            "execution.strategy": self.execution_strategy.value,
            "execution.from_cache": self.from_cache,
            "execution.retry_attempt": self.retry_attempt,
            "execution.duration_ms": self.duration_ms,
            "guard.final_verdict": self.final_verdict,
            "guard.count": len(self.guard_decisions),
            "guard.duration_ms": self.guard_duration_ms,
        }

        if self.request_id:
            attrs["request.id"] = self.request_id
        if self.error:
            attrs["error.type"] = self.error.error_type
            attrs["error.message"] = self.error.message
        if self.deterministic:
            attrs["tool.deterministic"] = True
        if self.memory_bytes:
            attrs["resource.memory_bytes"] = self.memory_bytes
        if self.cpu_time_ms:
            attrs["resource.cpu_time_ms"] = self.cpu_time_ms

        return attrs

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for structured logging."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "tool": self.full_tool_name,
            "outcome": self.outcome.value,
            "duration_ms": self.duration_ms,
            "guard_verdict": self.final_verdict,
            "sandbox": self.sandbox_type.value,
            "from_cache": self.from_cache,
            "retry_attempt": self.retry_attempt,
            "error": self.error.message if self.error else None,
        }


class SpanBuilder:
    """
    Builder for constructing ExecutionSpan incrementally during execution.

    This allows the execution pipeline to build up span data as it progresses
    through guards, execution, and result handling.

    Example:
        >>> builder = SpanBuilder(tool_name="calculator.add", arguments={"a": 5, "b": 3})
        >>> builder.add_guard_decision(GuardDecision(...))
        >>> builder.set_started()
        >>> # ... execute tool ...
        >>> builder.set_result(8)
        >>> span = builder.build()
    """

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        namespace: str = "default",
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        request_id: str | None = None,
        tool_call_id: str | None = None,
    ):
        self._span_id = str(uuid4())
        self._trace_id = trace_id or str(uuid4())
        self._parent_span_id = parent_span_id
        self._request_id = request_id
        self._tool_call_id = tool_call_id

        self._tool_name = tool_name
        self._namespace = namespace
        self._arguments = arguments
        self._effective_arguments: dict[str, Any] | None = None
        self._repaired_arguments: dict[str, Any] | None = None

        self._guard_decisions: list[GuardDecision] = []
        self._final_verdict = "ALLOW"
        self._guard_start: datetime | None = None
        self._guard_duration_ms = 0.0

        self._sandbox_type = SandboxType.NONE
        self._execution_strategy = ExecutionStrategy.INPROCESS
        self._retry_attempt = 0
        self._max_retries = 0
        self._from_cache = False
        self._cache_key: str | None = None

        self._created_at = datetime.now(UTC)
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None

        self._outcome = ExecutionOutcome.SUCCESS
        self._result: Any = None
        self._result_type: str | None = None
        self._error: ErrorInfo | None = None

        self._deterministic = False
        self._random_seed: int | None = None
        self._memory_bytes: int | None = None
        self._cpu_time_ms: float | None = None

    @property
    def span_id(self) -> str:
        """Get the span ID."""
        return self._span_id

    @property
    def trace_id(self) -> str:
        """Get the trace ID."""
        return self._trace_id

    def start_guard_phase(self) -> SpanBuilder:
        """Mark the start of guard evaluation."""
        self._guard_start = datetime.now(UTC)
        return self

    def add_guard_decision(self, decision: GuardDecision) -> SpanBuilder:
        """Add a guard decision to the span."""
        self._guard_decisions.append(decision)

        # Track the most restrictive verdict
        if decision.verdict == "BLOCK":
            self._final_verdict = "BLOCK"
        elif decision.verdict == "REPAIR" and self._final_verdict != "BLOCK":
            self._final_verdict = "REPAIR"
            if decision.repaired_args:
                self._repaired_arguments = decision.repaired_args
        elif decision.verdict == "WARN" and self._final_verdict == "ALLOW":
            self._final_verdict = "WARN"

        return self

    def end_guard_phase(self) -> SpanBuilder:
        """Mark the end of guard evaluation."""
        if self._guard_start:
            self._guard_duration_ms = (datetime.now(UTC) - self._guard_start).total_seconds() * 1000
        return self

    def set_effective_arguments(self, args: dict[str, Any]) -> SpanBuilder:
        """Set the actual arguments used for execution."""
        self._effective_arguments = args
        return self

    def set_sandbox(self, sandbox_type: SandboxType) -> SpanBuilder:
        """Set the sandbox type used."""
        self._sandbox_type = sandbox_type
        return self

    def set_strategy(self, strategy: ExecutionStrategy) -> SpanBuilder:
        """Set the execution strategy used."""
        self._execution_strategy = strategy
        return self

    def set_retry_info(self, attempt: int, max_retries: int) -> SpanBuilder:
        """Set retry information."""
        self._retry_attempt = attempt
        self._max_retries = max_retries
        return self

    def set_cache_hit(self, cache_key: str) -> SpanBuilder:
        """Mark this as a cache hit."""
        self._from_cache = True
        self._cache_key = cache_key
        return self

    def set_started(self) -> SpanBuilder:
        """Mark execution as started."""
        self._started_at = datetime.now(UTC)
        return self

    def set_result(self, result: Any) -> SpanBuilder:
        """Set successful result."""
        self._ended_at = datetime.now(UTC)
        self._outcome = ExecutionOutcome.REPAIRED if self._repaired_arguments else ExecutionOutcome.SUCCESS
        self._result = result
        self._result_type = type(result).__name__ if result is not None else None
        return self

    def set_blocked(self) -> SpanBuilder:
        """Mark execution as blocked by guards."""
        self._ended_at = datetime.now(UTC)
        self._outcome = ExecutionOutcome.BLOCKED
        return self

    def set_error(self, error: Exception | ErrorInfo) -> SpanBuilder:
        """Set error information."""
        self._ended_at = datetime.now(UTC)
        self._outcome = ExecutionOutcome.FAILED

        if isinstance(error, ErrorInfo):
            self._error = error
        else:
            self._error = ErrorInfo.from_exception(error)

        return self

    def set_timeout(self) -> SpanBuilder:
        """Mark execution as timed out."""
        self._ended_at = datetime.now(UTC)
        self._outcome = ExecutionOutcome.TIMEOUT
        return self

    def set_skipped(self, reason: str = "") -> SpanBuilder:
        """Mark execution as skipped."""
        self._ended_at = datetime.now(UTC)
        self._outcome = ExecutionOutcome.SKIPPED
        if reason:
            self._error = ErrorInfo(error_type="SkipError", message=reason)
        return self

    def set_deterministic(self, deterministic: bool, seed: int | None = None) -> SpanBuilder:
        """Set determinism information."""
        self._deterministic = deterministic
        self._random_seed = seed
        return self

    def set_resource_usage(
        self,
        memory_bytes: int | None = None,
        cpu_time_ms: float | None = None,
    ) -> SpanBuilder:
        """Set resource usage metrics."""
        self._memory_bytes = memory_bytes
        self._cpu_time_ms = cpu_time_ms
        return self

    def build(self) -> ExecutionSpan:
        """Build the final ExecutionSpan."""
        # Ensure we have an end time
        if self._ended_at is None:
            self._ended_at = datetime.now(UTC)

        # Calculate execution duration (excluding guard time)
        execution_duration_ms = 0.0
        if self._started_at and self._ended_at:
            execution_duration_ms = (self._ended_at - self._started_at).total_seconds() * 1000

        span = ExecutionSpan(
            span_id=self._span_id,
            parent_span_id=self._parent_span_id,
            trace_id=self._trace_id,
            request_id=self._request_id,
            tool_name=self._tool_name,
            namespace=self._namespace,
            arguments=self._arguments,
            tool_call_id=self._tool_call_id,
            guard_decisions=self._guard_decisions,
            final_verdict=self._final_verdict,
            repaired_arguments=self._repaired_arguments,
            effective_arguments=self._effective_arguments or self._arguments,
            sandbox_type=self._sandbox_type,
            execution_strategy=self._execution_strategy,
            retry_attempt=self._retry_attempt,
            max_retries=self._max_retries,
            from_cache=self._from_cache,
            cache_key=self._cache_key,
            created_at=self._created_at,
            started_at=self._started_at,
            ended_at=self._ended_at,
            guard_duration_ms=self._guard_duration_ms,
            execution_duration_ms=execution_duration_ms,
            outcome=self._outcome,
            result=self._result,
            result_type=self._result_type,
            error=self._error,
            deterministic=self._deterministic,
            random_seed=self._random_seed,
            memory_bytes=self._memory_bytes,
            cpu_time_ms=self._cpu_time_ms,
        )

        # Compute input hash
        return span.model_copy(update={"input_hash": span.compute_input_hash()})
