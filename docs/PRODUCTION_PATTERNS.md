# Production Patterns

This guide covers production-grade patterns for building reliable, scalable tool execution systems.

## Table of Contents

- [Idempotency & Deduplication](#idempotency--deduplication)
- [Cancellation & Deadlines](#cancellation--deadlines)
- [Per-Tool Policy Overrides](#per-tool-policy-overrides)
- [Parallel Execution & Streaming](#parallel-execution--streaming)
- [Scoped Registries](#scoped-registries-multi-tenant-isolation)
- [Bulkheads](#bulkheads-per-tool-concurrency-limits)
- [ExecutionContext](#executioncontext-request-tracing)

---

## Idempotency & Deduplication

Automatically deduplicate LLM retry quirks using SHA256-based idempotency keys:

```python
from chuk_tool_processor import ToolProcessor, initialize

await initialize()
async with ToolProcessor(enable_caching=True, cache_ttl=300) as p:
    # LLM retries the same call (common with streaming or errors)
    call1 = '<tool name="search" args=\'{"query": "Python"}\'/>'
    call2 = '<tool name="search" args=\'{"query": "Python"}\'/>'  # Identical

    results1 = await p.process(call1)  # Executes
    results2 = await p.process(call2)  # Cache hit! (idempotency key match)

    assert results1[0].cached == False
    assert results2[0].cached == True
```

**How it works:**
- Tool name + arguments are hashed to create an idempotency key
- Identical calls within the cache TTL return cached results
- Prevents duplicate API calls from LLM retry behavior

---

## Cancellation & Deadlines

Cooperative cancellation with request-scoped deadlines:

```python
import asyncio
from chuk_tool_processor import ToolProcessor, initialize

async def main():
    await initialize()
    async with ToolProcessor(default_timeout=60.0) as p:
        try:
            # Hard deadline for the whole batch (e.g., user request budget)
            async with asyncio.timeout(5.0):
                async for event in p.astream('<tool name="slow_report" args=\'{"n": 1000000}\'/>'):
                    print("chunk:", event)
        except TimeoutError:
            print("Request cancelled: deadline exceeded")
            # Processor automatically cancels the tool and cleans up

asyncio.run(main())
```

**Features:**
- Timeout at processor level (`default_timeout`)
- Timeout at request level (`asyncio.timeout`)
- Automatic cleanup on cancellation
- Works with streaming results

---

## Per-Tool Policy Overrides

Override timeouts, retries, and rate limits per tool:

```python
from chuk_tool_processor import ToolProcessor, initialize

await initialize()
async with ToolProcessor(
    default_timeout=30.0,
    enable_retries=True,
    max_retries=2,
    enable_rate_limiting=True,
    global_rate_limit=120,  # 120 requests/min across all tools
    tool_rate_limits={
        "expensive_api": (5, 60),  # 5 requests per 60 seconds
        "fast_local": (1000, 60),  # 1000 requests per 60 seconds
    }
) as p:
    # Tools run with their specific policies
    results = await p.process('''
        <tool name="expensive_api" args='{"q":"abc"}'/>
        <tool name="fast_local" args='{"data":"xyz"}'/>
    ''')
```

**Configuration options:**
- `default_timeout`: Default timeout for all tools
- `tool_rate_limits`: Per-tool rate limits as `(requests, period_seconds)`
- `global_rate_limit`: System-wide rate limit
- `max_retries`: Maximum retry attempts for transient failures

See [CONFIGURATION.md](CONFIGURATION.md) for all options.

---

## Parallel Execution & Streaming

Tools execute concurrently by default. Results return in **completion order** — faster tools return immediately without waiting for slower ones:

```python
import asyncio
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall

# Tools with different execution times
calls = [
    ToolCall(tool="slow_api", arguments={"query": "complex"}),    # 500ms
    ToolCall(tool="medium_api", arguments={"query": "medium"}),   # 200ms
    ToolCall(tool="fast_api", arguments={"query": "simple"}),     # 50ms
]

# Results return as: fast_api, medium_api, slow_api (completion order)
results = await strategy.run(calls)

# Match results back to original calls by tool name
for result in results:
    print(f"{result.tool}: {result.result}")
```

### Stream results as they arrive

```python
async for result in strategy.stream_run(calls):
    # Process each result immediately as it completes
    print(f"Completed: {result.tool}")
```

### Track when tools start

```python
async def on_start(call: ToolCall):
    print(f"Starting: {call.tool}")

async for result in strategy.stream_run(calls, on_tool_start=on_start):
    print(f"Completed: {result.tool}")
```

### Control concurrency

```python
# Limit to 2 concurrent tools (others queue)
strategy = InProcessStrategy(registry, max_concurrency=2)
```

> **See:** `examples/parallel_execution_demo.py` for a complete demonstration.

---

## Scoped Registries (Multi-Tenant Isolation)

Create isolated tool registries for multi-tenant apps, testing, or plugin systems:

```python
from chuk_tool_processor import ToolProcessor, create_registry

# Each tenant gets their own isolated registry
tenant_a_registry = create_registry()
tenant_b_registry = create_registry()

# Register different tools per tenant
await tenant_a_registry.register_tool(BasicTool, name="basic")
await tenant_b_registry.register_tool(BasicTool, name="basic")
await tenant_b_registry.register_tool(PremiumTool, name="premium")  # Only tenant B

# Create processors with isolated registries
processor_a = ToolProcessor(registry=tenant_a_registry)
processor_b = ToolProcessor(registry=tenant_b_registry)

# Tenant A cannot access premium tools
tools_a = await processor_a.list_tools()  # ['basic']
tools_b = await processor_b.list_tools()  # ['basic', 'premium']
```

### Use Cases

| Use Case | Description |
|----------|-------------|
| **Multi-tenant SaaS** | Different tool access per customer tier |
| **Testing** | Isolated registries prevent test pollution |
| **Plugin systems** | Each plugin gets its own namespace |
| **Feature flags** | Enable/disable tools per environment |

### Complete Example

```python
import asyncio
from chuk_tool_processor import ToolProcessor, create_registry, tool

@tool(name="basic_search")
class BasicSearch:
    async def execute(self, query: str) -> dict:
        return {"results": [f"Basic result for: {query}"]}

@tool(name="premium_search")
class PremiumSearch:
    async def execute(self, query: str, depth: int = 10) -> dict:
        return {"results": [f"Premium result for: {query}"], "depth": depth}

async def main():
    # Free tier: basic tools only
    free_registry = create_registry()
    await free_registry.register_tool(BasicSearch)

    # Premium tier: all tools
    premium_registry = create_registry()
    await premium_registry.register_tool(BasicSearch)
    await premium_registry.register_tool(PremiumSearch)

    # Process requests with appropriate registry
    free_processor = ToolProcessor(registry=free_registry)
    premium_processor = ToolProcessor(registry=premium_registry)

    async with free_processor, premium_processor:
        # Free user can only use basic_search
        free_result = await free_processor.process(
            '<tool name="basic_search" args=\'{"query": "test"}\'/>'
        )

        # Premium user can use premium_search
        premium_result = await premium_processor.process(
            '<tool name="premium_search" args=\'{"query": "test", "depth": 20}\'/>'
        )

asyncio.run(main())
```

---

## Bulkheads (Per-Tool Concurrency Limits)

Prevent slow tools from starving fast ones with bulkhead isolation:

```python
from chuk_tool_processor import Bulkhead, BulkheadConfig

# Configure per-tool concurrency limits
config = BulkheadConfig(
    default_limit=10,              # Default: 10 concurrent per tool
    tool_limits={"slow_api": 2},   # Slow API: max 2 concurrent
    namespace_limits={"external": 5},  # External namespace: max 5 total
    global_limit=50,               # System-wide: max 50 concurrent
    acquisition_timeout=5.0,       # Wait up to 5s for a slot
)

bulkhead = Bulkhead(config)

# Use as context manager
async with bulkhead.acquire("slow_api", namespace="external"):
    result = await call_slow_api()

# Check stats
stats = bulkhead.get_stats("slow_api", "external")
print(f"Peak concurrent: {stats.peak_active}")
print(f"Total wait time: {stats.total_wait_time:.3f}s")
```

### Three Levels of Isolation

| Level | Description | Example |
|-------|-------------|---------|
| **Per-tool** | Limit concurrent executions of a specific tool | `tool_limits={"slow_api": 2}` |
| **Per-namespace** | Limit concurrent executions across a group of tools | `namespace_limits={"external": 5}` |
| **Global** | System-wide concurrency cap | `global_limit=50` |

All three levels are enforced simultaneously — a request must acquire slots at all applicable levels.

### BulkheadConfig Options

```python
class BulkheadConfig:
    default_limit: int = 10           # Default per-tool limit
    tool_limits: dict[str, int] = {}  # Per-tool overrides
    namespace_limits: dict[str, int] = {}  # Per-namespace limits
    global_limit: int | None = None   # Optional global limit
    acquisition_timeout: float | None = None  # Timeout for slot acquisition
    enable_metrics: bool = True       # Emit metrics for monitoring
```

### Handling Bulkhead Full

```python
from chuk_tool_processor import BulkheadFullError, BulkheadLimitType

try:
    async with bulkhead.acquire("slow_api", timeout=1.0):
        result = await call_slow_api()
except BulkheadFullError as e:
    print(f"Bulkhead full: {e.limit_type.value} limit ({e.limit}) exceeded")
    # e.limit_type: TOOL, NAMESPACE, or GLOBAL
    # e.timeout: How long we waited
```

### Dynamic Configuration

```python
# Update limits at runtime
bulkhead.configure_tool("slow_api", limit=5)
bulkhead.configure_namespace("external", limit=10)
```

### Monitoring Queue Depth

```python
# Check how many requests are waiting
depth = await bulkhead.get_queue_depth("slow_api")
if depth > 10:
    # Apply backpressure
    return {"error": "Service busy, try again later"}
```

---

## ExecutionContext (Request Tracing)

Propagate request metadata through the entire execution pipeline:

```python
from chuk_tool_processor import ToolProcessor, ExecutionContext, get_current_context

# Create context with request metadata
ctx = ExecutionContext(
    request_id="req-12345",
    user_id="user-alice",
    tenant_id="acme-corp",
    traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    budget=100.0,  # Abstract budget units
)

# Or with a deadline
ctx = ExecutionContext.with_deadline(
    seconds=30,
    user_id="user-bob",
    tenant_id="other-corp",
)

# Pass to processor - tools can access via get_current_context()
async with ToolProcessor() as processor:
    results = await processor.process(tool_calls, context=ctx)
```

### Accessing Context in Tools

```python
from chuk_tool_processor import get_current_context

class MyTool:
    async def execute(self, query: str) -> dict:
        ctx = get_current_context()
        user = ctx.user_id if ctx else "anonymous"
        tenant = ctx.tenant_id if ctx else "default"

        # Log with context
        logger.info(f"Processing query for {user} in tenant {tenant}")

        return {"result": f"Processed for {user}"}
```

### ExecutionContext Properties

```python
ctx = ExecutionContext.with_deadline(30, user_id="alice")

# Check deadline status
print(f"Remaining time: {ctx.remaining_time}s")  # 29.99...
print(f"Is expired: {ctx.is_expired}")  # False
print(f"Elapsed time: {ctx.elapsed_time}s")  # 0.001...

# Create child context with new span
child_ctx = ctx.with_span("child-span-id")

# Add metadata
ctx_with_meta = ctx.with_metadata(operation="search", priority="high")

# Update budget
ctx_reduced = ctx.with_budget(50.0)
```

### Serialization for Distributed Systems

```python
# Convert to HTTP headers for MCP propagation
headers = ctx.to_headers()
# {
#     'X-Request-ID': 'req-12345',
#     'X-User-ID': 'user-alice',
#     'X-Tenant-ID': 'acme-corp',
#     'traceparent': '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01',
#     'X-Deadline-Seconds': '30'
# }

# Convert to dict for structured logging
log_context = ctx.to_dict()
# {
#     'request_id': 'req-12345',
#     'user_id': 'user-alice',
#     'tenant_id': 'acme-corp',
#     'remaining_time': 29.5,
#     ...
# }

# Reconstruct from headers (e.g., in MCP server)
ctx = ExecutionContext.from_headers(headers)
```

### Context Scoping

```python
from chuk_tool_processor import execution_scope

# Explicit context scope
async with execution_scope(ctx):
    # All tool calls in this scope see the context
    result = await some_tool.execute(query="test")

# Context automatically cleared after scope exits
```

### Features Summary

| Feature | Description |
|---------|-------------|
| **Immutable** | Pydantic frozen model prevents accidental mutation |
| **Deadline propagation** | `remaining_time`, `is_expired` properties |
| **W3C Trace Context** | Standard `traceparent` header support |
| **MCP-ready** | `to_headers()` for cross-service propagation |
| **Async-safe** | Uses `contextvars` for task-local storage |
| **Budget tracking** | Abstract budget units for cost control |

---

## Complete Example: All Patterns Combined

See `examples/02_production_features/production_patterns_demo.py` for a complete demonstration combining:

- Scoped registries for tenant isolation
- Bulkheads for concurrency control
- ExecutionContext for request tracing
- Caching and retries for reliability

```python
import asyncio
from chuk_tool_processor import (
    ToolProcessor,
    create_registry,
    ExecutionContext,
    BulkheadConfig,
)

async def handle_request(tenant_id: str, user_id: str, request_num: int):
    # 1. Get tenant-specific registry
    registry = get_tenant_registry(tenant_id)

    # 2. Configure bulkheads for this tenant
    bulkhead_config = BulkheadConfig(
        default_limit=10,
        tool_limits={"external_api": 3},
        global_limit=50,
    )

    # 3. Create processor with all features
    processor = ToolProcessor(
        registry=registry,
        enable_bulkhead=True,
        bulkhead_config=bulkhead_config,
        enable_caching=True,
        enable_retries=True,
    )

    # 4. Create execution context
    ctx = ExecutionContext(
        request_id=f"req-{request_num}",
        user_id=user_id,
        tenant_id=tenant_id,
    )

    # 5. Process with full production features
    async with processor:
        results = await processor.process(tool_calls, context=ctx)

    return results
```

---

## Related Documentation

- [CONFIGURATION.md](CONFIGURATION.md) - All configuration options
- [OBSERVABILITY.md](OBSERVABILITY.md) - Metrics and tracing
- [ERRORS.md](ERRORS.md) - Error handling patterns
