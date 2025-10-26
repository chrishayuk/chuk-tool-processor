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


def test_get_tracer_returns_noop_when_not_initialized():
    """Test get_tracer returns NoOpTracer when not initialized (line 76)."""
    # Reset global tracer state
    import chuk_tool_processor.observability.tracing as tracing_module
    from chuk_tool_processor.observability.tracing import NoOpTracer, get_tracer

    original_tracer = tracing_module._tracer
    tracing_module._tracer = None

    try:
        tracer = get_tracer()
        assert isinstance(tracer, NoOpTracer)
    finally:
        tracing_module._tracer = original_tracer


def test_trace_tool_execution_when_disabled():
    """Test trace_tool_execution when tracing is disabled (lines 106-107)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    # Save original state
    original_enabled = tracing_module._tracing_enabled
    original_tracer = tracing_module._tracer

    try:
        # Disable tracing
        tracing_module._tracing_enabled = False
        tracing_module._tracer = None

        from chuk_tool_processor.observability.tracing import trace_tool_execution

        # Should yield None and return early
        with trace_tool_execution("test_tool", namespace="default") as span:
            assert span is None

    finally:
        # Restore state
        tracing_module._tracing_enabled = original_enabled
        tracing_module._tracer = original_tracer


def test_trace_cache_operation_when_disabled():
    """Test trace_cache_operation when tracing is disabled (line 151)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled
    original_tracer = tracing_module._tracer

    try:
        tracing_module._tracing_enabled = False
        tracing_module._tracer = None

        from chuk_tool_processor.observability.tracing import trace_cache_operation

        with trace_cache_operation("lookup", "test_tool", hit=True) as span:
            assert span is None

    finally:
        tracing_module._tracing_enabled = original_enabled
        tracing_module._tracer = original_tracer


def test_trace_retry_attempt_when_disabled():
    """Test trace_retry_attempt when tracing is disabled (line 195)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled
    original_tracer = tracing_module._tracer

    try:
        tracing_module._tracing_enabled = False
        tracing_module._tracer = None

        from chuk_tool_processor.observability.tracing import trace_retry_attempt

        with trace_retry_attempt("test_tool", attempt=1, max_retries=3) as span:
            assert span is None

    finally:
        tracing_module._tracing_enabled = original_enabled
        tracing_module._tracer = original_tracer


def test_trace_circuit_breaker_when_disabled():
    """Test trace_circuit_breaker when tracing is disabled (line 235)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled
    original_tracer = tracing_module._tracer

    try:
        tracing_module._tracing_enabled = False
        tracing_module._tracer = None

        from chuk_tool_processor.observability.tracing import trace_circuit_breaker

        with trace_circuit_breaker("test_tool", state="CLOSED") as span:
            assert span is None

    finally:
        tracing_module._tracing_enabled = original_enabled
        tracing_module._tracer = original_tracer


def test_trace_rate_limit_when_disabled():
    """Test trace_rate_limit when tracing is disabled (line 274)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled
    original_tracer = tracing_module._tracer

    try:
        tracing_module._tracing_enabled = False
        tracing_module._tracer = None

        from chuk_tool_processor.observability.tracing import trace_rate_limit

        with trace_rate_limit("test_tool", allowed=True) as span:
            assert span is None

    finally:
        tracing_module._tracing_enabled = original_enabled
        tracing_module._tracer = original_tracer


def test_add_span_event_with_none_span():
    """Test add_span_event handles None span gracefully (line 304)."""
    from chuk_tool_processor.observability.tracing import add_span_event

    # Should not raise errors when span is None
    add_span_event(None, "test_event", {"key": "value"})
    assert True


def test_add_span_event_when_tracing_disabled():
    """Test add_span_event when tracing is disabled (line 304)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled

    try:
        tracing_module._tracing_enabled = False

        # Create a mock span
        from unittest.mock import MagicMock

        from chuk_tool_processor.observability.tracing import add_span_event

        mock_span = MagicMock()

        # Should return early without calling add_event
        add_span_event(mock_span, "test_event", {"key": "value"})

        # Verify add_event was not called
        mock_span.add_event.assert_not_called()

    finally:
        tracing_module._tracing_enabled = original_enabled


def test_add_span_event_error_handling():
    """Test add_span_event handles exceptions gracefully (line 309)."""
    from unittest.mock import MagicMock

    from chuk_tool_processor.observability.tracing import add_span_event

    # Create a mock span that raises an exception
    mock_span = MagicMock()
    mock_span.add_event.side_effect = Exception("Test error")

    # Should not raise, just log debug message
    add_span_event(mock_span, "test_event", {"key": "value"})
    assert True


def test_set_span_error_with_none_span():
    """Test set_span_error handles None span gracefully (line 321)."""
    from chuk_tool_processor.observability.tracing import set_span_error

    # Should not raise errors when span is None
    set_span_error(None, ValueError("Test error"))
    set_span_error(None, "String error")
    assert True


def test_set_span_error_when_tracing_disabled():
    """Test set_span_error when tracing is disabled (line 321)."""
    import chuk_tool_processor.observability.tracing as tracing_module

    original_enabled = tracing_module._tracing_enabled

    try:
        tracing_module._tracing_enabled = False

        from unittest.mock import MagicMock

        from chuk_tool_processor.observability.tracing import set_span_error

        mock_span = MagicMock()

        # Should return early without calling set_status
        set_span_error(mock_span, ValueError("Test error"))

        # Verify set_status was not called
        mock_span.set_status.assert_not_called()

    finally:
        tracing_module._tracing_enabled = original_enabled


def test_set_span_error_exception_handling():
    """Test set_span_error handles exceptions gracefully (line 334)."""
    from unittest.mock import MagicMock

    from chuk_tool_processor.observability.tracing import set_span_error

    # Create a mock span that raises an exception
    mock_span = MagicMock()
    mock_span.set_status.side_effect = Exception("Test error")

    # Should not raise, just log debug message
    set_span_error(mock_span, ValueError("Test error"))
    assert True


def test_noop_tracer_context_manager():
    """Test NoOpTracer.start_as_current_span context manager (line 343)."""
    from chuk_tool_processor.observability.tracing import NoOpTracer

    tracer = NoOpTracer()

    # Should yield None
    with tracer.start_as_current_span("test_span", attributes={"key": "value"}) as span:
        assert span is None


def test_trace_with_non_primitive_attributes():
    """Test trace context managers handle non-primitive attributes (lines 124, 168, 210, etc)."""
    from chuk_tool_processor.observability.tracing import (
        trace_cache_operation,
        trace_circuit_breaker,
        trace_rate_limit,
        trace_retry_attempt,
        trace_tool_execution,
    )

    # Test with complex attribute values that need str() conversion
    complex_attr = {"nested": {"data": [1, 2, 3]}}

    with trace_tool_execution("test_tool", attributes={"complex": complex_attr}):
        pass

    with trace_cache_operation("lookup", "test_tool", attributes={"complex": complex_attr}):
        pass

    with trace_retry_attempt("test_tool", attempt=1, max_retries=3, attributes={"complex": complex_attr}):
        pass

    with trace_circuit_breaker("test_tool", state="CLOSED", attributes={"complex": complex_attr}):
        pass

    with trace_rate_limit("test_tool", allowed=True, attributes={"complex": complex_attr}):
        pass

    assert True


def test_init_tracer_import_error():
    """Test init_tracer handles ImportError gracefully (lines 62-65)."""
    import sys
    from unittest.mock import patch

    # Mock opentelemetry to not be available
    with patch.dict(sys.modules, {"opentelemetry": None}):
        from chuk_tool_processor.observability.tracing import NoOpTracer, init_tracer

        # Should return NoOpTracer when opentelemetry is not available
        tracer = init_tracer(service_name="test-service")
        assert isinstance(tracer, NoOpTracer)

    assert True
