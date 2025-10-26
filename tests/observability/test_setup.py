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
