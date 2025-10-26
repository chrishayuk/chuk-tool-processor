"""
Tests for Prometheus metrics integration.
"""

import pytest


# Test that metrics module can be imported
def test_metrics_import():
    """Test that metrics module imports successfully."""
    from chuk_tool_processor.observability import metrics

    assert metrics is not None


def test_get_metrics_without_init():
    """Test get_metrics returns None when not initialized."""
    from chuk_tool_processor.observability.metrics import get_metrics

    # Should return None if not initialized
    assert get_metrics() is None


def test_init_metrics():
    """Test metrics initialization."""
    from chuk_tool_processor.observability.metrics import init_metrics

    metrics = init_metrics()
    assert metrics is not None


# Only run Prometheus tests if prometheus-client is installed
pytest.importorskip("prometheus_client", reason="prometheus-client not installed")


@pytest.mark.skip(reason="Skipping to avoid duplicate metrics in test suite - init tested via other tests")
def test_prometheus_metrics_initialization():
    """Test PrometheusMetrics initialization."""
    from prometheus_client import CollectorRegistry

    from chuk_tool_processor.observability.metrics import PrometheusMetrics

    # Use a custom registry to avoid duplicate metric errors
    _ = CollectorRegistry()

    # Monkey-patch to use custom registry (simplified for testing)
    # In production, metrics are created once globally
    metrics = PrometheusMetrics()

    # Check that metrics object was created
    assert metrics is not None
    assert hasattr(metrics, "_initialized")


def test_record_tool_execution():
    """Test recording tool execution metrics."""
    from chuk_tool_processor.observability.metrics import get_metrics, init_metrics

    # Use global metrics instance to avoid duplicates
    metrics = get_metrics()
    if not metrics:
        metrics = init_metrics()

    # Record successful execution
    metrics.record_tool_execution(tool="test_tool_exec", namespace="default", duration=1.5, success=True, cached=False)

    # Record failed execution
    metrics.record_tool_execution(tool="test_tool_exec", namespace="default", duration=0.5, success=False, cached=False)

    # Should not raise errors
    assert True


def test_record_cache_operations():
    """Test recording cache operation metrics."""
    from chuk_tool_processor.observability.metrics import get_metrics, init_metrics

    metrics = get_metrics()
    if not metrics:
        metrics = init_metrics()

    # Record cache hit
    metrics.record_cache_operation(tool="test_tool_cache", operation="lookup", hit=True)

    # Record cache miss
    metrics.record_cache_operation(tool="test_tool_cache", operation="lookup", hit=False)

    # Record cache set
    metrics.record_cache_operation(tool="test_tool_cache", operation="set")

    # Should not raise errors
    assert True


def test_record_retry_attempts():
    """Test recording retry attempt metrics."""
    from chuk_tool_processor.observability.metrics import get_metrics, init_metrics

    metrics = get_metrics()
    if not metrics:
        metrics = init_metrics()

    # Record successful retry
    metrics.record_retry_attempt(tool="test_tool_retry", attempt=1, success=True)

    # Record failed retry
    metrics.record_retry_attempt(tool="test_tool_retry", attempt=2, success=False)

    # Should not raise errors
    assert True


def test_record_circuit_breaker_state():
    """Test recording circuit breaker state metrics."""
    from chuk_tool_processor.observability.metrics import get_metrics, init_metrics

    metrics = get_metrics()
    if not metrics:
        metrics = init_metrics()

    # Record CLOSED state
    metrics.record_circuit_breaker_state(tool="test_tool_cb", state="CLOSED")

    # Record OPEN state
    metrics.record_circuit_breaker_state(tool="test_tool_cb", state="OPEN")

    # Record HALF_OPEN state
    metrics.record_circuit_breaker_state(tool="test_tool_cb", state="HALF_OPEN")

    # Should not raise errors
    assert True


def test_record_rate_limit_checks():
    """Test recording rate limit check metrics."""
    from chuk_tool_processor.observability.metrics import get_metrics, init_metrics

    metrics = get_metrics()
    if not metrics:
        metrics = init_metrics()

    # Record allowed check
    metrics.record_rate_limit_check(tool="test_tool_rl", allowed=True)

    # Record blocked check
    metrics.record_rate_limit_check(tool="test_tool_rl", allowed=False)

    # Should not raise errors
    assert True


def test_metrics_timer():
    """Test MetricsTimer context manager."""
    import time

    from chuk_tool_processor.observability.metrics import MetricsTimer

    with MetricsTimer() as timer:
        time.sleep(0.1)

    # Should have recorded duration
    assert timer.duration >= 0.1
    assert timer.duration < 0.2  # Should be close to 0.1s
