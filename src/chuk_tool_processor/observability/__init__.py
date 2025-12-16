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

    # Enable trace recording for replay
    from chuk_tool_processor.observability import init_trace_sink, InMemoryTraceSink

    init_trace_sink("memory")
    # or
    sink = InMemoryTraceSink()
    set_trace_sink(sink)
"""

from __future__ import annotations

from .metrics import PrometheusMetrics, get_metrics
from .setup import setup_observability
from .trace_sink import (
    BaseTraceSink,
    CompositeTraceSink,
    FileTraceSink,
    InMemoryTraceSink,
    NoOpTraceSink,
    SpanQuery,
    TraceQuery,
    TraceSink,
    TraceSinkStats,
    get_trace_sink,
    init_trace_sink,
    set_trace_sink,
)
from .tracing import get_tracer

__all__ = [
    # Setup
    "setup_observability",
    # Tracing (OpenTelemetry)
    "get_tracer",
    # Metrics (Prometheus)
    "get_metrics",
    "PrometheusMetrics",
    # Trace sink (execution recording)
    "TraceSink",
    "BaseTraceSink",
    "InMemoryTraceSink",
    "FileTraceSink",
    "CompositeTraceSink",
    "NoOpTraceSink",
    "SpanQuery",
    "TraceQuery",
    "TraceSinkStats",
    "get_trace_sink",
    "set_trace_sink",
    "init_trace_sink",
]
