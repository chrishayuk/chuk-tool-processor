"""Tests for observability metrics module."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest

# Mock prometheus_client before importing the module under test
sys.modules["prometheus_client"] = MagicMock()

from chuk_tool_processor.observability.metrics import (  # noqa: E402
    MetricsTimer,
    PrometheusMetrics,
    get_metrics,
    init_metrics,
    start_metrics_server,
)


class TestPrometheusMetrics:
    """Tests for PrometheusMetrics class."""

    def test_init_success(self):
        """Test successful initialization with prometheus_client."""
        # Reset module state
        # Reload to ensure fresh state
        import importlib

        import chuk_tool_processor.observability.metrics as metrics_module

        importlib.reload(metrics_module)

        metrics = metrics_module.PrometheusMetrics()

        assert metrics._initialized is True
        assert metrics.enabled is True

    def test_init_failure(self):
        """Test initialization failure when prometheus_client not installed."""
        # Temporarily remove prometheus_client to simulate missing dependency
        saved_module = sys.modules.pop("prometheus_client", None)

        try:
            import importlib

            import chuk_tool_processor.observability.metrics as metrics_module

            importlib.reload(metrics_module)

            metrics = metrics_module.PrometheusMetrics()

            assert metrics._initialized is False
            assert metrics.enabled is False
        finally:
            if saved_module:
                sys.modules["prometheus_client"] = saved_module

    def test_record_tool_execution(self):
        """Test recording tool execution metrics."""
        metrics = PrometheusMetrics()

        # Record success - should not raise even if mocked
        metrics.record_tool_execution("calculator", "math", 0.5, success=True)

    def test_record_tool_execution_cached(self):
        """Test recording cached tool execution doesn't record duration."""
        metrics = PrometheusMetrics()

        # Record cached result - should not raise even if mocked
        metrics.record_tool_execution("calculator", "math", 0.0, success=True, cached=True)

    def test_record_cache_operation(self):
        """Test recording cache operations."""
        metrics = PrometheusMetrics()

        # These should not raise even if mocked
        metrics.record_cache_operation("calculator", "lookup", hit=True)
        metrics.record_cache_operation("calculator", "lookup", hit=False)
        metrics.record_cache_operation("calculator", "set", hit=None)

    def test_record_circuit_breaker_state(self):
        """Test recording circuit breaker state."""
        metrics = PrometheusMetrics()

        # These should not raise even if mocked
        metrics.record_circuit_breaker_state("api_tool", "CLOSED")
        metrics.record_circuit_breaker_state("api_tool", "OPEN")
        metrics.record_circuit_breaker_state("api_tool", "HALF_OPEN")

    def test_record_circuit_breaker_failure(self):
        """Test recording circuit breaker failure."""
        metrics = PrometheusMetrics()

        metrics.record_circuit_breaker_failure("api_tool")

    def test_record_retry_attempt(self):
        """Test recording retry attempts."""
        metrics = PrometheusMetrics()

        metrics.record_retry_attempt("api_tool", 2, success=True)

    def test_record_rate_limit_check(self):
        """Test recording rate limit checks."""
        metrics = PrometheusMetrics()

        metrics.record_rate_limit_check("api_tool", allowed=True)

    def test_recording_when_not_initialized(self):
        """Test that recording methods don't fail when metrics not initialized."""
        # Create metrics with prometheus_client not available
        saved_module = sys.modules.pop("prometheus_client", None)

        try:
            import importlib

            import chuk_tool_processor.observability.metrics as metrics_module

            importlib.reload(metrics_module)

            metrics = metrics_module.PrometheusMetrics()
            assert not metrics.enabled

            # All these should not raise
            metrics.record_tool_execution("test", "default", 1.0, True)
            metrics.record_cache_operation("test", "lookup", True)
            metrics.record_circuit_breaker_state("test", "CLOSED")
            metrics.record_circuit_breaker_failure("test")
            metrics.record_retry_attempt("test", 1, True)
            metrics.record_rate_limit_check("test", True)
        finally:
            if saved_module:
                sys.modules["prometheus_client"] = saved_module


class TestMetricsTimer:
    """Tests for MetricsTimer context manager."""

    def test_timer_basic(self):
        """Test basic timer functionality."""
        with MetricsTimer() as timer:
            time.sleep(0.01)

        assert timer.duration > 0
        assert timer.start_time is not None
        assert timer.end_time is not None

    def test_timer_duration_before_exit(self):
        """Test getting duration before context exits."""
        with MetricsTimer() as timer:
            time.sleep(0.01)
            duration_during = timer.duration
            assert duration_during > 0

        duration_after = timer.duration
        assert duration_after >= duration_during

    def test_timer_uninitialized(self):
        """Test timer duration when not started."""
        timer = MetricsTimer()
        assert timer.duration == 0.0


class TestModuleFunctions:
    """Tests for module-level functions."""

    def teardown_method(self):
        """Reset global state after each test."""
        import chuk_tool_processor.observability.metrics as metrics_module

        metrics_module._metrics = None
        metrics_module._metrics_enabled = False

    def test_init_metrics(self):
        """Test init_metrics function."""
        metrics = init_metrics()

        assert metrics is not None
        # Metrics enabled depends on whether prometheus_client is available
        assert get_metrics() == metrics

    def test_init_metrics_failure(self):
        """Test init_metrics when prometheus_client not available."""
        saved_module = sys.modules.pop("prometheus_client", None)

        try:
            import importlib

            import chuk_tool_processor.observability.metrics as metrics_module

            importlib.reload(metrics_module)

            metrics = metrics_module.init_metrics()

            assert metrics is not None
            assert not metrics.enabled
        finally:
            if saved_module:
                sys.modules["prometheus_client"] = saved_module
                # Restore original state
                import chuk_tool_processor.observability.metrics as metrics_module

                importlib.reload(metrics_module)

    def test_get_metrics_when_none(self):
        """Test get_metrics when not initialized."""
        # Reset module state to ensure clean test
        import chuk_tool_processor.observability.metrics as metrics_module

        metrics_module._metrics_client = None
        assert get_metrics() is None

    def test_start_metrics_server_success(self):
        """Test starting metrics server successfully."""
        # Should not raise even if mocked
        start_metrics_server(port=9090, host="0.0.0.0")

    def test_start_metrics_server_no_client(self):
        """Test starting metrics server when client not installed."""
        saved_module = sys.modules.pop("prometheus_client", None)

        try:
            import importlib

            import chuk_tool_processor.observability.metrics as metrics_module

            importlib.reload(metrics_module)

            # Should not raise
            metrics_module.start_metrics_server(port=9090)
        finally:
            if saved_module:
                sys.modules["prometheus_client"] = saved_module

    def test_start_metrics_server_error(self):
        """Test starting metrics server with error."""
        # Mock start_http_server to raise an exception
        if "prometheus_client" in sys.modules:
            original_start = sys.modules["prometheus_client"].start_http_server
            sys.modules["prometheus_client"].start_http_server = MagicMock(side_effect=Exception("Port in use"))

            try:
                # Should not raise - errors are caught
                start_metrics_server(port=9090)
            finally:
                sys.modules["prometheus_client"].start_http_server = original_start


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
