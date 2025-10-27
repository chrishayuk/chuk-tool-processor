"""Tests for observability setup module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.observability.setup import setup_observability


class TestSetupObservability:
    """Tests for setup_observability function."""

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    @patch("chuk_tool_processor.observability.setup.start_metrics_server")
    def test_setup_both_enabled(self, mock_start_server, mock_init_metrics, mock_init_tracer):
        """Test setup with both tracing and metrics enabled."""
        mock_tracer = MagicMock()
        mock_init_tracer.return_value = mock_tracer

        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics.return_value = mock_metrics

        status = setup_observability(
            service_name="test-service",
            enable_tracing=True,
            enable_metrics=True,
            metrics_port=9090,
            metrics_host="0.0.0.0",
        )

        assert status["tracing_enabled"] is True
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is True

        mock_init_tracer.assert_called_once_with(service_name="test-service")
        mock_init_metrics.assert_called_once()
        mock_start_server.assert_called_once_with(port=9090, host="0.0.0.0")

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_tracing_only(self, mock_init_metrics, mock_init_tracer):
        """Test setup with only tracing enabled."""
        mock_tracer = MagicMock()
        mock_init_tracer.return_value = mock_tracer

        status = setup_observability(
            enable_tracing=True,
            enable_metrics=False,
        )

        assert status["tracing_enabled"] is True
        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False

        mock_init_tracer.assert_called_once()
        mock_init_metrics.assert_not_called()

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    @patch("chuk_tool_processor.observability.setup.start_metrics_server")
    def test_setup_metrics_only(self, mock_start_server, mock_init_metrics, mock_init_tracer):
        """Test setup with only metrics enabled."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics.return_value = mock_metrics

        status = setup_observability(
            enable_tracing=False,
            enable_metrics=True,
        )

        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is True

        mock_init_tracer.assert_not_called()
        mock_init_metrics.assert_called_once()

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_both_disabled(self, mock_init_metrics, mock_init_tracer):
        """Test setup with both disabled."""
        status = setup_observability(
            enable_tracing=False,
            enable_metrics=False,
        )

        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer", side_effect=Exception("Tracer init failed"))
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_tracer_init_failure(self, mock_init_metrics, mock_init_tracer):
        """Test setup when tracer initialization fails."""
        status = setup_observability(
            enable_tracing=True,
            enable_metrics=False,
        )

        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics", side_effect=Exception("Metrics init failed"))
    def test_setup_metrics_init_failure(self, mock_init_metrics, mock_init_tracer):
        """Test setup when metrics initialization fails."""
        mock_tracer = MagicMock()
        mock_init_tracer.return_value = mock_tracer

        status = setup_observability(
            enable_tracing=True,
            enable_metrics=True,
        )

        assert status["tracing_enabled"] is True
        assert status["metrics_enabled"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    @patch("chuk_tool_processor.observability.setup.start_metrics_server", side_effect=Exception("Server failed"))
    def test_setup_metrics_server_failure(self, mock_start_server, mock_init_metrics, mock_init_tracer):
        """Test setup when metrics server fails to start."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics.return_value = mock_metrics

        status = setup_observability(
            enable_tracing=False,
            enable_metrics=True,
        )

        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_metrics_disabled(self, mock_init_metrics, mock_init_tracer):
        """Test setup when metrics are disabled."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = False
        mock_init_metrics.return_value = mock_metrics

        status = setup_observability(
            enable_tracing=False,
            enable_metrics=True,
        )

        assert status["metrics_enabled"] is False
        assert status["metrics_server_started"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_tracer_returns_none(self, mock_init_metrics, mock_init_tracer):
        """Test setup when tracer returns None."""
        mock_init_tracer.return_value = None

        status = setup_observability(enable_tracing=True, enable_metrics=False)

        assert status["tracing_enabled"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_metrics_returns_none(self, mock_init_metrics, mock_init_tracer):
        """Test setup when metrics returns None."""
        mock_init_metrics.return_value = None

        status = setup_observability(enable_tracing=False, enable_metrics=True)

        assert status["metrics_enabled"] is False

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    def test_setup_custom_service_name(self, mock_init_metrics, mock_init_tracer):
        """Test setup with custom service name."""
        mock_tracer = MagicMock()
        mock_init_tracer.return_value = mock_tracer

        setup_observability(service_name="my-custom-service", enable_tracing=True, enable_metrics=False)

        mock_init_tracer.assert_called_once_with(service_name="my-custom-service")

    @patch("chuk_tool_processor.observability.setup.init_tracer")
    @patch("chuk_tool_processor.observability.setup.init_metrics")
    @patch("chuk_tool_processor.observability.setup.start_metrics_server")
    def test_setup_custom_metrics_port_and_host(self, mock_start_server, mock_init_metrics, mock_init_tracer):
        """Test setup with custom metrics port and host."""
        mock_metrics = MagicMock()
        mock_metrics.enabled = True
        mock_init_metrics.return_value = mock_metrics

        setup_observability(
            enable_tracing=False,
            enable_metrics=True,
            metrics_port=8080,
            metrics_host="127.0.0.1",
        )

        mock_start_server.assert_called_once_with(port=8080, host="127.0.0.1")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
