"""
Tests for OpenTelemetry tracing integration.
"""

import pytest


def test_tracing_import():
    """Test that tracing module imports successfully."""
    from chuk_tool_processor.observability import tracing

    assert tracing is not None


def test_get_tracer_without_init():
    """Test get_tracer returns no-op tracer when not initialized."""
    from chuk_tool_processor.observability.tracing import get_tracer

    tracer = get_tracer()
    assert tracer is not None


def test_is_tracing_enabled_default():
    """Test is_tracing_enabled returns status."""
    from chuk_tool_processor.observability.tracing import is_tracing_enabled

    # Should return a boolean (may be True if initialized in previous tests)
    result = is_tracing_enabled()
    assert isinstance(result, bool)


# Only run OTEL tests if opentelemetry packages are installed
pytest.importorskip("opentelemetry", reason="opentelemetry not installed")


def test_init_tracer():
    """Test tracer initialization."""
    from chuk_tool_processor.observability.tracing import init_tracer

    tracer = init_tracer(service_name="test-service")
    assert tracer is not None


def test_trace_tool_execution():
    """Test trace_tool_execution context manager."""
    from chuk_tool_processor.observability.tracing import trace_tool_execution

    # Should not raise errors
    with trace_tool_execution("test_tool", namespace="default", attributes={"operation": "add"}):
        pass

    assert True


def test_trace_cache_operation():
    """Test trace_cache_operation context manager."""
    from chuk_tool_processor.observability.tracing import trace_cache_operation

    # Test cache lookup
    with trace_cache_operation("lookup", "test_tool", hit=True):
        pass

    # Test cache set
    with trace_cache_operation("set", "test_tool", attributes={"ttl": 300}):
        pass

    assert True


def test_trace_retry_attempt():
    """Test trace_retry_attempt context manager."""
    from chuk_tool_processor.observability.tracing import trace_retry_attempt

    with trace_retry_attempt("test_tool", attempt=1, max_retries=3):
        pass

    assert True


def test_trace_circuit_breaker():
    """Test trace_circuit_breaker context manager."""
    from chuk_tool_processor.observability.tracing import trace_circuit_breaker

    with trace_circuit_breaker("test_tool", state="CLOSED"):
        pass

    with trace_circuit_breaker("test_tool", state="OPEN", attributes={"failure_count": 5}):
        pass

    assert True


def test_trace_rate_limit():
    """Test trace_rate_limit context manager."""
    from chuk_tool_processor.observability.tracing import trace_rate_limit

    with trace_rate_limit("test_tool", allowed=True):
        pass

    with trace_rate_limit("test_tool", allowed=False):
        pass

    assert True


def test_add_span_event():
    """Test add_span_event helper."""
    from chuk_tool_processor.observability.tracing import add_span_event, trace_tool_execution

    with trace_tool_execution("test_tool") as span:
        add_span_event(span, "test_event", {"key": "value"})

    assert True


def test_set_span_error():
    """Test set_span_error helper."""
    from chuk_tool_processor.observability.tracing import set_span_error, trace_tool_execution

    with trace_tool_execution("test_tool") as span:
        error = ValueError("Test error")
        set_span_error(span, error)

    with trace_tool_execution("test_tool") as span:
        set_span_error(span, "String error message")

    assert True
