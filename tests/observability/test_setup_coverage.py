# tests/observability/test_setup_coverage.py
"""Comprehensive tests for setup.py targeting >90% coverage.

NOTE: Uses patch.dict on function __globals__ instead of @patch decorators
because builtins.__import__ patching in earlier test files can cause module
identity splits, making standard @patch decorators ineffective.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from chuk_tool_processor.observability.setup import setup_observability


# Helper to patch names in setup_observability's own module globals.
def _patch_setup_globals(**overrides):
    """Return a patch.dict context manager targeting setup_observability.__globals__."""
    return patch.dict(setup_observability.__globals__, overrides)


class TestSetupObservability:
    """Tests for the setup_observability function."""

    def test_both_disabled(self):
        """When both tracing and metrics are disabled, nothing initializes."""
        status = setup_observability(enable_tracing=False, enable_metrics=False)
        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False

    def test_tracing_enabled_success(self):
        """Tracing initializes successfully when enabled."""
        mock_init_tracer = MagicMock(return_value=MagicMock())

        with _patch_setup_globals(init_tracer=mock_init_tracer):
            status = setup_observability(
                service_name="test-service",
                enable_tracing=True,
                enable_metrics=False,
            )
        assert status["tracing_enabled"] is True
        assert status["metrics_enabled"] is False
        mock_init_tracer.assert_called_once_with(service_name="test-service")

    def test_tracing_enabled_returns_none(self):
        """Tracing returns None when deps not installed."""
        mock_init_tracer = MagicMock(return_value=None)

        with _patch_setup_globals(init_tracer=mock_init_tracer):
            status = setup_observability(enable_tracing=True, enable_metrics=False)
        assert status["tracing_enabled"] is False

    def test_tracing_raises_exception(self):
        """Tracing exception is caught gracefully."""
        mock_init_tracer = MagicMock(side_effect=RuntimeError("import failed"))

        with _patch_setup_globals(init_tracer=mock_init_tracer):
            status = setup_observability(enable_tracing=True, enable_metrics=False)
        assert status["tracing_enabled"] is False

    def test_metrics_enabled_success(self):
        """Metrics and server initialize successfully."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics = MagicMock(return_value=mock_metrics)
        mock_start_server = MagicMock()

        with _patch_setup_globals(
            init_metrics=mock_init_metrics,
            start_metrics_server=mock_start_server,
        ):
            status = setup_observability(
                enable_tracing=False,
                enable_metrics=True,
                metrics_port=9999,
                metrics_host="127.0.0.1",
            )
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is True
        mock_start_server.assert_called_once_with(port=9999, host="127.0.0.1")

    def test_metrics_enabled_not_initialized(self):
        """Metrics enabled flag is False when init_metrics returns non-enabled."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = False
        mock_init_metrics = MagicMock(return_value=mock_metrics)
        mock_start_server = MagicMock()

        with _patch_setup_globals(
            init_metrics=mock_init_metrics,
            start_metrics_server=mock_start_server,
        ):
            status = setup_observability(enable_tracing=False, enable_metrics=True)
        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False
        mock_start_server.assert_not_called()

    def test_metrics_returns_none(self):
        """Metrics returns None -> not enabled."""
        mock_init_metrics = MagicMock(return_value=None)

        with _patch_setup_globals(init_metrics=mock_init_metrics):
            status = setup_observability(enable_tracing=False, enable_metrics=True)
        assert status["metrics_enabled"] is False

    def test_metrics_raises_exception(self):
        """Metrics init exception is caught gracefully."""
        mock_init_metrics = MagicMock(side_effect=RuntimeError("prometheus not installed"))

        with _patch_setup_globals(init_metrics=mock_init_metrics):
            status = setup_observability(enable_tracing=False, enable_metrics=True)
        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False

    def test_metrics_server_raises_exception(self):
        """Metrics server start exception is caught gracefully."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics = MagicMock(return_value=mock_metrics)
        mock_start_server = MagicMock(side_effect=OSError("port in use"))

        with _patch_setup_globals(
            init_metrics=mock_init_metrics,
            start_metrics_server=mock_start_server,
        ):
            status = setup_observability(enable_tracing=False, enable_metrics=True)
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is False

    def test_both_enabled_success(self):
        """Both tracing and metrics initialize successfully."""
        mock_init_tracer = MagicMock(return_value=MagicMock())
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics = MagicMock(return_value=mock_metrics)
        mock_start_server = MagicMock()

        with _patch_setup_globals(
            init_tracer=mock_init_tracer,
            init_metrics=mock_init_metrics,
            start_metrics_server=mock_start_server,
        ):
            status = setup_observability(
                service_name="full-service",
                enable_tracing=True,
                enable_metrics=True,
                metrics_port=8080,
            )
        assert status["tracing_enabled"] is True
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is True

    def test_log_summary_only_tracing(self):
        """Log summary branch when only tracing is enabled."""
        mock_init_tracer = MagicMock(return_value=MagicMock())

        with _patch_setup_globals(init_tracer=mock_init_tracer):
            status = setup_observability(enable_tracing=True, enable_metrics=False)
        assert status["tracing_enabled"] is True

    def test_log_summary_only_metrics(self):
        """Log summary branch when only metrics is enabled."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics = MagicMock(return_value=mock_metrics)
        mock_start_server = MagicMock()

        with _patch_setup_globals(
            init_metrics=mock_init_metrics,
            start_metrics_server=mock_start_server,
        ):
            status = setup_observability(enable_tracing=False, enable_metrics=True)
        assert status["metrics_enabled"] is True

    def test_log_summary_neither_enabled(self):
        """Log summary warning when nothing is enabled."""
        status = setup_observability(enable_tracing=False, enable_metrics=False)
        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is False

    def test_default_parameters(self):
        """Test default parameter values are used."""
        mock_init_tracer = MagicMock(return_value=None)

        with _patch_setup_globals(init_tracer=mock_init_tracer):
            setup_observability()
        # enable_tracing defaults to True, so init_tracer should be called
        mock_init_tracer.assert_called_once_with(service_name="chuk-tool-processor")
