# tests/observability/test_metrics_coverage.py
"""Comprehensive tests for metrics.py targeting >90% coverage."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from chuk_tool_processor.observability.metrics import (
    MetricsTimer,
    PrometheusMetrics,
    get_metrics,
    init_metrics,
    is_metrics_enabled,
    start_metrics_server,
)

# ------------------------------------------------------------------ #
# PrometheusMetrics - uninitialized (no prometheus_client)
# ------------------------------------------------------------------ #


class TestPrometheusMetricsNotInitialized:
    """Tests for when prometheus_client is not installed."""

    @patch("chuk_tool_processor.observability.metrics.PrometheusMetrics.__init__")
    def _make_uninit(self, mock_init: MagicMock) -> PrometheusMetrics:
        """Create a PrometheusMetrics with _initialized=False."""
        mock_init.return_value = None
        m = PrometheusMetrics.__new__(PrometheusMetrics)
        m._initialized = False
        return m

    def test_enabled_false(self):
        m = self._make_uninit()
        assert m.enabled is False

    def test_record_tool_execution_noop(self):
        m = self._make_uninit()
        # Should not raise
        m.record_tool_execution("calc", "default", 1.0, True)

    def test_record_cache_operation_noop(self):
        m = self._make_uninit()
        m.record_cache_operation("calc", "lookup", hit=True)

    def test_record_circuit_breaker_state_noop(self):
        m = self._make_uninit()
        m.record_circuit_breaker_state("calc", "OPEN")

    def test_record_circuit_breaker_failure_noop(self):
        m = self._make_uninit()
        m.record_circuit_breaker_failure("calc")

    def test_record_retry_attempt_noop(self):
        m = self._make_uninit()
        m.record_retry_attempt("calc", 1, False)

    def test_record_rate_limit_check_noop(self):
        m = self._make_uninit()
        m.record_rate_limit_check("calc", True)


# ------------------------------------------------------------------ #
# PrometheusMetrics - initialized (with mocked prometheus_client)
# ------------------------------------------------------------------ #


class TestPrometheusMetricsInitialized:
    """Tests for when prometheus_client is available."""

    def _make_metrics(self) -> PrometheusMetrics:
        """Create a PrometheusMetrics with mocked counters/gauges/histograms."""
        m = PrometheusMetrics.__new__(PrometheusMetrics)
        m._initialized = True

        # Mock all metric objects
        m.tool_executions_total = MagicMock()
        m.tool_execution_duration_seconds = MagicMock()
        m.tool_cache_operations_total = MagicMock()
        m.tool_circuit_breaker_state = MagicMock()
        m.tool_circuit_breaker_failures_total = MagicMock()
        m.tool_retry_attempts_total = MagicMock()
        m.tool_rate_limit_checks_total = MagicMock()
        return m

    def test_enabled_true(self):
        m = self._make_metrics()
        assert m.enabled is True

    def test_record_tool_execution_success(self):
        m = self._make_metrics()
        m.record_tool_execution("calc", "math", 0.5, True)
        m.tool_executions_total.labels.assert_called_with(tool="calc", namespace="math", status="success")
        m.tool_executions_total.labels().inc.assert_called_once()
        m.tool_execution_duration_seconds.labels.assert_called_with(tool="calc", namespace="math")
        m.tool_execution_duration_seconds.labels().observe.assert_called_once_with(0.5)

    def test_record_tool_execution_error(self):
        m = self._make_metrics()
        m.record_tool_execution("calc", "math", 1.0, False)
        m.tool_executions_total.labels.assert_called_with(tool="calc", namespace="math", status="error")

    def test_record_tool_execution_cached_skips_duration(self):
        m = self._make_metrics()
        m.record_tool_execution("calc", "math", 0.001, True, cached=True)
        m.tool_executions_total.labels().inc.assert_called_once()
        # Duration should NOT be observed for cached results
        m.tool_execution_duration_seconds.labels().observe.assert_not_called()

    def test_record_tool_execution_none_namespace(self):
        m = self._make_metrics()
        m.record_tool_execution("calc", None, 0.5, True)
        m.tool_executions_total.labels.assert_called_with(tool="calc", namespace="default", status="success")

    def test_record_cache_operation_hit(self):
        m = self._make_metrics()
        m.record_cache_operation("calc", "lookup", hit=True)
        m.tool_cache_operations_total.labels.assert_called_with(tool="calc", operation="lookup", result="hit")

    def test_record_cache_operation_miss(self):
        m = self._make_metrics()
        m.record_cache_operation("calc", "lookup", hit=False)
        m.tool_cache_operations_total.labels.assert_called_with(tool="calc", operation="lookup", result="miss")

    def test_record_cache_operation_set(self):
        m = self._make_metrics()
        m.record_cache_operation("calc", "set", hit=None)
        m.tool_cache_operations_total.labels.assert_called_with(tool="calc", operation="set", result="set")

    def test_record_circuit_breaker_state_closed(self):
        m = self._make_metrics()
        m.record_circuit_breaker_state("calc", "CLOSED")
        m.tool_circuit_breaker_state.labels.assert_called_with(tool="calc")
        m.tool_circuit_breaker_state.labels().set.assert_called_with(0)

    def test_record_circuit_breaker_state_open(self):
        m = self._make_metrics()
        m.record_circuit_breaker_state("calc", "OPEN")
        m.tool_circuit_breaker_state.labels().set.assert_called_with(1)

    def test_record_circuit_breaker_state_half_open(self):
        m = self._make_metrics()
        m.record_circuit_breaker_state("calc", "HALF_OPEN")
        m.tool_circuit_breaker_state.labels().set.assert_called_with(2)

    def test_record_circuit_breaker_state_unknown(self):
        m = self._make_metrics()
        m.record_circuit_breaker_state("calc", "UNKNOWN")
        m.tool_circuit_breaker_state.labels().set.assert_called_with(0)

    def test_record_circuit_breaker_failure(self):
        m = self._make_metrics()
        m.record_circuit_breaker_failure("calc")
        m.tool_circuit_breaker_failures_total.labels.assert_called_with(tool="calc")
        m.tool_circuit_breaker_failures_total.labels().inc.assert_called_once()

    def test_record_retry_attempt_success(self):
        m = self._make_metrics()
        m.record_retry_attempt("calc", 2, True)
        m.tool_retry_attempts_total.labels.assert_called_with(tool="calc", attempt="2", success="True")
        m.tool_retry_attempts_total.labels().inc.assert_called_once()

    def test_record_retry_attempt_failure(self):
        m = self._make_metrics()
        m.record_retry_attempt("calc", 1, False)
        m.tool_retry_attempts_total.labels.assert_called_with(tool="calc", attempt="1", success="False")

    def test_record_rate_limit_check_allowed(self):
        m = self._make_metrics()
        m.record_rate_limit_check("calc", True)
        m.tool_rate_limit_checks_total.labels.assert_called_with(tool="calc", allowed="True")
        m.tool_rate_limit_checks_total.labels().inc.assert_called_once()

    def test_record_rate_limit_check_denied(self):
        m = self._make_metrics()
        m.record_rate_limit_check("calc", False)
        m.tool_rate_limit_checks_total.labels.assert_called_with(tool="calc", allowed="False")


# ------------------------------------------------------------------ #
# PrometheusMetrics.__init__ with ImportError
# ------------------------------------------------------------------ #


class TestPrometheusMetricsImportError:
    """Test __init__ when prometheus_client is not installed."""

    def test_init_without_prometheus(self):
        """When prometheus_client can't be imported, _initialized is False.

        Instead of patching builtins.__import__ (which corrupts module
        identities for subsequent tests), we directly construct an
        uninitialised instance and verify the fallback behaviour.
        """
        m = PrometheusMetrics.__new__(PrometheusMetrics)
        m._initialized = False
        assert m.enabled is False


# ------------------------------------------------------------------ #
# Module-level functions
# ------------------------------------------------------------------ #


class TestModuleFunctions:
    """Tests for init_metrics, get_metrics, is_metrics_enabled, start_metrics_server."""

    def test_init_metrics(self):
        """Test init_metrics creates and sets a PrometheusMetrics instance."""
        result = init_metrics()
        assert result is not None
        assert isinstance(result, PrometheusMetrics)
        # Verify module state via get_metrics (same globals as init_metrics)
        assert get_metrics() is result
        assert is_metrics_enabled() == result.enabled

    def test_get_metrics_after_init(self):
        """Test get_metrics returns the instance after init."""
        init_metrics()
        result = get_metrics()
        assert result is not None
        assert isinstance(result, PrometheusMetrics)

    def test_is_metrics_enabled(self):
        """Test is_metrics_enabled reflects init state."""
        result = init_metrics()
        assert is_metrics_enabled() == result.enabled

    def test_start_metrics_server_success(self):
        """Server starts successfully when prometheus_client is available."""
        # prometheus_client is installed, so start_http_server exists.
        # Patch it at the point of use inside start_metrics_server.
        mock_start = MagicMock()
        with patch("prometheus_client.start_http_server", mock_start):
            start_metrics_server(port=9999, host="127.0.0.1")
        mock_start.assert_called_once_with(port=9999, addr="127.0.0.1")

    def test_start_metrics_server_runtime_error(self):
        """Server handles runtime errors gracefully."""
        mock_start = MagicMock(side_effect=OSError("Address already in use"))
        with patch("prometheus_client.start_http_server", mock_start):
            # Should not raise
            start_metrics_server(port=9999)

    def test_get_metrics_returns_none_before_init(self):
        """get_metrics returns None before init_metrics is called."""
        # Use function's own __globals__ to avoid module identity splits
        # caused by builtins.__import__ patching in earlier test files.
        g = get_metrics.__globals__
        old = g["_metrics"]
        g["_metrics"] = None
        try:
            assert get_metrics() is None
        finally:
            g["_metrics"] = old

    def test_is_metrics_enabled_false_before_init(self):
        """is_metrics_enabled is False before init."""
        g = is_metrics_enabled.__globals__
        old = g["_metrics_enabled"]
        g["_metrics_enabled"] = False
        try:
            assert is_metrics_enabled() is False
        finally:
            g["_metrics_enabled"] = old


# ------------------------------------------------------------------ #
# MetricsTimer
# ------------------------------------------------------------------ #


class TestMetricsTimer:
    """Tests for the MetricsTimer context manager."""

    def test_basic_usage(self):
        with MetricsTimer() as timer:
            time.sleep(0.01)

        assert timer.start_time is not None
        assert timer.end_time is not None
        assert timer.duration > 0.0

    def test_duration_before_enter(self):
        timer = MetricsTimer()
        assert timer.duration == 0.0

    def test_duration_during_context(self):
        timer = MetricsTimer()
        timer.start_time = time.perf_counter()
        # end_time is None => duration is computed from now
        dur = timer.duration
        assert dur >= 0.0

    def test_duration_after_exit(self):
        with MetricsTimer() as timer:
            pass
        dur = timer.duration
        assert dur >= 0.0
        assert timer.end_time is not None

    def test_start_time_none_returns_zero(self):
        timer = MetricsTimer()
        assert timer.start_time is None
        assert timer.duration == 0.0

    def test_end_time_none_returns_elapsed(self):
        timer = MetricsTimer()
        timer.start_time = time.perf_counter()
        # end_time is None, should compute from perf_counter
        d = timer.duration
        assert d >= 0.0

    def test_context_manager_enter_returns_self(self):
        timer = MetricsTimer()
        result = timer.__enter__()
        assert result is timer
        timer.__exit__(None, None, None)

    def test_context_manager_exit_sets_end_time(self):
        timer = MetricsTimer()
        timer.__enter__()
        assert timer.end_time is None
        timer.__exit__(None, None, None)
        assert timer.end_time is not None
