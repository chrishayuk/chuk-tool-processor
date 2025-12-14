# Production Patterns

This guide covers production-grade patterns for building reliable, scalable tool execution systems.

## Key Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| **Return order** | `completion` | Results return as tools finish (faster first) |
| **Parallel execution** | Enabled | Tools run concurrently by default |
| **Caching** | Disabled | Enable via `enable_caching=True` |
| **Bulkheads** | Disabled | Enable via `enable_bulkhead=True` |
| **Retries** | Disabled | Enable via `enable_retries=True` |
| **Rate limiting** | Disabled | Enable via `enable_rate_limiting=True` |

---

## Table of Contents

- [Idempotency via Caching](#idempotency-via-caching)
- [Cancellation & Deadlines](#cancellation--deadlines)
- [Per-Tool Policy Overrides](#per-tool-policy-overrides)
- [Policy Precedence](#policy-precedence)
- [Parallel Execution & Streaming](#parallel-execution--streaming)
- [Return Order](#return-order-completion-vs-submission)
- [Dotted Names for Namespacing](#dotted-names-for-namespacing)
- [Scoped Registries](#scoped-registries-multi-tenant-isolation)
- [Bulkheads](#bulkheads-per-tool-concurrency-limits)
- [Pattern-Based Bulkheads](#pattern-based-bulkheads)
- [ExecutionContext](#executioncontext-request-tracing)
- [SchedulerPolicy & DAG Scheduling](#schedulerpolicy--dag-scheduling)
- [Recipes](#recipes)

---

## Idempotency via Caching

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

### Safe by Default

Caching is **off by default** because:
- Some tools have side effects (`db.write`, `send_email`)
- Arguments may contain volatile fields (timestamps, random IDs)

**Recommended approach:**
- Enable caching selectively for read-only/idempotent tools
- Use `cache_key_fn` (future) to normalize arguments and strip volatile fields
- For true idempotency on side-effecting systems, use idempotency keys at the destination

### Persistence Options

| Backend | Use Case | Status |
|---------|----------|--------|
| **In-memory** | Single process, development | Default |
| **Redis** | Multi-process, production | Planned |
| **Custom** | Implement `CacheBackend` protocol | Supported |

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

### Cancel Behaviour by Strategy

| Strategy | Cancel Behaviour |
|----------|------------------|
| **In-process** | Cooperative `CancelledError`; coroutine yields control |
| **Subprocess** | `SIGTERM` sent; grace period then `SIGKILL` |
| **MCP remote** | Client stops waiting; server may continue (best-effort) |

**Important:** Cancellation is **best-effort**. For subprocess and MCP strategies, the underlying operation may continue server-side even after the client cancels. Design tools to be re-entrant or use idempotency keys on side-effecting operations.

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

See [CONFIGURATION.md](CONFIGURATION.md) for all options.

---

## Policy Precedence

When the same setting (e.g., `timeout_ms`, `max_retries`) is configured at multiple levels, the most specific wins:

| Priority | Source | Example |
|----------|--------|---------|
| **1 (highest)** | Per-call override from scheduler | `per_call_timeout_ms["fetch-1"] = 500` |
| **2** | Per-tool config | `tool_rate_limits={"slow_api": (5, 60)}` |
| **3** | Namespace/pattern config | `patterns={"mcp.*": 5}` |
| **4 (lowest)** | Global defaults | `default_timeout=30.0` |

This is especially important for `timeout_ms` and `max_retries` when using the scheduler.

---

## Parallel Execution & Streaming

Tools execute concurrently by default. Results return in **completion order** — faster tools return immediately without waiting for slower ones:

```python
import asyncio
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall

# Tools with different execution times
calls = [
    ToolCall(id="call-1", tool="slow_api", arguments={"query": "complex"}),    # 500ms
    ToolCall(id="call-2", tool="medium_api", arguments={"query": "medium"}),   # 200ms
    ToolCall(id="call-3", tool="fast_api", arguments={"query": "simple"}),     # 50ms
]

# Results return as: fast_api, medium_api, slow_api (completion order)
results = await strategy.run(calls)

# Match results back to original calls by call_id (NOT tool name!)
for result in results:
    print(f"call_id: {result.call_id}, tool: {result.tool}")
    # call_id: call-3, tool: fast_api
    # call_id: call-2, tool: medium_api
    # call_id: call-1, tool: slow_api
```

**Important:** Always match results by `call_id`, not `tool` name. Tool names repeat all the time; `call_id` is the unique join key.

### Stream results as they arrive

```python
async for result in strategy.stream_run(calls):
    # Process each result immediately as it completes
    print(f"Completed: {result.call_id} ({result.tool})")
```

### Track when tools start

```python
async def on_start(call: ToolCall):
    print(f"Starting: {call.id}")

async for result in strategy.stream_run(calls, on_tool_start=on_start):
    print(f"Completed: {result.call_id}")
```

### Control concurrency

```python
# Limit to 2 concurrent tools (others queue)
strategy = InProcessStrategy(registry, max_concurrency=2)
```

> **See:** `examples/parallel_execution_demo.py` for a complete demonstration.

---

## Return Order (Completion vs Submission)

Control the order in which results are returned:

```python
from chuk_tool_processor import ToolProcessor, ReturnOrder

async with ToolProcessor() as processor:
    calls = [
        {"tool": "slow_api", "arguments": {"query": "complex"}},    # ~500ms
        {"tool": "medium_api", "arguments": {"query": "medium"}},   # ~200ms
        {"tool": "fast_api", "arguments": {"query": "simple"}},     # ~50ms
    ]

    # COMPLETION order (default): Results return as tools finish
    # Returns: fast_api, medium_api, slow_api
    results = await processor.process(calls, return_order="completion")

    # SUBMISSION order: Results return in the same order as submitted
    # Returns: slow_api, medium_api, fast_api
    results = await processor.process(calls, return_order="submission")
```

### Return Order Options

```python
from chuk_tool_processor.models.return_order import ReturnOrder

class ReturnOrder(str, Enum):
    COMPLETION = "completion"  # Results as tools finish (default)
    SUBMISSION = "submission"  # Results in input order
```

### When to Use Each

| Order | Use Case |
|-------|----------|
| **completion** (default) | Streaming UIs, real-time dashboards, fastest response |
| **submission** | Deterministic testing, ordered pipelines, debugging |

### Tracking Results with call_id

Each `ToolResult` includes a `call_id` field that matches the original `ToolCall.id`:

```python
for result in results:
    print(f"call_id: {result.call_id}, tool: {result.tool}")
```

---

## Dotted Names for Namespacing

Dotted names are auto-parsed into namespace and tool name for cleaner registration:

```python
from chuk_tool_processor import create_registry

registry = create_registry()

# Dotted names auto-extract namespace
await registry.register_tool(FetchUser, name="web.fetch_user")      # namespace="web", name="fetch_user"
await registry.register_tool(WriteDB, name="db.write")              # namespace="db", name="write"
await registry.register_tool(SearchAPI, name="api.search")          # namespace="api", name="search"

# Explicit namespace (these are equivalent)
await registry.register_tool(FetchUser, name="fetch_user", namespace="web")

# Call using the full dotted name
result = await processor.process([{"tool": "web.fetch_user", "arguments": {"user_id": "123"}}])
```

### When Explicit Namespace Takes Precedence

If you provide both a dotted name and an explicit namespace (other than `"default"`), the explicit namespace wins:

```python
# Explicit namespace overrides dotted parsing
await registry.register_tool(MyTool, name="a.b", namespace="custom")
# → namespace="custom", name="a.b"
```

### Decorator Support

The `@tool` decorator also supports dotted names:

```python
from chuk_tool_processor import tool

@tool(name="web.fetch_user")  # Parsed to namespace="web", name="fetch_user"
class FetchUserTool:
    async def execute(self, user_id: str) -> dict:
        return {"user_id": user_id}
```

---

## Scoped Registries (Multi-Tenant Isolation)

Create isolated tool registries for multi-tenant apps, testing, or plugin systems:

```python
from chuk_tool_processor import ToolProcessor, create_registry

# Each tenant gets their own isolated registry
tenant_a_registry = create_registry()
tenant_b_registry = create_registry()

# Register different tools per tenant (using dotted names)
await tenant_a_registry.register_tool(BasicTool, name="core.basic")
await tenant_b_registry.register_tool(BasicTool, name="core.basic")
await tenant_b_registry.register_tool(PremiumTool, name="premium.advanced")  # Only tenant B

# Create processors with isolated registries
processor_a = ToolProcessor(registry=tenant_a_registry)
processor_b = ToolProcessor(registry=tenant_b_registry)

# Tenant A cannot access premium tools
tools_a = await processor_a.list_tools()  # ['basic']
tools_b = await processor_b.list_tools()  # ['basic', 'advanced']
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
    max_queue_depth=100,           # Max waiters before fail-fast
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
    patterns: dict[str, int] = {}     # Pattern-based limits (glob syntax)
    namespace_limits: dict[str, int] = {}  # Per-namespace limits
    global_limit: int | None = None   # Optional global limit
    acquisition_timeout: float | None = None  # Timeout for slot acquisition
    max_queue_depth: int | None = None  # Max waiters (None = unlimited)
    enable_metrics: bool = True       # Emit metrics for monitoring
```

### Queue Depth and Backpressure

Without `max_queue_depth`, a saturated pool becomes "infinite latency" — requests queue forever.

```python
config = BulkheadConfig(
    default_limit=10,
    max_queue_depth=50,  # Fail fast if >50 requests waiting
)
```

When `max_queue_depth` is exceeded, new requests immediately receive `BulkheadFullError`.

### Handling Bulkhead Full

```python
from chuk_tool_processor import BulkheadFullError, BulkheadLimitType

try:
    async with bulkhead.acquire("slow_api", timeout=1.0):
        result = await call_slow_api()
except BulkheadFullError as e:
    print(f"Bulkhead full: {e.limit_type.value} limit ({e.limit}) exceeded")
    # e.limit_type: TOOL, NAMESPACE, GLOBAL, or QUEUE_DEPTH
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

## Pattern-Based Bulkheads

Use glob patterns to group tools under shared concurrency limits:

```python
from chuk_tool_processor import Bulkhead, BulkheadConfig

config = BulkheadConfig(
    default_limit=10,
    patterns={
        "db.*": 3,           # All db.* tools share 3 slots
        "mcp.notion.*": 2,   # All Notion MCP tools share 2 slots
        "mcp.*": 5,          # Other MCP tools share 5 slots
        "web.*": 4,          # All web tools share 4 slots
    },
    global_limit=50,
)

bulkhead = Bulkhead(config)
```

### Pattern Matching Rules

Patterns use standard glob syntax via `fnmatch`:

| Pattern | Matches | Doesn't Match |
|---------|---------|---------------|
| `db.*` | `db.read`, `db.write`, `db.backup` | `database.query` |
| `mcp.notion.*` | `mcp.notion.search`, `mcp.notion.create` | `mcp.github.issues` |
| `*_api` | `slow_api`, `fast_api` | `api_client` |

### Priority Order

Limits are resolved in this order:

1. **Exact match** in `tool_limits` (highest priority)
2. **First matching pattern** in `patterns` (dict iteration order)
3. **`default_limit`** (fallback)

```python
config = BulkheadConfig(
    default_limit=10,
    tool_limits={"db.critical": 1},  # Exact match takes priority
    patterns={"db.*": 3},
)

# db.critical → 1 (exact match)
# db.read → 3 (pattern match)
# other_tool → 10 (default)
```

**Note:** Patterns are evaluated in dict iteration order (insertion order in Python 3.7+). For predictable behavior, list more specific patterns before broader ones, or use explicit tool limits for critical paths.

### Performance

Pattern matching uses an LRU cache (1024 entries) for fast lookups after the first match.

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

### Security Note

**Do not put secrets in context.** ExecutionContext may be:
- Logged to observability systems
- Serialized to headers for MCP propagation
- Included in error reports

Use it for identifiers (`user_id`, `tenant_id`, `request_id`), not credentials.

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

## SchedulerPolicy & DAG Scheduling

For complex workflows with dependencies, use the `SchedulerPolicy` interface to plan execution:

```python
from chuk_tool_processor import (
    GreedyDagScheduler,
    SchedulingConstraints,
    ToolCallSpec,
    ToolMetadata,
)

scheduler = GreedyDagScheduler()

# Define calls with dependencies and metadata
calls = [
    # Stage 1: Parallel fetches
    ToolCallSpec(
        call_id="fetch-users",
        tool_name="web.fetch",
        args={"url": "/api/users"},
        metadata=ToolMetadata(pool="web", est_ms=300, priority=10),
    ),
    ToolCallSpec(
        call_id="fetch-orders",
        tool_name="web.fetch",
        args={"url": "/api/orders"},
        metadata=ToolMetadata(pool="web", est_ms=300, priority=10),
    ),
    # Stage 2: Transform (depends on fetches)
    ToolCallSpec(
        call_id="transform",
        tool_name="compute.transform",
        depends_on=("fetch-users", "fetch-orders"),
        metadata=ToolMetadata(pool="compute", est_ms=500, priority=10),
    ),
    # Stage 3: Store (depends on transform)
    ToolCallSpec(
        call_id="store",
        tool_name="db.write",
        depends_on=("transform",),
        metadata=ToolMetadata(pool="db", est_ms=200, priority=10),
    ),
    # Optional: Low-priority analytics (may be skipped under deadline)
    ToolCallSpec(
        call_id="analytics",
        tool_name="analytics.log",
        depends_on=("store",),
        metadata=ToolMetadata(pool="analytics", est_ms=100, priority=0),
    ),
]

# Plan execution with constraints
constraints = SchedulingConstraints(
    deadline_ms=1500,                         # Global deadline
    max_cost=1.0,                             # Cost budget
    pool_limits={"web": 2, "db": 1, "compute": 1},
)

plan = scheduler.plan(calls, constraints)

# plan.stages: (('fetch-users', 'fetch-orders'), ('transform',), ('store',))
# plan.skip: ('analytics',)  # Skipped due to deadline + low priority
# plan.per_call_timeout_ms: {'fetch-users': 300, ...}
```

### ExecutionPlan Output

The scheduler returns an `ExecutionPlan` with:

| Field | Description |
|-------|-------------|
| `stages` | Tuple of stages, each containing call IDs to execute in parallel |
| `per_call_timeout_ms` | Per-call timeout adjustments to meet deadline |
| `per_call_max_retries` | Per-call retry overrides |
| `skip` | Call IDs to skip (deadline/cost infeasible or low priority) |

### ToolMetadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `pool` | `str` | Pool name for concurrency limits (default: "default") |
| `weight` | `int` | Relative weight for scheduling (default: 1) |
| `est_ms` | `int` | Estimated execution time in milliseconds |
| `cost` | `float` | Cost units for budget tracking |
| `priority` | `int` | Priority (higher = more important, 0 = can be skipped) |

### Failure and Skip Propagation

There are two types of skipping:

| Type | When | Behaviour |
|------|------|-----------|
| **Planned skip** | Before execution | Scheduler cascades skips based on deadline/cost/priority |
| **Runtime failure** | During execution | Dependents marked as `SKIPPED_DEPENDENCY_FAILED` |

**Example: Planned skip cascade**
```
fetch-users → transform → store → analytics
                                      ↑
                              Skipped (low priority, deadline tight)
```
If `analytics` is skipped, no dependents exist, so no cascade.

**Example: Runtime failure cascade**
```
fetch-users → transform → store
      ↓            ↑
   FAILED      SKIPPED (dependency failed)
```
If `fetch-users` fails at runtime, `transform` (and transitively `store`) are skipped because their dependency failed.

**Note:** To allow partial execution despite failures, use `continue_on_error=True` at the executor level (not scheduler).

### Scheduling Features

- **Topological Sort**: Respects `depends_on` for correct execution order
- **Pool Limits**: Respects per-pool concurrency limits in each stage
- **Deadline Awareness**: Skips low-priority calls if they would exceed deadline
- **Cost Limits**: Skips low-priority calls if they would exceed cost budget
- **Cascade Skipping**: If a call is skipped, its dependents are also skipped

### Custom Schedulers

Implement the `SchedulerPolicy` protocol for custom scheduling logic:

```python
from typing import Mapping, Sequence
from chuk_tool_processor import (
    ExecutionPlan,
    SchedulingConstraints,
    ToolCallSpec,
)

class MyCustomScheduler:
    def plan(
        self,
        calls: Sequence[ToolCallSpec],
        constraints: SchedulingConstraints,
        context: Mapping[str, object] | None = None,
    ) -> ExecutionPlan:
        # Your custom logic here
        return ExecutionPlan(
            stages=(tuple(c.call_id for c in calls),)
        )
```

> **See:** `examples/02_production_features/runtime_features_demo.py` for a complete demonstration.

---

## Recipes

### SLO Recipe: 2s P95 API Endpoint

Configure for a typical SaaS API with 2-second P95 latency SLO:

```python
from chuk_tool_processor import ToolProcessor, BulkheadConfig

async with ToolProcessor(
    # Timeouts: Leave headroom for retries
    default_timeout=1.5,           # Tool timeout (retries happen within 2s budget)

    # Retries: Fast retries for transient failures
    enable_retries=True,
    max_retries=1,                 # One retry max (fits in 2s with 1.5s timeout)
    retry_base_delay=0.1,          # Start fast

    # Rate limiting: Protect downstream services
    enable_rate_limiting=True,
    global_rate_limit=100,         # 100 req/min across all tools
    tool_rate_limits={
        "external_api": (10, 60),  # 10/min for expensive external calls
    },

    # Bulkheads: Prevent slow tools from starving fast ones
    enable_bulkhead=True,
    bulkhead_config=BulkheadConfig(
        default_limit=10,
        tool_limits={"external_api": 2},  # Limit external calls
        acquisition_timeout=0.5,          # Fail fast if pool saturated
        max_queue_depth=20,               # Backpressure
    ),

    # Caching: Reduce repeated calls
    enable_caching=True,
    cache_ttl=60,                  # 1 minute for most tools
) as processor:
    results = await processor.process(tool_calls)
```

### Multi-Tenant Recipe: Per-Tenant Isolation

Complete isolation with per-tenant pools and limits:

```python
from chuk_tool_processor import (
    ToolProcessor,
    create_registry,
    BulkheadConfig,
    ExecutionContext,
)

def create_tenant_processor(tenant_id: str, tier: str):
    # Tenant-specific registry (tool access by tier)
    registry = create_registry()
    register_tools_for_tier(registry, tier)

    # Tenant-specific bulkhead with namespaced pools
    config = BulkheadConfig(
        default_limit=5 if tier == "free" else 20,
        patterns={
            f"web:{tenant_id}:*": 3 if tier == "free" else 10,
            f"db:{tenant_id}:*": 1 if tier == "free" else 3,
        },
        global_limit=10 if tier == "free" else 50,
        max_queue_depth=5 if tier == "free" else 20,
    )

    return ToolProcessor(
        registry=registry,
        enable_bulkhead=True,
        bulkhead_config=config,
        enable_rate_limiting=True,
        global_rate_limit=30 if tier == "free" else 200,
    )

# Usage
async def handle_request(tenant_id: str, user_id: str, tool_calls):
    tier = await get_tenant_tier(tenant_id)
    processor = create_tenant_processor(tenant_id, tier)

    ctx = ExecutionContext(
        request_id=f"req-{uuid4()}",
        user_id=user_id,
        tenant_id=tenant_id,
    )

    async with processor:
        return await processor.process(tool_calls, context=ctx)
```

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
- [MCP_INTEGRATION.md](MCP_INTEGRATION.md) - Middleware stack for resilience
- [OBSERVABILITY.md](OBSERVABILITY.md) - Metrics and tracing
- [ERRORS.md](ERRORS.md) - Error handling patterns
