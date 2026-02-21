# CHUK Tool Processor — Architecture Principles

> These principles govern all code in chuk-tool-processor.
> Every PR should be evaluated against them.

---

## 1. Async Native

Every public API is `async def`. No blocking calls anywhere in the call path.

**Rules:**
- All tool execution, registry access, and MCP communication use `async`/`await`
- File I/O uses `aiofiles` or runs in an executor — never bare `open()`/`write()` in async context
- Use `asyncio.Lock` (not `threading.Lock`) for shared state
- Use `time.monotonic()` for elapsed-time measurement, never `time.time()` for durations
- Synchronous helpers (pure computation, no I/O) are acceptable but must not block the event loop

**Why:** Tool execution is inherently concurrent. A single blocking call in the hot path stalls every tool call sharing that event loop.

---

## 2. Pydantic Native

Structured data flows through Pydantic models, not raw dicts.

**Rules:**
- Inputs and outputs of public APIs are Pydantic `BaseModel` instances
- Configuration objects are Pydantic models (not dataclasses, not plain dicts)
- Use `model_validator`, `field_validator`, and `Field(...)` for constraints
- Use `ConfigDict(frozen=True)` for immutable value objects
- Factory methods (`from_function()`, `create_error()`) return model instances
- Serialization goes through `.model_dump()` / `.model_dump_json()`

**Why:** Pydantic gives us validation at construction time, clear field documentation, and serialization for free. Raw dicts defer errors to runtime and make refactoring dangerous.

---

## 3. No Dictionary Goop

Never pass `dict[str, Any]` through public interfaces when a model will do.

**Rules:**
- If a dict has a known shape, define a model or `TypedDict`
- If a function returns `dict[str, Any]`, ask: should this be a model?
- Accessing nested dicts with `.get("key")` chains is a code smell — model it
- Internal dict usage for caches, indexes, and transient lookups is fine
- JSON schemas from external systems (MCP, OpenAI) are exempt at the boundary — but wrap them in models as early as possible

**Why:** `data["tool_calls"][0]["function"]["name"]` is unreadable, unrefactorable, and produces `KeyError` at runtime instead of a validation error at construction.

---

## 4. No Magic Strings

Use enums, constants, or Pydantic `Literal` types — never bare string comparisons.

**Rules:**
- Status values (`"ALLOW"`, `"BLOCK"`, `"WARN"`) → `str` Enum
- Transport types (`"stdio"`, `"sse"`, `"http_streamable"`) → `str` Enum
- Provider types (`"memory"`, `"redis"`) → `str` Enum
- Error codes → `ErrorCode` enum (already exists)
- If you find yourself writing `if x == "some_string"`, define a constant or enum first
- Enum members that need to serialize as strings use `class Foo(str, Enum)`

**Why:** Magic strings are invisible to refactoring tools, produce silent bugs when misspelled, and can't be auto-completed by IDEs.

---

## 5. Clean Code

Small functions. Clear names. Single responsibility. Minimal coupling.

**Rules:**
- Functions do one thing; if a function needs a comment explaining what it does, extract sub-functions
- Modules have a single area of responsibility (e.g., `retry.py` only handles retries)
- Avoid deep inheritance; prefer composition and protocols
- Use `Protocol` (structural subtyping) over ABC where possible
- No dead code, no commented-out blocks, no `# TODO: maybe later` without a tracking issue
- Limit module size — if a file exceeds ~500 lines, consider splitting

**Why:** Tool processors are composed of many small, hot-path operations. Clarity in each piece makes the whole system debuggable under production pressure.

---

## 6. Test Coverage ≥ 90% Per File

Every source file must have ≥ 90% line coverage individually.

**Rules:**
- Each `src/.../foo.py` has a corresponding `tests/.../test_foo.py`
- Coverage is measured per-file, not just as a project aggregate
- Test both happy paths and error/edge cases
- Async tests use `pytest-asyncio` with `@pytest.mark.asyncio`
- Mock external dependencies (Redis, MCP servers, file systems) — never hit real services in unit tests
- Integration tests (hitting real services) are separate and clearly marked

**Current Violations (to fix):**

| File | Coverage | Target |
|------|----------|--------|
| `execution/wrappers/factory.py` | 30% | 90% |
| `execution/wrappers/redis_circuit_breaker.py` | 29% | 90% |
| `execution/wrappers/redis_rate_limiting.py` | 19% | 90% |
| `observability/setup.py` | 17% | 90% |
| `observability/trace_sink.py` | 42% | 90% |
| `models/tool_spec.py` | 84% | 90% |
| `mcp/transport/sse_transport.py` | 87% | 90% |
| `observability/metrics.py` | 88% | 90% |
| `discovery/searchable.py` | 88% | 90% |
| `observability/tracing.py` | 89% | 90% |
| `plugins/parsers/base.py` | 88% | 90% |

---

## 7. Separation of Concerns

CHUK decides **how** to execute. Planners decide **what** to execute.

**Rules:**
- The processor never makes tool-selection decisions — it executes what it's given
- Guards can block or warn, but never rewrite the planner's intent silently
- Registry is a lookup service, not a decision engine
- MCP transports are dumb pipes — protocol logic lives in the transport, not the tool
- Middleware wraps execution uniformly — no tool-specific branching in middleware

---

## 8. Observable by Default

Every execution produces structured telemetry without opt-in.

**Rules:**
- `ExecutionSpan` captures timing, outcome, guard decisions, and strategy for every call
- OpenTelemetry spans are created for tool execution, MCP calls, and middleware
- Prometheus counters/histograms track latency, errors, cache hits, circuit state
- Structured logging includes `trace_id`, `tool_name`, `session_id` in every log line
- Observability must not throw — if tracing is misconfigured, execution still succeeds

---

## 9. Fail Safe, Fail Loud

Execution must not silently swallow errors.

**Rules:**
- Errors return `ToolResult` with `is_error=True` and structured `ErrorInfo` — never empty strings
- Circuit breakers fail open (allow traffic) when state is unknown
- Rate limiters fail open on clock skew or Redis unavailability
- Silent `except Exception: pass` is forbidden in production paths
- Log errors at the point of origin with full context, not at a distant catch site

---

## 10. Composable Middleware

Reliability features compose as a stack, applied in a deterministic order.

**Middleware order:** Cache → Rate Limit → Retry → Circuit Breaker → Bulkhead → Execute

**Rules:**
- Each wrapper is independent and testable in isolation
- Wrappers don't know about each other — they receive a callable and return a callable
- The factory assembles the stack; individual wrappers don't reference the factory
- Adding a new wrapper requires zero changes to existing wrappers
- Wrappers propagate `ExecutionContext` transparently

---

## Checklist for PRs

- [ ] All new public APIs are `async def`
- [ ] New data structures use Pydantic models (not raw dicts)
- [ ] No new magic string comparisons (use enums/constants)
- [ ] New file has corresponding test file with ≥ 90% coverage
- [ ] No blocking I/O in async code paths
- [ ] Errors produce `ToolResult` with `ErrorInfo`, not bare strings
- [ ] Observability: new code paths have spans/metrics where appropriate
