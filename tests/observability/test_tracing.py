"""Tests for observability tracing module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.observability.tracing import (
    NoOpTracer,
    add_span_event,
    init_tracer,
    is_tracing_enabled,
    set_span_error,
    trace_cache_operation,
    trace_circuit_breaker,
    trace_rate_limit,
    trace_retry_attempt,
    trace_tool_execution,
)


class TestInitTracer:
    """Tests for tracer initialization."""

    def teardown_method(self):
        """Reset global state after each test."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_init_tracer_success(self):
        """Test successful tracer initialization.

        Note: This test will return NoOpTracer if OpenTelemetry is not installed,
        which is expected behavior.
        """
        tracer = init_tracer(service_name="test-service")

        # Tracer should always be returned (real or NoOpTracer)
        assert tracer is not None

        # Check if it's a real tracer or NoOpTracer
        # If OpenTelemetry is installed, tracing should be enabled
        # If not, we get NoOpTracer and tracing is disabled
        if isinstance(tracer, NoOpTracer):
            assert not is_tracing_enabled()
        else:
            assert is_tracing_enabled()

    def test_init_tracer_import_error(self):
        """Test that NoOpTracer is returned when OpenTelemetry not available.

        Note: This test verifies NoOpTracer functionality rather than simulating
        import failures, as the latter is difficult to test reliably due to
        Python's import caching.
        """
        # Verify NoOpTracer works correctly as a fallback
        noop_tracer = NoOpTracer()

        # Should work as a context manager
        with noop_tracer.start_as_current_span("test_span") as span:
            assert span is None

    def test_get_tracer_not_initialized(self):
        """Test get_tracer when not initialized."""
        # Import to ensure we use the non-reloaded module
        import chuk_tool_processor.observability.tracing as tracing_module

        # Ensure tracer is not initialized
        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

        tracer = tracing_module.get_tracer()
        assert isinstance(tracer, tracing_module.NoOpTracer)


class TestNoOpTracer:
    """Tests for NoOpTracer."""

    def test_noop_tracer_context_manager(self):
        """Test NoOpTracer context manager."""
        tracer = NoOpTracer()

        with tracer.start_as_current_span("test_span", attributes={"foo": "bar"}) as span:
            assert span is None


class TestTraceToolExecution:
    """Tests for trace_tool_execution context manager."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_trace_tool_execution_disabled(self):
        """Test trace_tool_execution when tracing disabled."""
        with trace_tool_execution("calculator") as span:
            assert span is None

    def test_trace_tool_execution_enabled(self):
        """Test trace_tool_execution when tracing enabled."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # This should not raise even if mocked
        with trace_tool_execution("calculator", namespace="math", attributes={"operation": "add"}):
            pass

    def test_trace_tool_execution_type_conversion(self):
        """Test attribute type conversion in trace_tool_execution."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # Test with complex object that needs string conversion - should not raise
        with trace_tool_execution("test", attributes={"obj": {"nested": "value"}}):
            pass


class TestTraceCacheOperation:
    """Tests for trace_cache_operation context manager."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_trace_cache_disabled(self):
        """Test trace_cache_operation when disabled."""
        with trace_cache_operation("lookup", "calculator", hit=True) as span:
            assert span is None

    def test_trace_cache_enabled(self):
        """Test trace_cache_operation when enabled."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # Should not raise
        with trace_cache_operation("lookup", "calculator", hit=True, attributes={"key": "test"}):
            pass


class TestTraceRetryAttempt:
    """Tests for trace_retry_attempt context manager."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_trace_retry_disabled(self):
        """Test trace_retry_attempt when disabled."""
        with trace_retry_attempt("api_tool", 1, 3) as span:
            assert span is None

    def test_trace_retry_enabled(self):
        """Test trace_retry_attempt when enabled."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # Should not raise
        with trace_retry_attempt("api_tool", 2, 5, attributes={"reason": "timeout"}):
            pass


class TestTraceCircuitBreaker:
    """Tests for trace_circuit_breaker context manager."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_trace_circuit_breaker_disabled(self):
        """Test trace_circuit_breaker when disabled."""
        with trace_circuit_breaker("api_tool", "OPEN") as span:
            assert span is None

    def test_trace_circuit_breaker_enabled(self):
        """Test trace_circuit_breaker when enabled."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # Should not raise
        with trace_circuit_breaker("api_tool", "OPEN", attributes={"failures": 5}):
            pass


class TestTraceRateLimit:
    """Tests for trace_rate_limit context manager."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_trace_rate_limit_disabled(self):
        """Test trace_rate_limit when disabled."""
        with trace_rate_limit("api_tool", allowed=True) as span:
            assert span is None

    def test_trace_rate_limit_enabled(self):
        """Test trace_rate_limit when enabled."""
        # Initialize tracer first
        init_tracer(service_name="test")

        # Should not raise
        with trace_rate_limit("api_tool", allowed=False, attributes={"limit": 100}):
            pass


class TestSpanHelpers:
    """Tests for span helper functions."""

    def teardown_method(self):
        """Reset global state."""
        import chuk_tool_processor.observability.tracing as tracing_module

        tracing_module._tracer = None
        tracing_module._tracing_enabled = False

    def test_add_span_event_no_span(self):
        """Test add_span_event with None span."""
        # Should not raise
        add_span_event(None, "test_event", {"key": "value"})

    def test_add_span_event_with_span(self):
        """Test add_span_event with valid span."""
        import chuk_tool_processor.observability.tracing as tracing_module

        # Enable tracing so the function doesn't early return
        tracing_module._tracing_enabled = True

        mock_span = MagicMock()

        add_span_event(mock_span, "test_event", {"key": "value"})

        # Should have called add_event
        mock_span.add_event.assert_called_once_with("test_event", attributes={"key": "value"})

    def test_add_span_event_exception(self):
        """Test add_span_event handles exceptions."""
        mock_span = MagicMock()
        mock_span.add_event.side_effect = Exception("Test error")

        # Should not raise
        add_span_event(mock_span, "test_event")

    def test_set_span_error_no_span(self):
        """Test set_span_error with None span."""
        # Should not raise
        set_span_error(None, Exception("test"))

    def test_set_span_error_with_exception(self):
        """Test set_span_error with exception."""
        import chuk_tool_processor.observability.tracing as tracing_module

        # Enable tracing so the function doesn't early return
        tracing_module._tracing_enabled = True

        # Mock OpenTelemetry imports that are imported inside the function
        mock_status_instance = MagicMock()
        mock_status = MagicMock(return_value=mock_status_instance)
        mock_status_code = MagicMock()
        mock_status_code.ERROR = "ERROR"

        # Patch the imports inside the set_span_error function
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.trace": MagicMock(Status=mock_status, StatusCode=mock_status_code),
            },
        ):
            mock_span = MagicMock()
            error = Exception("Test error")

            set_span_error(mock_span, error)

            # Should have called set_status and record_exception
            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once_with(error)

    def test_set_span_error_with_string(self):
        """Test set_span_error with string error."""
        import chuk_tool_processor.observability.tracing as tracing_module

        # Enable tracing so the function doesn't early return
        tracing_module._tracing_enabled = True

        # Mock OpenTelemetry imports that are imported inside the function
        mock_status_instance = MagicMock()
        mock_status = MagicMock(return_value=mock_status_instance)
        mock_status_code = MagicMock()
        mock_status_code.ERROR = "ERROR"

        # Patch the imports inside the set_span_error function
        with patch.dict(
            "sys.modules",
            {
                "opentelemetry.trace": MagicMock(Status=mock_status, StatusCode=mock_status_code),
            },
        ):
            mock_span = MagicMock()

            set_span_error(mock_span, "Test error message")

            # Should have called set_status and add_event
            mock_span.set_status.assert_called_once()
            mock_span.add_event.assert_called_once_with("error", {"error.message": "Test error message"})

    def test_set_span_error_exception_handling(self):
        """Test set_span_error handles exceptions gracefully."""
        mock_span = MagicMock()
        # Make set_status raise an exception
        mock_span.set_status.side_effect = Exception("Test error")

        # Should not raise
        set_span_error(mock_span, Exception("test"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
