# chuk_tool_processor/execution/wrappers/circuit_breaker.py
"""
Circuit breaker pattern for tool execution.

Prevents cascading failures by tracking failure rates and temporarily
blocking calls to failing tools. Implements a state machine:

CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN)

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests blocked immediately
- HALF_OPEN: Testing if service recovered, limited requests allowed
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from chuk_tool_processor.core.exceptions import ToolCircuitOpenError
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = get_logger("chuk_tool_processor.execution.wrappers.circuit_breaker")

# Optional observability imports
try:
    from chuk_tool_processor.observability.metrics import get_metrics
    from chuk_tool_processor.observability.tracing import trace_circuit_breaker

    _observability_available = True
except ImportError:
    _observability_available = False

    # No-op functions when observability not available
    def get_metrics():
        return None

    def trace_circuit_breaker(*_args, **_kwargs):
        from contextlib import nullcontext

        return nullcontext()


# --------------------------------------------------------------------------- #
# Circuit breaker state
# --------------------------------------------------------------------------- #
class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests due to failures
    HALF_OPEN = "half_open"  # Testing recovery with limited requests


class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        timeout_threshold: float | None = None,
    ):
        """
        Initialize circuit breaker configuration.

        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes in HALF_OPEN to close circuit
            reset_timeout: Seconds to wait before trying HALF_OPEN
            half_open_max_calls: Max concurrent calls in HALF_OPEN state
            timeout_threshold: Optional timeout (s) to consider as failure
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        self.timeout_threshold = timeout_threshold


class CircuitBreakerState:
    """Per-tool circuit breaker state tracking."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.opened_at: float | None = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.debug(f"Circuit HALF_OPEN: success {self.success_count}/{self.config.success_threshold}")

                # Enough successes? Close the circuit
                if self.success_count >= self.config.success_threshold:
                    logger.info("Circuit breaker: Transitioning to CLOSED (service recovered)")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.opened_at = None
                    self.half_open_calls = 0
            else:
                # In CLOSED state, just reset failure count
                self.failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            logger.debug(f"Circuit: failure {self.failure_count}/{self.config.failure_threshold}")

            if self.state == CircuitState.CLOSED:
                # Check if we should open
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning(f"Circuit breaker: OPENING after {self.failure_count} failures")
                    self.state = CircuitState.OPEN
                    self.opened_at = time.monotonic()
            elif self.state == CircuitState.HALF_OPEN:
                # Failed during test → back to OPEN
                logger.warning("Circuit breaker: Back to OPEN (test failed)")
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.opened_at = time.monotonic()
                self.half_open_calls = 0

    async def can_execute(self) -> bool:
        """Check if a call should be allowed through."""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.HALF_OPEN:
                # Limit concurrent calls in HALF_OPEN
                if self.half_open_calls < self.config.half_open_max_calls:
                    self.half_open_calls += 1
                    return True
                return False

            # OPEN state: check if we should try HALF_OPEN
            if self.opened_at is not None:
                elapsed = time.monotonic() - self.opened_at
                if elapsed >= self.config.reset_timeout:
                    logger.info("Circuit breaker: Transitioning to HALF_OPEN (testing recovery)")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 1
                    self.success_count = 0
                    return True

            return False

    async def release_half_open_slot(self) -> None:
        """Release a HALF_OPEN slot after call completes."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls = max(0, self.half_open_calls - 1)

    def get_state(self) -> dict[str, Any]:
        """Get current state as dict."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "opened_at": self.opened_at,
            "time_until_half_open": (
                max(0, self.config.reset_timeout - (time.monotonic() - self.opened_at))
                if self.opened_at and self.state == CircuitState.OPEN
                else None
            ),
        }


# --------------------------------------------------------------------------- #
# Circuit breaker executor wrapper
# --------------------------------------------------------------------------- #
class CircuitBreakerExecutor:
    """
    Executor wrapper that implements circuit breaker pattern.

    Tracks failures per tool and opens circuit breakers to prevent
    cascading failures when tools are consistently failing.
    """

    def __init__(
        self,
        executor: Any,
        *,
        default_config: CircuitBreakerConfig | None = None,
        tool_configs: dict[str, CircuitBreakerConfig] | None = None,
    ):
        """
        Initialize circuit breaker executor.

        Args:
            executor: Underlying executor to wrap
            default_config: Default circuit breaker configuration
            tool_configs: Per-tool circuit breaker configurations
        """
        self.executor = executor
        self.default_config = default_config or CircuitBreakerConfig()
        self.tool_configs = tool_configs or {}
        self._states: dict[str, CircuitBreakerState] = {}
        self._states_lock = asyncio.Lock()

    async def _get_state(self, tool: str) -> CircuitBreakerState:
        """Get or create circuit breaker state for a tool."""
        if tool not in self._states:
            async with self._states_lock:
                if tool not in self._states:
                    config = self.tool_configs.get(tool, self.default_config)
                    self._states[tool] = CircuitBreakerState(config)
        return self._states[tool]

    async def execute(
        self,
        calls: list[ToolCall],
        *,
        timeout: float | None = None,
        use_cache: bool = True,
    ) -> list[ToolResult]:
        """
        Execute tool calls with circuit breaker protection.

        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results

        Returns:
            List of tool results
        """
        if not calls:
            return []

        results: list[ToolResult] = []

        for call in calls:
            state = await self._get_state(call.tool)

            # Record circuit breaker state
            metrics = get_metrics()
            if metrics:
                metrics.record_circuit_breaker_state(call.tool, state.state.value)

            # Check if circuit allows execution with tracing
            with trace_circuit_breaker(call.tool, state.state.value):
                can_execute = await state.can_execute()

            if not can_execute:
                # Circuit is OPEN - reject immediately
                state_info = state.get_state()
                logger.warning(f"Circuit breaker OPEN for {call.tool} (failures: {state.failure_count})")

                reset_time = state_info.get("time_until_half_open")
                error = ToolCircuitOpenError(
                    tool_name=call.tool,
                    failure_count=state.failure_count,
                    reset_timeout=reset_time,
                )

                now = datetime.now(UTC)
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result=None,
                        error=str(error),
                        start_time=now,
                        end_time=now,
                        machine="circuit_breaker",
                        pid=0,
                    )
                )
                continue

            # Execute the call
            start_time = time.monotonic()
            try:
                # Execute single call
                executor_kwargs = {"timeout": timeout}
                if hasattr(self.executor, "use_cache"):
                    executor_kwargs["use_cache"] = use_cache

                result_list = await self.executor.execute([call], **executor_kwargs)
                result = result_list[0]

                # Check if successful
                duration = time.monotonic() - start_time

                # Determine success/failure
                is_timeout = state.config.timeout_threshold is not None and duration > state.config.timeout_threshold
                is_error = result.error is not None

                if is_error or is_timeout:
                    await state.record_failure()
                    # Record circuit breaker failure metric
                    if metrics:
                        metrics.record_circuit_breaker_failure(call.tool)
                else:
                    await state.record_success()

                results.append(result)

            except Exception as e:
                # Exception during execution
                await state.record_failure()

                now = datetime.now(UTC)
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result=None,
                        error=f"Circuit breaker caught exception: {str(e)}",
                        start_time=now,
                        end_time=now,
                        machine="circuit_breaker",
                        pid=0,
                    )
                )

            finally:
                # Release HALF_OPEN slot if applicable
                if state.state == CircuitState.HALF_OPEN:
                    await state.release_half_open_slot()

        return results

    async def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """
        Get current state of all circuit breakers.

        Returns:
            Dict mapping tool name to state info
        """
        states = {}
        async with self._states_lock:
            for tool, state in self._states.items():
                states[tool] = state.get_state()
        return states

    async def reset_circuit(self, tool: str) -> None:
        """
        Manually reset a circuit breaker.

        Args:
            tool: Tool name to reset
        """
        if tool in self._states:
            state = self._states[tool]
            async with state._lock:
                state.state = CircuitState.CLOSED
                state.failure_count = 0
                state.success_count = 0
                state.opened_at = None
                state.half_open_calls = 0
            logger.info(f"Manually reset circuit breaker for {tool}")
