# OpenTelemetry & Prometheus Observability

This document describes the drop-in OpenTelemetry and Prometheus observability features added to chuk-tool-processor.

## Overview

The observability integration provides:

- **OpenTelemetry distributed tracing** - Automatic span creation for all tool operations
- **Prometheus metrics** - Standard metrics exposed via HTTP endpoint
- **Zero-configuration setup** - Works out of the box with a single function call
- **Graceful degradation** - Optional dependencies, doesn't break if not installed

## Quick Start

```python
from chuk_tool_processor.observability import setup_observability

# Enable everything
setup_observability(
    service_name="my-service",
    enable_tracing=True,
    enable_metrics=True,
    metrics_port=9090
)

# All tool execution is now automatically instrumented!
```

## Installation

```bash
# Install observability dependencies
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client

# Or with uv
uv pip install chuk-tool-processor --group observability
```

## OpenTelemetry Spans

The following spans are automatically created:

### tool.execute
Main tool execution span with attributes:
- `tool.name` - Tool name
- `tool.namespace` - Tool namespace
- `tool.duration_ms` - Execution duration
- `tool.cached` - Whether result was cached
- `tool.error` - Error message if failed

### tool.cache.lookup
Cache lookup operation with attributes:
- `tool.name` - Tool name
- `cache.hit` - Whether cache hit (true/false)
- `cache.operation` - Operation type ("lookup")

### tool.cache.set
Cache write operation with attributes:
- `tool.name` - Tool name
- `cache.ttl` - Time-to-live in seconds
- `cache.operation` - Operation type ("set")

### tool.retry.attempt
Retry attempt span with attributes:
- `tool.name` - Tool name
- `retry.attempt` - Current attempt number
- `retry.max_attempts` - Maximum retry attempts

### tool.circuit_breaker.check
Circuit breaker state check with attributes:
- `tool.name` - Tool name
- `circuit.state` - Current state (CLOSED/OPEN/HALF_OPEN)

### tool.rate_limit.check
Rate limiting check with attributes:
- `tool.name` - Tool name
- `rate_limit.allowed` - Whether request was allowed

## Prometheus Metrics

The following metrics are exposed at `http://localhost:9090/metrics`:

### Counters
- `tool_executions_total{tool,namespace,status}` - Total tool executions
- `tool_cache_operations_total{tool,operation,result}` - Total cache operations
- `tool_retry_attempts_total{tool,attempt,success}` - Total retry attempts
- `tool_circuit_breaker_failures_total{tool}` - Total circuit breaker failures
- `tool_rate_limit_checks_total{tool,allowed}` - Total rate limit checks

### Histograms
- `tool_execution_duration_seconds{tool,namespace}` - Tool execution duration

### Gauges
- `tool_circuit_breaker_state{tool}` - Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)

## Architecture

The observability integration is designed to be:

1. **Non-intrusive**: Uses optional imports and gracefully degrades
2. **Zero-overhead**: No-op when not enabled
3. **Drop-in**: No code changes required to existing tools
4. **Composable**: Works with all execution wrappers (cache, retry, circuit breaker, rate limit)

### Implementation Details

Each execution wrapper includes optional observability code:

```python
# Optional observability imports
try:
    from chuk_tool_processor.observability.metrics import get_metrics
    from chuk_tool_processor.observability.tracing import trace_cache_operation
    _observability_available = True
except ImportError:
    _observability_available = False
    # No-op functions when not available
    def get_metrics():
        return None
    def trace_cache_operation(*args, **kwargs):
        from contextlib import nullcontext
        return nullcontext()
```

This pattern ensures:
- No import errors if dependencies not installed
- No runtime overhead when disabled
- Automatic instrumentation when enabled

## Example Usage

See `examples/observability_demo.py` for a complete working example demonstrating:
- Tracing and metrics setup
- Tool execution with retries
- Cache hits and misses
- Circuit breaker state tracking
- Rate limiting checks

## Integration with Existing Systems

### Jaeger (Trace Visualization)

```bash
# Start Jaeger
docker run -d -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest

# View traces at http://localhost:16686
```

### Grafana + Prometheus

```bash
# Scrape metrics from http://localhost:9090/metrics
# Import Grafana dashboard for visualization
```

### OTEL Collector

Configure via environment variables:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
export OTEL_SERVICE_NAME=my-service
```

## Environment Variables

- `OTEL_EXPORTER_OTLP_ENDPOINT` - OTLP endpoint (default: `http://localhost:4317`)
- `OTEL_SERVICE_NAME` - Service name (overrides `service_name` parameter)

## Testing

Tests are located in `tests/observability/`:
- `test_metrics.py` - Prometheus metrics tests
- `test_tracing.py` - OpenTelemetry tracing tests
- `test_setup.py` - Setup and integration tests

Run tests:
```bash
pytest tests/observability/
```

## Benefits

✅ **Drop-in**: One function call to enable full observability
✅ **Production-ready**: Standard OTEL + Prometheus metrics
✅ **Automatic**: All wrappers automatically instrumented
✅ **Zero-config**: Works out of the box
✅ **Optional**: Gracefully degrades if packages not installed
✅ **Ops-friendly**: Standard metrics ops teams expect

## Future Enhancements

Potential future additions:
- Custom metric exporters (StatsD, DataDog, etc.)
- Trace sampling configuration
- Custom span attributes via tool metadata
- Baggage propagation for distributed tracing
- Health check endpoint integration
