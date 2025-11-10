"""
Prometheus metrics integration for chuk-tool-processor.

Provides drop-in Prometheus metrics with a /metrics HTTP endpoint.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from chuk_tool_processor.logging import get_logger

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram

logger = get_logger("chuk_tool_processor.observability.metrics")

# Global metrics instance
_metrics: PrometheusMetrics | None = None
_metrics_enabled = False


class PrometheusMetrics:
    """
    Prometheus metrics collector for tool execution.

    Provides standard metrics:
    - tool_executions_total: Counter of tool executions by tool, status
    - tool_execution_duration_seconds: Histogram of execution duration
    - tool_cache_operations_total: Counter of cache operations
    - tool_circuit_breaker_state: Gauge of circuit breaker state
    - tool_retry_attempts_total: Counter of retry attempts
    """

    def __init__(self) -> None:
        """Initialize Prometheus metrics."""
        try:
            from prometheus_client import Counter, Gauge, Histogram

            self._initialized = True

            # Tool execution metrics
            self.tool_executions_total: Counter = Counter(
                "tool_executions_total",
                "Total number of tool executions",
                ["tool", "namespace", "status"],
            )

            self.tool_execution_duration_seconds: Histogram = Histogram(
                "tool_execution_duration_seconds",
                "Tool execution duration in seconds",
                ["tool", "namespace"],
                buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            )

            # Cache metrics
            self.tool_cache_operations_total: Counter = Counter(
                "tool_cache_operations_total",
                "Total number of cache operations",
                ["tool", "operation", "result"],
            )

            # Circuit breaker metrics
            self.tool_circuit_breaker_state: Gauge = Gauge(
                "tool_circuit_breaker_state",
                "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
                ["tool"],
            )

            self.tool_circuit_breaker_failures_total: Counter = Counter(
                "tool_circuit_breaker_failures_total",
                "Total circuit breaker failures",
                ["tool"],
            )

            # Retry metrics
            self.tool_retry_attempts_total: Counter = Counter(
                "tool_retry_attempts_total",
                "Total retry attempts",
                ["tool", "attempt", "success"],
            )

            # Rate limiting metrics
            self.tool_rate_limit_checks_total: Counter = Counter(
                "tool_rate_limit_checks_total",
                "Total rate limit checks",
                ["tool", "allowed"],
            )

            logger.info("Prometheus metrics initialized")

        except ImportError as e:
            logger.warning(f"Prometheus client not installed: {e}. Metrics disabled.")
            self._initialized = False

    @property
    def enabled(self) -> bool:
        """Check if metrics are enabled."""
        return self._initialized

    def record_tool_execution(
        self,
        tool: str,
        namespace: str | None,
        duration: float,
        success: bool,
        cached: bool = False,
    ) -> None:
        """
        Record tool execution metrics.

        Args:
            tool: Tool name
            namespace: Tool namespace
            duration: Execution duration in seconds
            success: Whether execution succeeded
            cached: Whether result was cached
        """
        if not self._initialized:
            return

        ns = namespace or "default"
        status = "success" if success else "error"

        # Record execution count
        self.tool_executions_total.labels(tool=tool, namespace=ns, status=status).inc()

        # Record duration (skip for cached results as they're instant)
        if not cached:
            self.tool_execution_duration_seconds.labels(tool=tool, namespace=ns).observe(duration)

    def record_cache_operation(
        self,
        tool: str,
        operation: str,
        hit: bool | None = None,
    ) -> None:
        """
        Record cache operation metrics.

        Args:
            tool: Tool name
            operation: Cache operation (lookup, set, invalidate)
            hit: Whether cache hit (for lookup operations)
        """
        if not self._initialized:
            return

        result = "hit" if hit else "miss" if hit is not None else "set"
        self.tool_cache_operations_total.labels(tool=tool, operation=operation, result=result).inc()

    def record_circuit_breaker_state(
        self,
        tool: str,
        state: str,
    ) -> None:
        """
        Record circuit breaker state.

        Args:
            tool: Tool name
            state: Circuit state (CLOSED, OPEN, HALF_OPEN)
        """
        if not self._initialized:
            return

        state_value = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}.get(state.upper(), 0)
        self.tool_circuit_breaker_state.labels(tool=tool).set(state_value)

    def record_circuit_breaker_failure(self, tool: str) -> None:
        """
        Record circuit breaker failure.

        Args:
            tool: Tool name
        """
        if not self._initialized:
            return

        self.tool_circuit_breaker_failures_total.labels(tool=tool).inc()

    def record_retry_attempt(
        self,
        tool: str,
        attempt: int,
        success: bool,
    ) -> None:
        """
        Record retry attempt.

        Args:
            tool: Tool name
            attempt: Attempt number
            success: Whether attempt succeeded
        """
        if not self._initialized:
            return

        self.tool_retry_attempts_total.labels(
            tool=tool,
            attempt=str(attempt),
            success=str(success),
        ).inc()

    def record_rate_limit_check(
        self,
        tool: str,
        allowed: bool,
    ) -> None:
        """
        Record rate limit check.

        Args:
            tool: Tool name
            allowed: Whether request was allowed
        """
        if not self._initialized:
            return

        self.tool_rate_limit_checks_total.labels(tool=tool, allowed=str(allowed)).inc()


def init_metrics() -> PrometheusMetrics:
    """
    Initialize Prometheus metrics.

    Returns:
        PrometheusMetrics instance
    """
    global _metrics, _metrics_enabled

    _metrics = PrometheusMetrics()
    _metrics_enabled = _metrics.enabled

    return _metrics


def get_metrics() -> PrometheusMetrics | None:
    """
    Get current metrics instance.

    Returns:
        PrometheusMetrics instance or None if not initialized
    """
    return _metrics


def is_metrics_enabled() -> bool:
    """Check if metrics are enabled."""
    return _metrics_enabled


def start_metrics_server(port: int = 9090, host: str = "0.0.0.0") -> None:  # nosec B104
    """
    Start Prometheus metrics HTTP server.

    Serves metrics at http://{host}:{port}/metrics

    Args:
        port: Port to listen on
        host: Host to bind to

    Example:
        from chuk_tool_processor.observability import start_metrics_server

        # Start metrics server on port 9090
        start_metrics_server(port=9090)
    """
    try:
        from prometheus_client import start_http_server

        start_http_server(port=port, addr=host)
        logger.info(f"Prometheus metrics server started on http://{host}:{port}/metrics")

    except ImportError:
        logger.error("prometheus-client not installed. Install with: pip install prometheus-client")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")


class MetricsTimer:
    """
    Context manager for timing operations with Prometheus metrics.

    Example:
        with MetricsTimer() as timer:
            result = await tool.execute()

        # Record duration
        metrics.record_tool_execution("calculator", "default", timer.duration, success=True)
    """

    def __init__(self) -> None:
        self.start_time: float | None = None
        self.end_time: float | None = None

    def __enter__(self) -> MetricsTimer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_time = time.perf_counter()

    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        if self.start_time is None:
            return 0.0
        if self.end_time is None:
            return time.perf_counter() - self.start_time
        return self.end_time - self.start_time
