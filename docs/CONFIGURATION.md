# Configuration Reference

Complete reference for all configuration options in CHUK Tool Processor.

## Table of Contents

- [ToolProcessor Configuration](#toolprocessor-configuration)
- [Timeout Configuration](#timeout-configuration)
- [Environment Variables](#environment-variables)
- [Retry Policy Configuration](#retry-policy-configuration)
- [Rate Limiting Configuration](#rate-limiting-configuration)
- [Circuit Breaker Configuration](#circuit-breaker-configuration)
- [Cache Configuration](#cache-configuration)

---

## ToolProcessor Configuration

All configuration options for the `ToolProcessor` class.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `strategy` | `ExecutionStrategy` | `InProcessStrategy()` | Execution strategy (InProcess or Subprocess) |
| `default_timeout` | `float` | `30.0` | Default timeout for tool execution (seconds) |
| `max_concurrency` | `int` | `10` | Maximum concurrent tool executions |
| `enable_caching` | `bool` | `True` | Enable result caching |
| `cache_ttl` | `int` | `300` | Cache time-to-live (seconds) |
| `enable_rate_limiting` | `bool` | `False` | Enable rate limiting |
| `global_rate_limit` | `int \| None` | `None` | Global rate limit (requests/minute) |
| `tool_rate_limits` | `dict[str, tuple[int, int]] \| None` | `None` | Per-tool rate limits: `{"tool_name": (max_requests, window_seconds)}` |
| `enable_retries` | `bool` | `True` | Enable automatic retries on failure |
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `retry_delay` | `float` | `1.0` | Initial retry delay (seconds) |
| `retry_backoff` | `float` | `2.0` | Exponential backoff multiplier |
| `enable_circuit_breaker` | `bool` | `False` | Enable circuit breaker pattern |
| `circuit_breaker_threshold` | `int` | `5` | Failures before circuit opens |
| `circuit_breaker_timeout` | `float` | `60.0` | Circuit reset timeout (seconds) |

### Example: Basic Configuration

```python
from chuk_tool_processor.core.processor import ToolProcessor

processor = ToolProcessor(
    default_timeout=30.0,
    max_concurrency=20,
    enable_caching=True,
    cache_ttl=600
)
```

### Example: Production Configuration

```python
processor = ToolProcessor(
    # Execution
    default_timeout=30.0,
    max_concurrency=20,

    # Caching
    enable_caching=True,
    cache_ttl=600,  # 10 minutes

    # Rate Limiting
    enable_rate_limiting=True,
    global_rate_limit=100,  # 100 req/min globally
    tool_rate_limits={
        "expensive_api": (10, 60),  # 10 requests per minute
        "local_tool": (1000, 60)    # 1000 requests per minute
    },

    # Retries
    enable_retries=True,
    max_retries=3,
    retry_delay=1.0,
    retry_backoff=2.0,

    # Circuit Breaker
    enable_circuit_breaker=True,
    circuit_breaker_threshold=5,
    circuit_breaker_timeout=60.0
)
```

---

## Timeout Configuration

Unified timeout configuration for MCP transports and StreamManager.

| Category | Default | Used For |
|----------|---------|----------|
| `connect` | `30.0s` | Connection establishment, initialization, session discovery |
| `operation` | `30.0s` | Normal operations (tool calls, listing tools/resources/prompts) |
| `quick` | `5.0s` | Fast health checks and pings |
| `shutdown` | `2.0s` | Cleanup and shutdown operations |

### Example: TimeoutConfig

```python
from chuk_tool_processor.mcp.transport import TimeoutConfig

timeout_config = TimeoutConfig(
    connect=60.0,     # Longer for slow initialization
    operation=45.0,   # Longer for heavy operations
    quick=3.0,        # Faster health checks
    shutdown=5.0      # More time for cleanup
)
```

### Example: Using with StreamManager

```python
from chuk_tool_processor.mcp.stream_manager import StreamManager

manager = StreamManager(timeout_config=timeout_config)
```

### Example: Using with MCP Setup

```python
from chuk_tool_processor.mcp import setup_mcp_stdio

processor, manager = await setup_mcp_stdio(
    config_file="mcp_config.json",
    servers=["sqlite"],
    namespace="db",
    initialization_timeout=120.0  # Separate init timeout
)

# Set custom timeouts on the manager
manager.timeout_config = timeout_config
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUK_TOOL_REGISTRY_PROVIDER` | `memory` | Registry backend (`memory` only currently) |
| `CHUK_DEFAULT_TIMEOUT` | `30.0` | Default timeout for tool execution (seconds) |
| `CHUK_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CHUK_STRUCTURED_LOGGING` | `true` | Enable JSON logging (`true`/`false`) |
| `MCP_BEARER_TOKEN` | - | Bearer token for MCP SSE authentication |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OpenTelemetry collector endpoint |
| `OTEL_SERVICE_NAME` | `chuk-tool-processor` | Service name for traces/metrics |
| `OTEL_TRACES_SAMPLER` | `always_on` | Trace sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | - | Sampler argument (e.g., `0.1` for 10% sampling) |

### Example: Setting Environment Variables

```bash
# Logging
export CHUK_LOG_LEVEL=DEBUG
export CHUK_STRUCTURED_LOGGING=true

# Timeouts
export CHUK_DEFAULT_TIMEOUT=60.0

# OpenTelemetry
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
export OTEL_SERVICE_NAME=production-api
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

---

## Retry Policy Configuration

Retry behavior is controlled by three parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | `3` | Maximum retry attempts (0 = no retries) |
| `retry_delay` | `1.0` | Initial delay between retries (seconds) |
| `retry_backoff` | `2.0` | Exponential backoff multiplier |

### Retry Delay Calculation

```
delay = retry_delay * (retry_backoff ** attempt)
```

**Examples:**
- Attempt 1: 1.0 * (2.0 ** 0) = 1.0s
- Attempt 2: 1.0 * (2.0 ** 1) = 2.0s
- Attempt 3: 1.0 * (2.0 ** 2) = 4.0s

### Example: Conservative Retry Policy

```python
processor = ToolProcessor(
    enable_retries=True,
    max_retries=5,
    retry_delay=2.0,
    retry_backoff=1.5
)
```

### Example: Aggressive Retry Policy

```python
processor = ToolProcessor(
    enable_retries=True,
    max_retries=2,
    retry_delay=0.5,
    retry_backoff=3.0
)
```

### Example: Disable Retries

```python
processor = ToolProcessor(
    enable_retries=False
)
```

---

## Rate Limiting Configuration

Rate limiting uses a sliding window algorithm.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_rate_limiting` | `False` | Enable rate limiting |
| `global_rate_limit` | `None` | Global limit (requests/minute) across all tools |
| `tool_rate_limits` | `None` | Per-tool limits: `{"tool_name": (max_requests, window_seconds)}` |

### Rate Limit Priority

1. **Per-tool limits** override global limits
2. **Global limit** applies to tools without specific limits
3. **No limit** if rate limiting is disabled or no limits configured

### Example: Global Rate Limit

```python
processor = ToolProcessor(
    enable_rate_limiting=True,
    global_rate_limit=100  # 100 requests/minute across all tools
)
```

### Example: Per-Tool Rate Limits

```python
processor = ToolProcessor(
    enable_rate_limiting=True,
    global_rate_limit=100,  # Default for all tools
    tool_rate_limits={
        "notion.search_pages": (10, 60),    # 10 per minute
        "expensive_api": (5, 60),           # 5 per minute
        "local_calculator": (1000, 60)      # 1000 per minute
    }
)
```

### Example: Different Time Windows

```python
processor = ToolProcessor(
    enable_rate_limiting=True,
    tool_rate_limits={
        "fast_api": (100, 10),    # 100 requests per 10 seconds
        "slow_api": (50, 300),    # 50 requests per 5 minutes
        "hourly_api": (1000, 3600)  # 1000 requests per hour
    }
)
```

---

## Circuit Breaker Configuration

Circuit breaker prevents cascading failures by temporarily blocking requests to failing tools.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_circuit_breaker` | `False` | Enable circuit breaker pattern |
| `circuit_breaker_threshold` | `5` | Number of failures before circuit opens |
| `circuit_breaker_timeout` | `60.0` | Time (seconds) before attempting recovery |

### Circuit States

1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Too many failures, requests blocked immediately
3. **HALF_OPEN**: Testing recovery with limited requests

### State Transitions

```
CLOSED --[threshold failures]--> OPEN
OPEN --[timeout expires]--> HALF_OPEN
HALF_OPEN --[success]--> CLOSED
HALF_OPEN --[failure]--> OPEN
```

### Example: Conservative Circuit Breaker

```python
processor = ToolProcessor(
    enable_circuit_breaker=True,
    circuit_breaker_threshold=10,  # More tolerance
    circuit_breaker_timeout=120.0  # Longer recovery time
)
```

### Example: Aggressive Circuit Breaker

```python
processor = ToolProcessor(
    enable_circuit_breaker=True,
    circuit_breaker_threshold=3,   # Fail fast
    circuit_breaker_timeout=30.0   # Quick recovery attempts
)
```

---

## Cache Configuration

Result caching with TTL and automatic idempotency key generation.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_caching` | `True` | Enable result caching |
| `cache_ttl` | `300` | Cache time-to-live (seconds) |

### Cache Key Generation

Cache keys are automatically generated from:
1. Tool name
2. Tool arguments (deterministic serialization)
3. SHA256 hash

**Example cache key:**
```python
ToolCall(tool="search", arguments={"query": "Python"})
# → idempotency_key: "e3b0c44298fc1c149afbf4c8996fb924..."
```

### Example: Long-Lived Cache

```python
processor = ToolProcessor(
    enable_caching=True,
    cache_ttl=3600  # 1 hour
)
```

### Example: Short-Lived Cache

```python
processor = ToolProcessor(
    enable_caching=True,
    cache_ttl=60  # 1 minute
)
```

### Example: Disable Caching

```python
processor = ToolProcessor(
    enable_caching=False
)
```

---

## Performance Tuning Guide

### High-Throughput Scenario

```python
processor = ToolProcessor(
    max_concurrency=50,        # High concurrency
    default_timeout=10.0,      # Shorter timeouts
    enable_caching=True,       # Cache aggressively
    cache_ttl=300,
    enable_rate_limiting=True,
    global_rate_limit=500,     # High rate limit
    enable_retries=False       # Skip retries for speed
)
```

### High-Reliability Scenario

```python
processor = ToolProcessor(
    max_concurrency=10,            # Conservative concurrency
    default_timeout=60.0,          # Generous timeouts
    enable_caching=True,
    cache_ttl=600,
    enable_retries=True,
    max_retries=5,                 # More retries
    retry_delay=2.0,
    retry_backoff=1.5,
    enable_circuit_breaker=True,   # Prevent cascading failures
    circuit_breaker_threshold=10,
    circuit_breaker_timeout=120.0
)
```

### Cost-Optimized Scenario

```python
processor = ToolProcessor(
    enable_caching=True,
    cache_ttl=3600,            # Long cache for expensive calls
    enable_rate_limiting=True,
    global_rate_limit=50,      # Conservative rate limit
    enable_retries=True,
    max_retries=3,
    enable_circuit_breaker=True  # Avoid wasting credits
)
```

---

## See Also

- [README.md](../README.md) - Main documentation
- [OBSERVABILITY.md](../OBSERVABILITY.md) - Monitoring and observability
- [examples/](../examples/) - Configuration examples
