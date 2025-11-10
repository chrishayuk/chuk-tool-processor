"""
OpenTelemetry tracing integration for chuk-tool-processor.

Provides drop-in distributed tracing with standardized span names and attributes.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from chuk_tool_processor.logging import get_logger

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

logger = get_logger("chuk_tool_processor.observability.tracing")

# Global tracer instance
_tracer: Tracer | None = None
_tracing_enabled = False


def init_tracer(service_name: str = "chuk-tool-processor") -> Tracer | NoOpTracer:
    """
    Initialize OpenTelemetry tracer with best-practice configuration.

    Args:
        service_name: Service name for tracing

    Returns:
        Configured OpenTelemetry tracer or NoOpTracer if initialization fails
    """
    global _tracer, _tracing_enabled

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Create resource with service name
        resource = Resource.create({"service.name": service_name})

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter (exports to OTEL collector)
        otlp_exporter = OTLPSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        _tracer = trace.get_tracer(__name__)
        _tracing_enabled = True

        logger.info(f"OpenTelemetry tracing initialized for service: {service_name}")
        return _tracer

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}. Tracing disabled.")
        _tracing_enabled = False
        return NoOpTracer()


def get_tracer() -> Tracer | NoOpTracer:
    """
    Get the current tracer instance.

    Returns:
        OpenTelemetry tracer or no-op tracer if not initialized
    """
    if _tracer is None:
        return NoOpTracer()
    return _tracer


def is_tracing_enabled() -> bool:
    """Check if tracing is enabled."""
    return _tracing_enabled


@contextmanager
def trace_tool_execution(
    tool: str,
    namespace: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for tracing tool execution.

    Creates a span with name "tool.execute" and standard attributes.

    Args:
        tool: Tool name
        namespace: Optional tool namespace
        attributes: Additional span attributes

    Example:
        with trace_tool_execution("calculator", attributes={"operation": "add"}):
            result = await tool.execute(a=5, b=3)
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    span_name = "tool.execute"
    span_attributes: dict[str, str | int | float | bool] = {
        "tool.name": tool,
    }

    if namespace:
        span_attributes["tool.namespace"] = namespace

    if attributes:
        # Flatten attributes with "tool." prefix
        for key, value in attributes.items():
            # Convert value to string for OTEL compatibility
            if isinstance(value, (str, int, float, bool)):
                span_attributes[f"tool.{key}"] = value
            else:
                span_attributes[f"tool.{key}"] = str(value)

    with _tracer.start_as_current_span(span_name, attributes=span_attributes) as span:
        yield span


@contextmanager
def trace_cache_operation(
    operation: str,
    tool: str,
    hit: bool | None = None,
    attributes: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for tracing cache operations.

    Args:
        operation: Cache operation (lookup, set, invalidate)
        tool: Tool name
        hit: Whether cache hit (for lookup operations)
        attributes: Additional span attributes

    Example:
        with trace_cache_operation("lookup", "calculator", hit=True):
            result = await cache.get(tool, key)
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    span_name = f"tool.cache.{operation}"
    span_attributes: dict[str, str | int | float | bool] = {
        "tool.name": tool,
        "cache.operation": operation,
    }

    if hit is not None:
        span_attributes["cache.hit"] = hit

    if attributes:
        for key, value in attributes.items():
            if isinstance(value, (str, int, float, bool)):
                span_attributes[f"cache.{key}"] = value
            else:
                span_attributes[f"cache.{key}"] = str(value)

    with _tracer.start_as_current_span(span_name, attributes=span_attributes) as span:
        yield span


@contextmanager
def trace_retry_attempt(
    tool: str,
    attempt: int,
    max_retries: int,
    attributes: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for tracing retry attempts.

    Args:
        tool: Tool name
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum retry attempts
        attributes: Additional span attributes

    Example:
        with trace_retry_attempt("api_tool", attempt=1, max_retries=3):
            result = await executor.execute([call])
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    span_name = "tool.retry.attempt"
    span_attributes: dict[str, str | int | float | bool] = {
        "tool.name": tool,
        "retry.attempt": attempt,
        "retry.max_attempts": max_retries,
    }

    if attributes:
        for key, value in attributes.items():
            if isinstance(value, (str, int, float, bool)):
                span_attributes[f"retry.{key}"] = value
            else:
                span_attributes[f"retry.{key}"] = str(value)

    with _tracer.start_as_current_span(span_name, attributes=span_attributes) as span:
        yield span


@contextmanager
def trace_circuit_breaker(
    tool: str,
    state: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for tracing circuit breaker operations.

    Args:
        tool: Tool name
        state: Circuit breaker state (CLOSED, OPEN, HALF_OPEN)
        attributes: Additional span attributes

    Example:
        with trace_circuit_breaker("api_tool", state="OPEN"):
            can_execute = await breaker.can_execute()
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    span_name = "tool.circuit_breaker.check"
    span_attributes: dict[str, str | int | float | bool] = {
        "tool.name": tool,
        "circuit.state": state,
    }

    if attributes:
        for key, value in attributes.items():
            if isinstance(value, (str, int, float, bool)):
                span_attributes[f"circuit.{key}"] = value
            else:
                span_attributes[f"circuit.{key}"] = str(value)

    with _tracer.start_as_current_span(span_name, attributes=span_attributes) as span:
        yield span


@contextmanager
def trace_rate_limit(
    tool: str,
    allowed: bool,
    attributes: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for tracing rate limiting.

    Args:
        tool: Tool name
        allowed: Whether request was allowed
        attributes: Additional span attributes

    Example:
        with trace_rate_limit("api_tool", allowed=True):
            await rate_limiter.acquire()
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    span_name = "tool.rate_limit.check"
    span_attributes: dict[str, str | int | float | bool] = {
        "tool.name": tool,
        "rate_limit.allowed": allowed,
    }

    if attributes:
        for key, value in attributes.items():
            if isinstance(value, (str, int, float, bool)):
                span_attributes[f"rate_limit.{key}"] = value
            else:
                span_attributes[f"rate_limit.{key}"] = str(value)

    with _tracer.start_as_current_span(span_name, attributes=span_attributes) as span:
        yield span


def add_span_event(span: Span | None, name: str, attributes: dict[str, Any] | None = None) -> None:
    """
    Add an event to the current span.

    Args:
        span: Span to add event to (can be None)
        name: Event name
        attributes: Event attributes
    """
    if span is None or not _tracing_enabled:
        return

    try:
        span.add_event(name, attributes=attributes or {})
    except Exception as e:
        logger.debug(f"Error adding span event: {e}")


def set_span_error(span: Span | None, error: Exception | str) -> None:
    """
    Mark span as error and record exception details.

    Args:
        span: Span to mark as error (can be None)
        error: Error to record
    """
    if span is None or not _tracing_enabled:
        return

    try:
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, str(error)))

        if isinstance(error, Exception):
            span.record_exception(error)
        else:
            span.add_event("error", {"error.message": str(error)})

    except Exception as e:
        logger.debug(f"Error setting span error: {e}")


class NoOpTracer:
    """No-op tracer when OpenTelemetry is not available."""

    @contextmanager
    def start_as_current_span(self, _name: str, **_kwargs: Any) -> Generator[None, None, None]:
        """No-op span context manager."""
        yield None
