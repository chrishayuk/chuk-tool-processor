# Telemetry & Observability Guide

## Overview

`chuk-tool-processor` provides **production-ready telemetry** through OpenTelemetry distributed tracing and Prometheus metrics. This guide explains how to instrument, monitor, and troubleshoot your tool executions in production environments.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [OpenTelemetry Tracing](#opentelemetry-tracing)
- [Prometheus Metrics](#prometheus-metrics)
- [Integration Patterns](#integration-patterns)
- [Production Setup](#production-setup)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Quick Start

### Enable Full Observability (One Line)

```python
from chuk_tool_processor.observability import setup_observability

# Enable everything with defaults
setup_observability(
    service_name="my-service",
    enable_tracing=True,
    enable_metrics=True,
    metrics_port=9090
)
```

**That's it!** All tool executions are now automatically instrumented with:
- Distributed traces sent to OTLP endpoint (default: `localhost:4317`)
- Prometheus metrics at `http://localhost:9090/metrics`

### Verify It's Working

```bash
# Check Prometheus metrics
curl http://localhost:9090/metrics | grep tool_

# Start Jaeger to view traces
docker run -d -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest
# Visit http://localhost:16686
```

---

## Installation

### With Observability Dependencies

```bash
# Using pip
pip install chuk-tool-processor[observability]

# Using uv (recommended)
uv pip install chuk-tool-processor --group observability
```

### Manual Installation

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client
```

### Optional: Graceful Degradation

If you don't install the observability packages, the library **still works** - telemetry is simply disabled. No errors, no overhead.

---

## OpenTelemetry Tracing

### What Gets Traced?

Every tool execution automatically creates **distributed trace spans** with rich contextual attributes.

### Span Hierarchy

```
tool.execute (root span)
├── tool.cache.lookup (if caching enabled)
├── tool.retry.attempt (if retries configured)
│   └── tool.execute (nested for retry)
├── tool.circuit_breaker.check (if circuit breaker enabled)
└── tool.rate_limit.check (if rate limiting enabled)
```

### Span Details

#### `tool.execute`
Main execution span for every tool call.

**Attributes:**
- `tool.name` - Tool name (e.g., `"calculator"`)
- `tool.namespace` - Tool namespace (e.g., `"math"`)
- `tool.duration_ms` - Execution duration in milliseconds
- `tool.cached` - Whether result came from cache (`true`/`false`)
- `tool.error` - Error message if execution failed
- `tool.success` - Whether execution succeeded (`true`/`false`)

**Example trace:**
```json
{
  "name": "tool.execute",
  "attributes": {
    "tool.name": "calculator",
    "tool.namespace": "math",
    "tool.duration_ms": 125.3,
    "tool.cached": false,
    "tool.success": true
  }
}
```

#### `tool.cache.lookup`
Cache lookup operation span.

**Attributes:**
- `tool.name` - Tool name
- `cache.hit` - Whether cache hit (`true`/`false`)
- `cache.operation` - Always `"lookup"`

#### `tool.cache.set`
Cache write operation span.

**Attributes:**
- `tool.name` - Tool name
- `cache.ttl` - Time-to-live in seconds
- `cache.operation` - Always `"set"`

#### `tool.retry.attempt`
Retry attempt span (created for each retry).

**Attributes:**
- `tool.name` - Tool name
- `retry.attempt` - Current attempt number (0-indexed)
- `retry.max_attempts` - Maximum configured retries
- `retry.success` - Whether this attempt succeeded

#### `tool.circuit_breaker.check`
Circuit breaker state check span.

**Attributes:**
- `tool.name` - Tool name
- `circuit.state` - Current state (`CLOSED`/`OPEN`/`HALF_OPEN`)
- `circuit.failure_count` - Number of consecutive failures (if applicable)

#### `tool.rate_limit.check`
Rate limiting check span.

**Attributes:**
- `tool.name` - Tool name
- `rate_limit.allowed` - Whether request was allowed (`true`/`false`)
- `rate_limit.reason` - Reason if blocked (e.g., `"global_limit"`, `"tool_limit"`)

### Configuration

#### Basic Configuration

```python
from chuk_tool_processor.observability import setup_observability

setup_observability(
    service_name="my-api",
    enable_tracing=True
)
```

#### Advanced Configuration (Environment Variables)

```bash
# OTLP endpoint (default: http://localhost:4317)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

# Service name (overrides code)
export OTEL_SERVICE_NAME=production-api

# Sampling (1.0 = 100%, 0.1 = 10%)
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

#### Custom Tracer Usage

```python
from chuk_tool_processor.observability.tracing import get_tracer, trace_tool_execution

tracer = get_tracer()

# Manual span creation
with tracer.start_as_current_span("custom.operation") as span:
    span.set_attribute("custom.key", "value")
    # ... your code ...

# Or use helper context managers
with trace_tool_execution("my_tool", namespace="custom", attributes={"version": "1.0"}):
    # ... tool execution ...
    pass
```

---

## Prometheus Metrics

### Available Metrics

All metrics follow Prometheus naming conventions and include standard labels for filtering/aggregation.

#### Counters

**`tool_executions_total{tool, namespace, status}`**
- Total number of tool executions
- Labels:
  - `tool` - Tool name
  - `namespace` - Tool namespace
  - `status` - `"success"` or `"error"`

**`tool_cache_operations_total{tool, operation, result}`**
- Total cache operations
- Labels:
  - `tool` - Tool name
  - `operation` - `"lookup"` or `"set"`
  - `result` - `"hit"`, `"miss"`, or `"set"`

**`tool_retry_attempts_total{tool, attempt, success}`**
- Total retry attempts
- Labels:
  - `tool` - Tool name
  - `attempt` - Attempt number (e.g., `"0"`, `"1"`, `"2"`)
  - `success` - `"true"` or `"false"`

**`tool_circuit_breaker_failures_total{tool}`**
- Total circuit breaker failures
- Labels:
  - `tool` - Tool name

**`tool_rate_limit_checks_total{tool, allowed}`**
- Total rate limit checks
- Labels:
  - `tool` - Tool name
  - `allowed` - `"true"` or `"false"`

#### Histograms

**`tool_execution_duration_seconds{tool, namespace}`**
- Tool execution duration histogram
- Buckets: `.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, +Inf`
- Labels:
  - `tool` - Tool name
  - `namespace` - Tool namespace

**Usage:**
- `_sum` - Total execution time
- `_count` - Total executions
- `_bucket` - Distribution across latency buckets

#### Gauges

**`tool_circuit_breaker_state{tool}`**
- Current circuit breaker state
- Values:
  - `0` = CLOSED (healthy)
  - `1` = OPEN (failing)
  - `2` = HALF_OPEN (testing recovery)
- Labels:
  - `tool` - Tool name

### Metrics Endpoint

Metrics are exposed via HTTP at the configured port (default: `9090`):

```bash
# View all metrics
curl http://localhost:9090/metrics

# Filter for tool metrics
curl http://localhost:9090/metrics | grep ^tool_

# Scrape from Prometheus
# Add to prometheus.yml:
scrape_configs:
  - job_name: 'chuk-tool-processor'
    static_configs:
      - targets: ['localhost:9090']
```

### Useful Queries (PromQL)

```promql
# Average execution time per tool (last 5m)
rate(tool_execution_duration_seconds_sum[5m])
/ rate(tool_execution_duration_seconds_count[5m])

# Error rate per tool
rate(tool_executions_total{status="error"}[5m])
/ rate(tool_executions_total[5m])

# Cache hit rate
rate(tool_cache_operations_total{result="hit"}[5m])
/ rate(tool_cache_operations_total{operation="lookup"}[5m])

# P95 latency
histogram_quantile(0.95, rate(tool_execution_duration_seconds_bucket[5m]))

# Retry rate (how often tools need retries)
rate(tool_retry_attempts_total{attempt!="0"}[5m])
/ rate(tool_executions_total[5m])

# Circuit breaker currently open
tool_circuit_breaker_state == 1
```

---

## Integration Patterns

### With Jaeger (Distributed Tracing UI)

```bash
# Start Jaeger all-in-one
docker run -d \
  --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest

# Configure application
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Visit `http://localhost:16686` to view traces.

### With Grafana + Prometheus

**prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'chuk-tool-processor'
    scrape_interval: 15s
    static_configs:
      - targets: ['app:9090']
```

**Grafana Dashboards:**
- Import dashboard ID `15760` (Prometheus Stats)
- Create custom dashboard with PromQL queries above

### With OpenTelemetry Collector

**otel-collector-config.yaml:**
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  jaeger:
    endpoint: jaeger:14250
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger]
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

**Application configuration:**
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

### With Cloud Providers

#### AWS X-Ray

```python
from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
from chuk_tool_processor.observability.tracing import init_tracer

# Configure before setup_observability()
import os
os.environ['OTEL_TRACES_SAMPLER'] = 'xray'

# Then setup as normal
setup_observability(service_name="my-service")
```

#### Google Cloud Trace

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://cloudtrace.googleapis.com/v1/projects/PROJECT_ID/traces
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

#### Datadog

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4317
export DD_ENV=production
export DD_SERVICE=my-service
```

---

## Production Setup

### Recommended Configuration

```python
from chuk_tool_processor.observability import setup_observability

# Production setup
status = setup_observability(
    service_name="production-api",
    enable_tracing=True,
    enable_metrics=True,
    metrics_port=9090,
    metrics_host="0.0.0.0"  # Allow external scraping
)

# Verify setup
if not status["tracing_enabled"]:
    logger.warning("Tracing not available - install observability dependencies")

if not status["metrics_server_started"]:
    logger.error("Metrics server failed to start")
```

### Environment Variables

```bash
# Service identification
export OTEL_SERVICE_NAME=api-production
export OTEL_SERVICE_VERSION=1.2.3
export OTEL_DEPLOYMENT_ENVIRONMENT=production

# OTLP endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

# Sampling (reduce overhead in high-traffic scenarios)
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sampling

# Batch processing
export OTEL_BSP_MAX_QUEUE_SIZE=2048
export OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512
export OTEL_BSP_SCHEDULE_DELAY=5000  # ms
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  app:
    image: my-app:latest
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
      OTEL_SERVICE_NAME: my-service
    ports:
      - "9090:9090"  # Prometheus metrics
    depends_on:
      - otel-collector

  otel-collector:
    image: otel/opentelemetry-collector:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"  # OTLP gRPC

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9091:9090"  # Prometheus UI

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # Jaeger UI
      - "14250:14250"  # Accept traces from collector
```

### Kubernetes Setup

**deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
spec:
  template:
    metadata:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: app
        image: my-app:latest
        env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector:4317"
        - name: OTEL_SERVICE_NAME
          value: "my-service"
        - name: OTEL_K8S_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: OTEL_K8S_POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        ports:
        - containerPort: 9090
          name: metrics
```

---

## Troubleshooting

### Common Issues

#### 1. "No traces appearing in Jaeger"

**Check OTLP endpoint:**
```bash
# Verify collector is reachable
curl http://localhost:4317

# Check logs for connection errors
# Look for: "Failed to export traces"
```

**Verify tracing is enabled:**
```python
from chuk_tool_processor.observability.tracing import is_tracing_enabled

print(f"Tracing enabled: {is_tracing_enabled()}")
```

**Check environment variables:**
```bash
echo $OTEL_EXPORTER_OTLP_ENDPOINT
echo $OTEL_SERVICE_NAME
```

#### 2. "Metrics endpoint returns 404"

**Verify metrics server started:**
```python
status = setup_observability(enable_metrics=True, metrics_port=9090)
print(status["metrics_server_started"])  # Should be True
```

**Check port binding:**
```bash
# Is something else using port 9090?
lsof -i :9090

# Try different port
setup_observability(metrics_port=9091)
```

#### 3. "Duplicate metric error"

This happens if you call `init_metrics()` multiple times. Solution:

```python
from chuk_tool_processor.observability.metrics import get_metrics

# Always use get_metrics() - it returns singleton
metrics = get_metrics()

# Only init if not already initialized
if not metrics:
    from chuk_tool_processor.observability import setup_observability
    setup_observability()
```

#### 4. "High memory usage from telemetry"

**Reduce sampling:**
```bash
# Sample only 10% of traces
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

**Reduce batch sizes:**
```bash
export OTEL_BSP_MAX_QUEUE_SIZE=512
export OTEL_BSP_MAX_EXPORT_BATCH_SIZE=128
```

**Use histogram buckets wisely:**
The default buckets are optimized for typical tool execution times. If your tools are much faster/slower, you may get better distribution with custom buckets (requires code change).

#### 5. "Import errors for opentelemetry/prometheus"

**Check installation:**
```bash
pip list | grep opentelemetry
pip list | grep prometheus

# Install if missing
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp prometheus-client
```

**Graceful degradation:**
If you don't need telemetry, it's safe to not install these packages - the library will work fine without them.

### Debug Mode

Enable debug logging to see what's happening:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("chuk_tool_processor.observability")
logger.setLevel(logging.DEBUG)

# Now run setup
setup_observability(service_name="debug-test")
```

---

## Best Practices

### 1. Use Meaningful Service Names

```python
# Good - identifies service and environment
setup_observability(service_name="user-api-production")

# Bad - generic names make filtering hard
setup_observability(service_name="app")
```

### 2. Tag Spans with Context

```python
from chuk_tool_processor.observability.tracing import trace_tool_execution

with trace_tool_execution(
    "calculator",
    namespace="math",
    attributes={
        "user.id": user_id,
        "request.id": request_id,
        "version": "2.0"
    }
):
    # ... execution ...
    pass
```

### 3. Monitor Error Rates

Set up alerts on:
```promql
# Error rate > 5%
rate(tool_executions_total{status="error"}[5m])
/ rate(tool_executions_total[5m]) > 0.05

# Circuit breaker open
tool_circuit_breaker_state == 1

# High retry rate
rate(tool_retry_attempts_total{attempt!="0"}[5m]) > 10
```

### 4. Use Sampling in Production

```bash
# Don't trace every request in high-traffic services
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10%
```

### 5. Correlate Traces with Logs

```python
from chuk_tool_processor.logging import get_logger
from opentelemetry import trace

logger = get_logger("my-tool")

# Add trace context to logs
span = trace.get_current_span()
trace_id = span.get_span_context().trace_id
logger.info(f"Processing request", extra={"trace_id": trace_id})
```

### 6. Dashboard Key Metrics

Create dashboards with:
- **RED metrics** (Rate, Errors, Duration) per tool
- Cache hit rates
- Retry rates
- Circuit breaker states
- P95/P99 latencies

### 7. Test Observability in CI/CD

```python
# tests/test_observability.py
def test_telemetry_setup():
    """Ensure observability can be initialized."""
    from chuk_tool_processor.observability import setup_observability

    status = setup_observability(
        service_name="test",
        enable_tracing=True,
        enable_metrics=True,
        metrics_port=9999  # Use non-standard port for tests
    )

    assert status["tracing_enabled"] or status["metrics_enabled"]
```

---

## Additional Resources

- **OpenTelemetry Docs**: https://opentelemetry.io/docs/
- **Prometheus Docs**: https://prometheus.io/docs/
- **Example Code**: `examples/observability_demo.py`
- **Architecture Details**: `OBSERVABILITY.md`

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-repo/chuk-tool-processor/issues
- Documentation: `README.md`, `OBSERVABILITY.md`

---

**Happy monitoring!** 📊🔍
