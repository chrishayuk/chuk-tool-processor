"""
Tests for observability setup.
"""

import pytest


def test_setup_import():
    """Test that setup module imports successfully."""
    from chuk_tool_processor.observability import setup

    assert setup is not None


def test_setup_observability_import():
    """Test that setup_observability function can be imported."""
    from chuk_tool_processor.observability import setup_observability

    assert setup_observability is not None
    assert callable(setup_observability)


# Only run full setup tests if OTEL packages are installed
pytest.importorskip("opentelemetry", reason="opentelemetry not installed")
pytest.importorskip("prometheus_client", reason="prometheus-client not installed")


def test_setup_observability_both_disabled():
    """Test setup_observability with both tracing and metrics disabled."""
    from chuk_tool_processor.observability import setup_observability

    status = setup_observability(service_name="test-service", enable_tracing=False, enable_metrics=False)

    assert isinstance(status, dict)
    assert "tracing_enabled" in status
    assert "metrics_enabled" in status
    assert "metrics_server_started" in status


def test_setup_observability_tracing_only():
    """Test setup_observability with only tracing enabled."""
    from chuk_tool_processor.observability import setup_observability

    status = setup_observability(service_name="test-service", enable_tracing=True, enable_metrics=False)

    assert isinstance(status, dict)
    assert "tracing_enabled" in status
    assert "metrics_enabled" in status
    assert status["metrics_enabled"] is False


def test_setup_observability_metrics_only():
    """Test setup_observability with only metrics enabled."""
    from chuk_tool_processor.observability import setup_observability

    # Use a different port to avoid conflicts
    status = setup_observability(
        service_name="test-service", enable_tracing=False, enable_metrics=True, metrics_port=9091
    )

    assert isinstance(status, dict)
    assert "tracing_enabled" in status
    assert "metrics_enabled" in status
    assert "metrics_server_started" in status
    assert status["tracing_enabled"] is False


def test_setup_observability_full():
    """Test setup_observability with both tracing and metrics enabled."""
    from chuk_tool_processor.observability import setup_observability

    # Use a different port to avoid conflicts
    status = setup_observability(
        service_name="test-service", enable_tracing=True, enable_metrics=True, metrics_port=9092
    )

    assert isinstance(status, dict)
    assert "tracing_enabled" in status
    assert "metrics_enabled" in status
    assert "metrics_server_started" in status


def test_setup_observability_tracing_error_handling():
    """Test setup_observability handles tracing initialization errors (lines 69-70)."""
    from unittest.mock import patch

    from chuk_tool_processor.observability import setup_observability

    # Mock init_tracer to raise an exception
    with patch("chuk_tool_processor.observability.setup.init_tracer", side_effect=Exception("Test error")):
        status = setup_observability(service_name="test-service", enable_tracing=True, enable_metrics=False)

        assert isinstance(status, dict)
        assert status["tracing_enabled"] is False
        assert "metrics_enabled" in status


def test_setup_observability_metrics_error_handling():
    """Test setup_observability handles metrics initialization errors (lines 76-85)."""
    from unittest.mock import MagicMock, patch

    from chuk_tool_processor.observability import setup_observability

    # Mock init_metrics to raise an exception
    with patch("chuk_tool_processor.observability.setup.init_metrics", side_effect=Exception("Test error")):
        status = setup_observability(service_name="test-service", enable_tracing=False, enable_metrics=True)

        assert isinstance(status, dict)
        assert status["metrics_enabled"] is False

    # Test metrics server start failure (line 85)
    mock_metrics = MagicMock()
    mock_metrics.enabled = True

    with (
        patch("chuk_tool_processor.observability.setup.init_metrics", return_value=mock_metrics),
        patch("chuk_tool_processor.observability.setup.start_metrics_server", side_effect=Exception("Server error")),
    ):
        status = setup_observability(service_name="test-service", enable_tracing=False, enable_metrics=True)

        assert isinstance(status, dict)
        # Metrics should be enabled but server failed to start
        assert status["metrics_enabled"] is True
        assert status["metrics_server_started"] is False


def test_setup_observability_no_features_warning():
    """Test setup_observability logs warning when no features enabled (line 96)."""
    from unittest.mock import patch

    from chuk_tool_processor.observability import setup_observability

    # Mock both to return None/False to trigger the warning path
    with (
        patch("chuk_tool_processor.observability.setup.init_tracer", return_value=None),
        patch("chuk_tool_processor.observability.setup.init_metrics") as mock_metrics,
    ):
        mock_metrics_instance = mock_metrics.return_value
        mock_metrics_instance.enabled = False

        # Disable both features
        status = setup_observability(service_name="test-service", enable_tracing=False, enable_metrics=False)

        assert isinstance(status, dict)
        assert status["tracing_enabled"] is False
        assert status["metrics_enabled"] is False
