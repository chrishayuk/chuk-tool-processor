"""
OpenTelemetry observability integration for chuk-tool-processor.

This module provides drop-in OpenTelemetry tracing and Prometheus metrics
for tool execution, making it trivial to instrument your tool pipeline.

Example:
    from chuk_tool_processor.observability import setup_observability

    # Enable both tracing and metrics
    setup_observability(
        service_name="my-tool-service",
        enable_tracing=True,
        enable_metrics=True,
        metrics_port=9090
    )
"""

from __future__ import annotations

from .metrics import PrometheusMetrics, get_metrics
from .setup import setup_observability
from .tracing import get_tracer

__all__ = [
    "setup_observability",
    "get_tracer",
    "get_metrics",
    "PrometheusMetrics",
]
