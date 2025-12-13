# chuk_tool_processor/mcp/middleware.py
"""
Middleware integration for StreamManager.

Async-native, Pydantic-based middleware configuration for:
- Retry with exponential backoff
- Circuit breaker pattern
- Rate limiting
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from chuk_tool_processor.execution.wrappers.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerExecutor,
)
from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimitedToolExecutor,
    RateLimiter,
)
from chuk_tool_processor.execution.wrappers.retry import (
    RetryableToolExecutor,
    RetryConfig,
)
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

if TYPE_CHECKING:
    from chuk_tool_processor.mcp.stream_manager import StreamManager

logger = get_logger("chuk_tool_processor.mcp.middleware")


# ============================================================================
# Enums
# ============================================================================


class MiddlewareLayer(str, Enum):
    """Middleware layer identifiers."""

    RETRY = "retry"
    CIRCUIT_BREAKER = "circuit_breaker"
    RATE_LIMITING = "rate_limiting"


class RetryableError(str, Enum):
    """Error patterns that should trigger retry."""

    TRANSPORT_NOT_INITIALIZED = "Transport not initialized"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    RESET = "reset"
    CLOSED = "closed"


class NonRetryableError(str, Enum):
    """Error patterns that should NOT be retried."""

    OAUTH = "oauth"
    UNAUTHORIZED = "unauthorized"
    AUTHENTICATION = "authentication"
    INVALID_GRANT = "invalid_grant"
    NO_SERVER_FOUND = "No server found"


# ============================================================================
# Constants
# ============================================================================


class RetryDefaults:
    """Default values for retry configuration."""

    ENABLED: bool = True
    MAX_RETRIES: int = 3
    BASE_DELAY: float = 1.0
    MAX_DELAY: float = 30.0
    JITTER: bool = True


class CircuitBreakerDefaults:
    """Default values for circuit breaker configuration."""

    ENABLED: bool = True
    FAILURE_THRESHOLD: int = 5
    SUCCESS_THRESHOLD: int = 2
    RESET_TIMEOUT: float = 60.0
    HALF_OPEN_MAX_CALLS: int = 1


class RateLimitingDefaults:
    """Default values for rate limiting configuration."""

    ENABLED: bool = False
    GLOBAL_LIMIT: int = 100
    PERIOD: float = 60.0


# ============================================================================
# Pydantic Configuration Models
# ============================================================================


class RetrySettings(BaseModel):
    """Retry middleware settings."""

    enabled: bool = Field(default=RetryDefaults.ENABLED)
    max_retries: int = Field(default=RetryDefaults.MAX_RETRIES, ge=0)
    base_delay: float = Field(default=RetryDefaults.BASE_DELAY, gt=0)
    max_delay: float = Field(default=RetryDefaults.MAX_DELAY, gt=0)
    jitter: bool = Field(default=RetryDefaults.JITTER)
    retry_on_errors: list[str] = Field(default_factory=lambda: [e.value for e in RetryableError])
    skip_on_errors: list[str] = Field(default_factory=lambda: [e.value for e in NonRetryableError])

    model_config = {"frozen": True}


class CircuitBreakerSettings(BaseModel):
    """Circuit breaker middleware settings."""

    enabled: bool = Field(default=CircuitBreakerDefaults.ENABLED)
    failure_threshold: int = Field(default=CircuitBreakerDefaults.FAILURE_THRESHOLD, ge=1)
    success_threshold: int = Field(default=CircuitBreakerDefaults.SUCCESS_THRESHOLD, ge=1)
    reset_timeout: float = Field(default=CircuitBreakerDefaults.RESET_TIMEOUT, gt=0)
    half_open_max_calls: int = Field(default=CircuitBreakerDefaults.HALF_OPEN_MAX_CALLS, ge=1)

    model_config = {"frozen": True}


class RateLimitSettings(BaseModel):
    """Rate limiting middleware settings."""

    enabled: bool = Field(default=RateLimitingDefaults.ENABLED)
    global_limit: int | None = Field(default=RateLimitingDefaults.GLOBAL_LIMIT, ge=1)
    period: float = Field(default=RateLimitingDefaults.PERIOD, gt=0)
    per_tool_limits: dict[str, tuple[int, float]] = Field(default_factory=dict)

    model_config = {"frozen": True}


class MiddlewareConfig(BaseModel):
    """Complete middleware configuration.

    Example:
        config = MiddlewareConfig(
            retry=RetrySettings(max_retries=5),
            circuit_breaker=CircuitBreakerSettings(failure_threshold=3),
        )
    """

    retry: RetrySettings = Field(default_factory=RetrySettings)
    circuit_breaker: CircuitBreakerSettings = Field(default_factory=CircuitBreakerSettings)
    rate_limiting: RateLimitSettings = Field(default_factory=RateLimitSettings)

    model_config = {"frozen": True}


# ============================================================================
# Status Models (for diagnostics)
# ============================================================================


class RetryStatus(BaseModel):
    """Retry middleware status."""

    enabled: bool
    max_retries: int
    base_delay: float
    max_delay: float


class CircuitBreakerToolState(BaseModel):
    """State of a circuit breaker for a specific tool."""

    state: str
    failure_count: int
    success_count: int
    time_until_half_open: float | None = None


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker middleware status."""

    enabled: bool
    failure_threshold: int
    reset_timeout: float
    tool_states: dict[str, CircuitBreakerToolState] = Field(default_factory=dict)


class RateLimitStatus(BaseModel):
    """Rate limiting middleware status."""

    enabled: bool
    global_limit: int | None
    period: float


class MiddlewareStatus(BaseModel):
    """Complete middleware status for diagnostics."""

    retry: RetryStatus | None = None
    circuit_breaker: CircuitBreakerStatus | None = None
    rate_limiting: RateLimitStatus | None = None


# ============================================================================
# Tool Execution Result Model
# ============================================================================


class ToolExecutionResult(BaseModel):
    """Result of a tool execution through middleware."""

    success: bool
    result: Any = None
    error: str | None = None
    tool_name: str
    duration_ms: float
    attempts: int = 1
    from_cache: bool = False

    model_config = {"arbitrary_types_allowed": True}


# ============================================================================
# StreamManager Executor Adapter
# ============================================================================


class StreamManagerExecutor:
    """
    Async-native adapter that makes StreamManager work with middleware wrappers.

    Converts StreamManager's call_tool(tool_name, arguments) interface
    to the execute(list[ToolCall]) -> list[ToolResult] interface.
    """

    __slots__ = ("_stream_manager",)

    def __init__(self, stream_manager: StreamManager) -> None:
        self._stream_manager = stream_manager

    async def execute(
        self,
        calls: list[ToolCall],
        *,
        timeout: float | None = None,
        use_cache: bool = True,  # noqa: ARG002
    ) -> list[ToolResult]:
        """Execute tool calls via StreamManager."""
        results: list[ToolResult] = []

        for call in calls:
            start_time = datetime.now(UTC)
            tool_name = call.tool
            arguments = call.arguments or {}

            try:
                raw_result = await self._stream_manager._direct_call_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    timeout=timeout,
                )

                end_time = datetime.now(UTC)

                if isinstance(raw_result, dict) and raw_result.get("isError"):
                    result = ToolResult(
                        tool=tool_name,
                        result=None,
                        error=raw_result.get("error", "Unknown error"),
                        start_time=start_time,
                        end_time=end_time,
                        machine="stream_manager",
                        pid=0,
                    )
                else:
                    result = ToolResult(
                        tool=tool_name,
                        result=raw_result,
                        error=None,
                        start_time=start_time,
                        end_time=end_time,
                        machine="stream_manager",
                        pid=0,
                    )
                results.append(result)

            except Exception as e:
                end_time = datetime.now(UTC)
                results.append(
                    ToolResult(
                        tool=tool_name,
                        result=None,
                        error=str(e),
                        start_time=start_time,
                        end_time=end_time,
                        machine="stream_manager",
                        pid=0,
                    )
                )

        return results


# ============================================================================
# Middleware Stack
# ============================================================================


class MiddlewareStack:
    """
    Async-native middleware stack for tool execution.

    Wraps a StreamManager with retry, circuit breaker, and rate limiting.
    Order: rate_limit -> circuit_breaker -> retry -> transport
    """

    __slots__ = ("_config", "_base_executor", "_executor", "_circuit_breaker_executor")

    def __init__(
        self,
        stream_manager: StreamManager,
        config: MiddlewareConfig | None = None,
    ) -> None:
        self._config = config or MiddlewareConfig()
        self._base_executor = StreamManagerExecutor(stream_manager)
        self._executor: Any = None
        self._circuit_breaker_executor: CircuitBreakerExecutor | None = None
        self._build_stack()

    def _build_stack(self) -> None:
        """Build the middleware stack."""
        executor = self._base_executor

        # Layer 1: Retry (innermost)
        if self._config.retry.enabled:
            retry_config = RetryConfig(
                max_retries=self._config.retry.max_retries,
                base_delay=self._config.retry.base_delay,
                max_delay=self._config.retry.max_delay,
                jitter=self._config.retry.jitter,
                retry_on_error_substrings=self._config.retry.retry_on_errors,
                skip_retry_on_error_substrings=self._config.retry.skip_on_errors,
            )
            executor = RetryableToolExecutor(executor, default_config=retry_config)
            logger.debug("Retry enabled: max_retries=%d", self._config.retry.max_retries)

        # Layer 2: Circuit Breaker
        if self._config.circuit_breaker.enabled:
            cb_config = CircuitBreakerConfig(
                failure_threshold=self._config.circuit_breaker.failure_threshold,
                success_threshold=self._config.circuit_breaker.success_threshold,
                reset_timeout=self._config.circuit_breaker.reset_timeout,
                half_open_max_calls=self._config.circuit_breaker.half_open_max_calls,
            )
            self._circuit_breaker_executor = CircuitBreakerExecutor(executor, default_config=cb_config)
            executor = self._circuit_breaker_executor
            logger.debug(
                "Circuit breaker enabled: failure_threshold=%d",
                self._config.circuit_breaker.failure_threshold,
            )

        # Layer 3: Rate Limiting (outermost)
        if self._config.rate_limiting.enabled:
            rate_limiter = RateLimiter(
                global_limit=self._config.rate_limiting.global_limit,
                global_period=self._config.rate_limiting.period,
                tool_limits=self._config.rate_limiting.per_tool_limits,
            )
            executor = RateLimitedToolExecutor(executor, limiter=rate_limiter)
            logger.debug(
                "Rate limiting enabled: global=%s/%ss",
                self._config.rate_limiting.global_limit,
                self._config.rate_limiting.period,
            )

        self._executor = executor

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float | None = None,
    ) -> ToolExecutionResult:
        """Execute a tool call through the middleware stack."""
        start = datetime.now(UTC)
        call = ToolCall(tool=tool_name, arguments=arguments)

        try:
            results = await self._executor.execute([call], timeout=timeout)
            result = results[0] if results else None

            end = datetime.now(UTC)
            duration_ms = (end - start).total_seconds() * 1000

            if result is None:
                return ToolExecutionResult(
                    success=False,
                    error="No result returned",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                )

            if result.error:
                return ToolExecutionResult(
                    success=False,
                    error=result.error,
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    attempts=getattr(result, "attempts", 1),
                )

            return ToolExecutionResult(
                success=True,
                result=result.result,
                tool_name=tool_name,
                duration_ms=duration_ms,
                attempts=getattr(result, "attempts", 1),
                from_cache=getattr(result, "cached", False),
            )

        except Exception as e:
            end = datetime.now(UTC)
            duration_ms = (end - start).total_seconds() * 1000
            logger.error("Middleware stack error for %s: %s", tool_name, e)
            return ToolExecutionResult(
                success=False,
                error=str(e),
                tool_name=tool_name,
                duration_ms=duration_ms,
            )

    def get_status(self) -> MiddlewareStatus:
        """Get middleware status for diagnostics."""
        retry_status = None
        if self._config.retry.enabled:
            retry_status = RetryStatus(
                enabled=True,
                max_retries=self._config.retry.max_retries,
                base_delay=self._config.retry.base_delay,
                max_delay=self._config.retry.max_delay,
            )

        cb_status = None
        if self._config.circuit_breaker.enabled:
            tool_states: dict[str, CircuitBreakerToolState] = {}
            if self._circuit_breaker_executor and hasattr(self._circuit_breaker_executor, "_states"):
                for tool, state in self._circuit_breaker_executor._states.items():
                    state_dict = state.get_state()
                    tool_states[tool] = CircuitBreakerToolState(
                        state=state_dict["state"],
                        failure_count=state_dict["failure_count"],
                        success_count=state_dict["success_count"],
                        time_until_half_open=state_dict.get("time_until_half_open"),
                    )
            cb_status = CircuitBreakerStatus(
                enabled=True,
                failure_threshold=self._config.circuit_breaker.failure_threshold,
                reset_timeout=self._config.circuit_breaker.reset_timeout,
                tool_states=tool_states,
            )

        rl_status = None
        if self._config.rate_limiting.enabled:
            rl_status = RateLimitStatus(
                enabled=True,
                global_limit=self._config.rate_limiting.global_limit,
                period=self._config.rate_limiting.period,
            )

        return MiddlewareStatus(
            retry=retry_status,
            circuit_breaker=cb_status,
            rate_limiting=rl_status,
        )

    @property
    def config(self) -> MiddlewareConfig:
        """Get the middleware configuration."""
        return self._config
