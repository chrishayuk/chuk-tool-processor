# CHUK Tool Processor — Roadmap

> Last updated: 2026-02-17

---

## Shipped (v0.20)

Everything below is production-ready on `main`.

### Core Runtime
- [x] Async-native tool execution (Python 3.11+)
- [x] Multi-format parsing — Anthropic XML, OpenAI `tool_calls`, JSON
- [x] Timeouts, retries (exponential backoff + jitter), caching (TTL + SHA256 keys)
- [x] Rate limiting (global + per-tool sliding windows)
- [x] Circuit breakers with automatic recovery
- [x] Structured error categories with retry hints for planners

### Execution Strategies
- [x] InProcess — fast, trusted tools
- [x] Subprocess/Isolated — untrusted code with zero crash blast radius
- [x] Remote via MCP — distributed tool execution

### MCP Integration
- [x] STDIO transport (local processes)
- [x] SSE transport (legacy servers) with headers support
- [x] HTTP Streamable transport (modern MCP spec 2025-11-25)
- [x] StreamManager with multi-server lifecycle management
- [x] Middleware stack — retry, circuit breaker, rate limiting for MCP calls
- [x] OAuth token refresh callbacks
- [x] Robust shutdown handling (shield + fallback strategies)
- [x] Health checks and diagnostics

### Multi-Tenant & Isolation
- [x] Bulkheads — per-tool/namespace concurrency limits
- [x] Pattern bulkheads — glob patterns (`"db.*": 3`)
- [x] Scoped registries for multi-tenant apps
- [x] ExecutionContext — request-scoped metadata propagation
- [x] Redis registry for distributed deployments
- [x] Redis-backed circuit breaker and rate limiting

### Scheduling
- [x] Return order — completion (fast first) or submission (deterministic)
- [x] DAG-based greedy scheduler with topological sort
- [x] Deadline-aware skipping of low-priority calls
- [x] Pool-based concurrency constraints

### Guards (Constitution Layer)
- [x] SchemaStrictnessGuard — JSON schema validation + type coercion
- [x] SensitiveDataGuard — detect/block/redact secrets
- [x] NetworkPolicyGuard — SSRF defense
- [x] SideEffectGuard — read_only/write/destructive classification
- [x] ConcurrencyGuard — global/per-tool/per-namespace limits
- [x] TimeoutBudgetGuard — wall-clock budgets with soft/hard limits
- [x] OutputSizeGuard — payload size/depth/array limits
- [x] RetrySafetyGuard — backoff, idempotency, non-retryable classification
- [x] ProvenanceGuard — output attribution and lineage
- [x] PlanShapeGuard — detect fan-out explosions, long chains
- [x] SaturationGuard — degenerate statistical outputs
- [x] RunawayGuard, BudgetGuard, PerToolGuard, PreconditionGuard, UnresolvedReferenceGuard

### Discovery
- [x] Natural language tool search with synonym expansion
- [x] Fuzzy matching with typo tolerance
- [x] Session boosting — recent tools rank higher
- [x] BaseDynamicToolProvider for LLM-driven discovery

### Observability
- [x] OpenTelemetry distributed tracing
- [x] Prometheus metrics (latency, error rate, cache hits, circuit state)
- [x] Structured logging with context propagation

### Developer Experience
- [x] `@tool` and `@register_tool` decorators
- [x] `register_fn_tool` for plain functions
- [x] PEP 561 type stubs (`py.typed`)
- [x] 90+ test files with comprehensive coverage
- [x] 20+ working examples
- [x] Apache 2.0 license

---

## In Progress — MCP Apps (v0.21)

Current branch: `mcp-apps`

- [ ] Align transport layer with latest chuk-mcp changes
- [ ] SSE transport enhancements (base transport additions)
- [ ] Streamline example imports for new chuk-mcp API

---

## Near-Term

### Distributed Caching (Redis)
Redis-backed rate limiting and circuit breakers are shipped. Caching is next.

- [ ] Redis cache provider implementing existing `CacheInterface`
- [ ] TTL and eviction policy configuration
- [ ] Cache key prefixing for multi-tenant isolation

### Cache Key Normalization
Improve cache hit rates for tools with volatile arguments.

- [ ] `cache_key_fn` parameter on tool registration
- [ ] Strip timestamps, random IDs, and other volatile fields before hashing
- [ ] Documentation and examples

### WebAssembly Sandbox
Infrastructure is already scaffolded (`IsolationLevel.WASM`).

- [ ] WASM runtime integration (wasmtime or similar)
- [ ] Lightweight, portable tool isolation
- [ ] Resource limits (memory, CPU cycles) within WASM boundary

### Guard Integration with Processor
Guards exist as a standalone system. Wire them into the processor pipeline.

- [ ] `guards=` parameter on `ToolProcessor`
- [ ] Pre-execution guard chain (before tool call)
- [ ] Post-execution guard chain (validate outputs)
- [ ] Guard metrics in observability layer

---

## Medium-Term

### Type Safety Hardening
Systematic module-by-module tightening of mypy strictness.

- [ ] Enable `disallow_untyped_defs` for public APIs (`core.processor`)
- [ ] Enable `disallow_untyped_calls` gradually
- [ ] Reduce mypy `ignore_errors` overrides for:
  - `mcp.*`
  - `plugins.*`
  - `execution.wrappers.*`
  - `execution.strategies.*`
  - `registry.decorators`

### Expanded Observability
- [ ] Custom metric exporters (StatsD, Datadog)
- [ ] Trace sampling configuration
- [ ] Custom span attributes via tool metadata
- [ ] Baggage propagation for distributed tracing
- [ ] Health check endpoint integration

### MCP Resources & Prompts
StreamManager already has `list_resources()`, `read_resource()`, `list_prompts()`. Expose these more fully.

- [ ] Resource subscriptions (watch for changes)
- [ ] Prompt template execution through processor
- [ ] Resource caching with invalidation

### Streaming Tool Execution
`StreamingTool` model exists. Extend runtime support.

- [ ] First-class streaming in `ToolProcessor.process()`
- [ ] Streaming results via async generators
- [ ] Backpressure handling for slow consumers
- [ ] Streaming through MCP transports

---

## Longer-Term

### A2A (Agent-to-Agent) Protocol
As the chuk-acp ecosystem matures, tool processor becomes the execution substrate for agent-to-agent communication.

- [ ] A2A task cards as tool calls
- [ ] Cross-agent tool delegation
- [ ] Agent capability advertisement via tool schemas

### Multi-Model Tool Routing
Route tool calls to different execution backends based on tool characteristics.

- [ ] Cost-aware routing (cheap tools local, expensive tools remote)
- [ ] Latency-aware routing with automatic fallback
- [ ] Geographic routing for data sovereignty

### Plugin Ecosystem
- [ ] Third-party tool packs (pip-installable)
- [ ] Auto-discovery of installed tool packages
- [ ] Tool marketplace / registry service integration

---

## Ecosystem Context

**chuk-tool-processor** is a foundational layer in the chuk-ai ecosystem. These packages depend on it:

| Package | Min Version | Role |
|---------|-------------|------|
| **chuk-acp-agent** | >=0.9.7 | ACP agent framework |
| **chuk-ai-session-manager** | >=0.18 | Session management |
| **chuk-ai-planner** | >=0.11 | Planning agent |
| **chuk-mcp-server** | >=0.11.3 | MCP proxy server |
| **chuk-agent-experimental** | latest | Experimental agents |

Breaking changes require coordinated updates across these packages.

---

## Version Housekeeping

- [x] ~~Sync `__init__.py` version with `pyproject.toml`~~ — resolved: `__init__.py` now reads from `importlib.metadata` at runtime
- [ ] Establish semantic versioning policy for 1.0
