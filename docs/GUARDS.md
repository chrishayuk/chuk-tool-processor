# Runtime Guards

Runtime guards provide a "constitution layer" for tool execution — enforcing safety policies, validating inputs, managing resources, and preventing abuse before and after tool calls execute.

## Overview

Guards are composable checks that run before (pre-execution) or after (post-execution) tool calls. Each guard returns one of four verdicts:

| Verdict | Description |
|---------|-------------|
| **ALLOW** | Proceed with execution |
| **WARN** | Proceed but log a warning |
| **BLOCK** | Do not execute, return error |
| **REPAIR** | Proceed with modified arguments/output |

## Quick Start

```python
from chuk_tool_processor.guards import (
    GuardChain,
    SchemaStrictnessGuard,
    SensitiveDataGuard,
    NetworkPolicyGuard,
)

# Create guards
schema_guard = SchemaStrictnessGuard(get_schema=my_schema_getter)
sensitive_guard = SensitiveDataGuard()
network_guard = NetworkPolicyGuard(block_private_ips=True)

# Compose into a chain
chain = GuardChain([schema_guard, sensitive_guard, network_guard])

# Check before execution
result = await chain.check_all_async("api.fetch", {"url": "https://example.com"})

if result.blocked:
    print(f"Blocked by {result.stopped_at}: {result.reason}")
elif result.repaired:
    # Use repaired arguments
    await execute_tool(result.repaired_args)
else:
    await execute_tool(original_args)
```

---

## Available Guards

### 1. SchemaStrictnessGuard

Validates tool arguments against JSON schemas before execution.

```python
from chuk_tool_processor.guards import SchemaStrictnessGuard, SchemaStrictnessConfig
from chuk_tool_processor.guards.models import EnforcementLevel

# Schema getter function
def get_schema(tool_name: str) -> dict | None:
    schemas = {
        "create_user": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "role": {"type": "string", "enum": ["admin", "user", "guest"]},
            },
            "required": ["name", "age"],
        }
    }
    return schemas.get(tool_name)

guard = SchemaStrictnessGuard(
    config=SchemaStrictnessConfig(
        mode=EnforcementLevel.BLOCK,  # BLOCK, WARN, or OFF
        coerce_types=True,             # Auto-convert "18" → 18
        allow_extra_fields=False,      # Block unknown fields
        reject_empty_strings=True,     # Block empty required strings
    ),
    get_schema=get_schema,
)

# Valid arguments
result = guard.check("create_user", {"name": "Alice", "age": 30})
assert result.allowed

# Type coercion (age as string)
result = guard.check("create_user", {"name": "Bob", "age": "25"})
assert result.repaired
assert result.repaired_args["age"] == 25  # Coerced to int

# Missing required field
result = guard.check("create_user", {"name": "Charlie"})
assert result.blocked
print(result.reason)  # "Missing required field: age"
```

**Validations:**
- Required fields present
- Type matching (string, integer, boolean, array, object)
- Enum value validation
- Unknown field detection
- Empty/whitespace string detection

---

### 2. SensitiveDataGuard

Detects and blocks or redacts secrets in arguments and outputs.

```python
from chuk_tool_processor.guards import SensitiveDataGuard, SensitiveDataConfig, RedactMode

guard = SensitiveDataGuard(
    config=SensitiveDataConfig(
        mode=EnforcementLevel.BLOCK,
        redact_mode=RedactMode.BLOCK,  # BLOCK, REDACT, or HASH
        check_args=True,
        check_output=True,
        allowlist={"test_key_12345"},  # Allow specific test keys
    )
)

# API key detected
result = guard.check("tool", {"config": "api_key=sk_fake_abc123def456"})
assert result.blocked
print(result.reason)  # "Sensitive data detected: api_key"

# Redaction mode
guard_redact = SensitiveDataGuard(
    config=SensitiveDataConfig(redact_mode=RedactMode.REDACT)
)
result = guard_redact.check("tool", {"key": "api_key=sk_fake_abc123"})
assert result.repaired
print(result.repaired_args)  # {"key": "[REDACTED]"}
```

**Detected Patterns:**
- API keys (`api_key=...`, `sk_fake_...`, `sk_test_...`)
- Bearer tokens (`Bearer eyJ...`)
- AWS access keys (`AKIA...`)
- Private keys (`-----BEGIN RSA PRIVATE KEY-----`)
- Passwords in URLs (`postgres://user:password@host`)
- JWT tokens (three-part base64)

---

### 3. NetworkPolicyGuard

SSRF defense — enforces network access policies.

```python
from chuk_tool_processor.guards import (
    NetworkPolicyGuard,
    NetworkPolicyConfig,
    DEFAULT_METADATA_IPS,
    DEFAULT_LOCALHOST_PATTERNS,
)

guard = NetworkPolicyGuard(
    config=NetworkPolicyConfig(
        block_private_ips=True,      # Block 10.x, 172.16.x, 192.168.x
        block_localhost=True,        # Block localhost, 127.0.0.1
        block_metadata_ips=True,     # Block 169.254.169.254 (AWS/GCP metadata)
        require_https=True,          # Block http:// URLs
        allowed_domains={"api.example.com", "cdn.example.com"},  # Whitelist
        # Customize blocked patterns (extend defaults):
        metadata_ips=set(DEFAULT_METADATA_IPS) | {"custom.metadata.internal"},
        localhost_patterns=set(DEFAULT_LOCALHOST_PATTERNS) | {"dev.local"},
        url_argument_names={"url", "endpoint", "webhook_url"},  # Custom URL arg names
    )
)

# Public URL allowed
result = guard.check("fetch", {"url": "https://api.example.com/data"})
assert result.allowed

# Localhost blocked
result = guard.check("fetch", {"url": "http://localhost:8080/admin"})
assert result.blocked
print(result.reason)  # "Localhost access blocked"

# Private IP blocked
result = guard.check("fetch", {"url": "http://192.168.1.1/internal"})
assert result.blocked

# Cloud metadata blocked
result = guard.check("fetch", {"url": "http://169.254.169.254/latest/meta-data"})
assert result.blocked
```

**Checks URL arguments:** `url`, `endpoint`, `host`, `target`, `destination`

---

### 4. SideEffectGuard

Controls read/write/destructive operations based on mode and environment.

```python
from chuk_tool_processor.guards import (
    SideEffectGuard, SideEffectConfig, ExecutionMode, Environment, SideEffectClass
)

guard = SideEffectGuard(
    config=SideEffectConfig(
        mode=ExecutionMode.WRITE_ALLOWED,  # READ_ONLY, WRITE_ALLOWED, DESTRUCTIVE_ALLOWED
        environment=Environment.PROD,       # DEV, STAGING, PROD
        prod_blocked_classes={SideEffectClass.DESTRUCTIVE},  # Block destructive in prod
        require_capability_token=False,
    )
)

# Read operations always allowed
result = guard.check("get_user", {})
assert result.allowed

# Write operations allowed in WRITE_ALLOWED mode
result = guard.check("create_user", {})
assert result.allowed

# Destructive operations blocked in production
result = guard.check("delete_user", {})
assert result.blocked
print(result.reason)  # "Tool 'delete_user' classified as destructive is blocked in production"

# Read-only mode for demos/evals
guard_readonly = SideEffectGuard(
    config=SideEffectConfig(mode=ExecutionMode.READ_ONLY)
)
result = guard_readonly.check("update_user", {})
assert result.blocked
```

**Tool Classification (automatic via heuristics):**
- `read_only`: get, list, search, read, fetch, query, describe
- `write`: create, update, put, post, write, save, insert
- `destructive`: delete, remove, drop, truncate, destroy, purge

---

### 5. ConcurrencyGuard

Limits simultaneous in-flight tool calls.

```python
from chuk_tool_processor.guards import ConcurrencyGuard, ConcurrencyConfig

guard = ConcurrencyGuard(
    config=ConcurrencyConfig(
        global_max=50,                          # Total concurrent calls
        default_tool_max=10,                    # Per-tool default
        per_tool_max={"heavy_api": 2},          # Specific tool limits
        default_namespace_max=20,               # Per-namespace default
        per_namespace_max={"external": 5},      # Specific namespace limits
        per_session_max=10,                     # Per-session limit
    )
)

# Acquire slot before execution
result = await guard.acquire("heavy_api", session_id="user-123")
if result.blocked:
    print(f"Rate limited: {result.reason}")
else:
    try:
        await execute_tool()
    finally:
        await guard.release("heavy_api", session_id="user-123")

# Or use context manager
async with guard.slot("heavy_api"):
    await execute_tool()
```

---

### 6. TimeoutBudgetGuard

Enforces wall-clock time budgets across tool executions.

```python
from chuk_tool_processor.guards import TimeoutBudgetGuard, TimeoutBudgetConfig

guard = TimeoutBudgetGuard(
    config=TimeoutBudgetConfig(
        per_turn_budget_ms=30000,    # 30 second hard limit
        soft_budget_ratio=0.8,       # Warn at 80% (24s)
        degrade_actions=["disable_retries", "reduce_parallelism"],
    )
)

# Start timing
guard.start_turn()

# Check budget before each call
result = guard.check("tool", {})
if result.verdict == GuardVerdict.WARN:
    print("Approaching timeout, degrading...")
    # Reduce parallelism, disable retries, etc.
elif result.blocked:
    print("Time budget exceeded")

# Record execution time
guard.record_execution(500)  # 500ms

# Get stats
print(f"Elapsed: {guard.get_turn_elapsed_ms()}ms")
print(f"Remaining: {guard.get_remaining_budget_ms()}ms")
```

---

### 7. OutputSizeGuard

Prevents pathological payloads from overwhelming context or storage.

```python
from chuk_tool_processor.guards import OutputSizeGuard, OutputSizeConfig, TruncationMode

guard = OutputSizeGuard(
    config=OutputSizeConfig(
        max_bytes=100_000,           # 100KB max
        max_array_length=1000,       # Max items in arrays
        max_depth=20,                # Max nesting depth
        max_string_length=10_000,    # Max chars per string before truncation
        max_tokens=25_000,           # Optional token limit (chars/4 estimate)
        chars_per_token=4,           # Token estimation ratio
        truncation_mode=TruncationMode.ERROR,  # ERROR, TRUNCATE, or PAGINATE
    )
)

# Check output after execution
result = guard.check_output("tool", {}, {"items": list(range(2000))})
assert result.blocked
print(result.reason)  # "array_length_exceeded: 2000 > 1000"

# Truncation mode repairs instead of blocking
guard_truncate = OutputSizeGuard(
    config=OutputSizeConfig(truncation_mode=TruncationMode.TRUNCATE)
)
result = guard_truncate.check_output("tool", {}, {"data": "x" * 200_000})
assert result.repaired
print(len(result.repaired_output["data"]))  # Truncated
```

---

### 8. RetrySafetyGuard

Guards retry behavior to prevent abuse and ensure safety.

```python
from chuk_tool_processor.guards import RetrySafetyGuard, RetrySafetyConfig

guard = RetrySafetyGuard(
    config=RetrySafetyConfig(
        max_same_signature_retries=3,
        non_retryable_errors={"validation", "auth", "permission"},
        require_idempotency_key=True,  # For non-idempotent tools
        enforce_backoff=True,
        min_backoff_ms=100,
    )
)

# Track retries by signature
result = guard.check("db_query", {"sql": "SELECT *"})  # Attempt 1 - OK
result = guard.check("db_query", {"sql": "SELECT *"})  # Attempt 2 - OK
result = guard.check("db_query", {"sql": "SELECT *"})  # Attempt 3 - OK
result = guard.check("db_query", {"sql": "SELECT *"})  # Attempt 4 - BLOCKED

# Non-retryable error check
guard.record_error("api_call", {"id": 1}, "validation")
result = guard.check("api_call", {"id": 1})
assert result.blocked
print(result.reason)  # "Error class 'validation' is non-retryable"

# Idempotency key required
result = guard.check("create_order", {"item": "widget"})  # No key - BLOCKED
result = guard.check("create_order", {"item": "widget", "_idempotency_key": "abc123"})  # OK
```

---

### 9. ProvenanceGuard

Tracks output attribution and lineage.

```python
from chuk_tool_processor.guards import ProvenanceGuard, ProvenanceConfig

guard = ProvenanceGuard(
    config=ProvenanceConfig(
        require_attribution=True,
        track_lineage=True,
        max_unattributed_uses=0,
    )
)

# Record output and get reference ID
ref_id = guard.record_output("fetch_data", {"url": "..."}, {"data": [1, 2, 3]})
print(ref_id)  # "fetch_data:abc123def:1703001234567"

# Record dependent output with parent reference
child_ref = guard.record_output(
    "transform_data",
    {"input_ref": ref_id},
    {"transformed": [2, 4, 6]},
    parent_refs=[ref_id]
)

# Get provenance
provenance = guard.get_provenance(ref_id)
print(provenance)  # {"tool": "fetch_data", "args_hash": "abc123", "timestamp": ...}

# Get lineage chain
lineage = guard.get_lineage(child_ref)
print(lineage)  # [child_record, parent_record]

# Validate references before use
result = guard.check("use_data", {"ref": ref_id})  # Valid reference - OK
result = guard.check("use_data", {"ref": "fake:invalid:123"})  # Invalid - WARN/BLOCK
```

---

### 10. PlanShapeGuard

Detects pathological execution patterns in batches and sequences.

```python
from chuk_tool_processor.guards import PlanShapeGuard, PlanShapeConfig

guard = PlanShapeGuard(
    config=PlanShapeConfig(
        max_chain_length=20,         # Max sequential calls
        max_unique_tools=15,         # Max different tools in one plan
        max_fan_out=100,             # Max parallel calls from one point
        max_batch_size=500,          # Max calls in one batch
        detect_fan_out_fan_in=True,  # Detect explosion patterns
    )
)

# Check a batch of calls
calls = [{"tool": f"tool_{i}", "args": {}} for i in range(600)]
result = guard.check_batch(calls)
assert result.blocked
print(result.reason)  # "batch_too_large: 600 > 500"

# Check for fan-out explosion
parallel_calls = [{"tool": "api.fetch", "args": {"id": i}} for i in range(150)]
result = guard.check_batch(parallel_calls)
assert result.blocked
print(result.reason)  # "fan_out_too_large: 150 > 100"

# Track chain length incrementally
for i in range(25):
    guard.record_call(f"step_{i}")
result = guard.check("next_step", {})
assert result.blocked
print(result.reason)  # "chain_too_long: 25 > 20"
```

---

### 11. SaturationGuard

Detects degenerate statistical outputs - catches common model errors in statistical calculations.

```python
from chuk_tool_processor.guards import SaturationGuard, SaturationGuardConfig

guard = SaturationGuard(
    config=SaturationGuardConfig(
        # Tools that compute CDFs (must be explicitly configured)
        cdf_tools={"normal_cdf", "t_cdf", "chi2_cdf"},
        # Maximum |Z| before warning (8σ is essentially 0/1)
        z_threshold=8.0,
        # Block instead of warn on extreme inputs
        block_on_extreme=False,
        # Consecutive degenerate outputs before warning
        max_consecutive_degenerate=3,
        # Values considered degenerate (must be explicitly configured)
        degenerate_values={0.0, 1.0},
        # Tolerance for matching degenerate values
        tolerance=1e-9,
    )
)

# Pre-execution: Check for extreme Z-score inputs
result = guard.check("normal_cdf", {"x": 100, "mean": 0, "std": 1})
if result.warned:
    print(result.reason)
    # "SATURATION_WARNING: `normal_cdf` called with extreme Z-score |Z|=100.00 > 8.0..."

# Post-execution: Check for degenerate outputs
result = guard.check_output("normal_cdf", {"result": 1.0})
# After 3 consecutive 0.0 or 1.0 results, warns about calculation errors

# Reset state between prompts
guard.reset()

# Get current status
status = guard.get_status()
print(status)  # {"consecutive_degenerate": 0, "recent_results": []}
```

**Use Cases:**
- Statistical tools (normal_cdf, t_test, chi_square)
- Detecting upstream calculation errors
- Preventing models from continuing with garbage values

**Key Features:**
- Pre-execution check for extreme Z-score inputs
- Post-execution check for consecutive degenerate outputs
- Configurable thresholds and tool lists
- No hardcoded defaults - must explicitly configure which tools to monitor

---

## Guard Chain

Compose multiple guards into a pipeline:

```python
from chuk_tool_processor.guards import GuardChain, create_default_guard_chain

# Create with explicit guards
chain = GuardChain([
    SchemaStrictnessGuard(get_schema=my_getter),
    SensitiveDataGuard(),
    NetworkPolicyGuard(),
    SideEffectGuard(),
    ConcurrencyGuard(),
])

# Or use default chain with all guards
chain = create_default_guard_chain(
    get_schema=my_getter,
    get_classification=my_classifier,
)

# Check all guards
result = await chain.check_all_async("api.fetch", {"url": "https://..."})

# Result includes:
# - result.final_verdict: Overall verdict (ALLOW, WARN, BLOCK, REPAIR)
# - result.stopped_at: Which guard blocked/repaired (if any)
# - result.reason: Combined reason message
# - result.repaired_args: Modified arguments (if REPAIR)
# - result.details: Per-guard details

# Post-execution check (for OutputSizeGuard, SensitiveDataGuard output check)
output_result = await chain.check_output_async("tool", {}, {"response": "..."})
```

---

## Enforcement Levels

All guards support three enforcement levels:

```python
from chuk_tool_processor.guards.models import EnforcementLevel

# OFF - Guard is disabled
config = SomeConfig(mode=EnforcementLevel.OFF)

# WARN - Log warning but allow execution
config = SomeConfig(mode=EnforcementLevel.WARN)

# BLOCK - Prevent execution
config = SomeConfig(mode=EnforcementLevel.BLOCK)
```

---

## Recommended Guard Order

For optimal protection, order guards from fast-fail to resource-intensive:

1. **SchemaStrictnessGuard** — Fail fast on invalid args
2. **SensitiveDataGuard** (args) — Block secrets before execution
3. **NetworkPolicyGuard** — SSRF defense
4. **SideEffectGuard** — Permission check
5. **ConcurrencyGuard** — Resource limits
6. **TimeoutBudgetGuard** — Time limits
7. **PlanShapeGuard** — Structural limits
8. **RetrySafetyGuard** — Retry policy

Post-execution:
9. **OutputSizeGuard** — Size limits
10. **SensitiveDataGuard** (output) — Redact secrets in output
11. **ProvenanceGuard** — Track attribution

---

## Example: Complete Guard Setup

```python
from chuk_tool_processor.guards import (
    GuardChain,
    SchemaStrictnessGuard, SchemaStrictnessConfig,
    SensitiveDataGuard, SensitiveDataConfig, RedactMode,
    NetworkPolicyGuard, NetworkPolicyConfig,
    SideEffectGuard, SideEffectConfig, ExecutionMode, Environment,
    ConcurrencyGuard, ConcurrencyConfig,
    TimeoutBudgetGuard, TimeoutBudgetConfig,
    OutputSizeGuard, OutputSizeConfig,
)
from chuk_tool_processor.guards.models import EnforcementLevel

# Create production guard chain
chain = GuardChain([
    # Schema validation
    SchemaStrictnessGuard(
        config=SchemaStrictnessConfig(
            mode=EnforcementLevel.BLOCK,
            coerce_types=True,
        ),
        get_schema=my_schema_getter,
    ),

    # Secret detection
    SensitiveDataGuard(
        config=SensitiveDataConfig(
            mode=EnforcementLevel.BLOCK,
            redact_mode=RedactMode.REDACT,
        )
    ),

    # Network policy
    NetworkPolicyGuard(
        config=NetworkPolicyConfig(
            block_private_ips=True,
            block_metadata_ips=True,
            require_https=True,
        )
    ),

    # Side effect control
    SideEffectGuard(
        config=SideEffectConfig(
            mode=ExecutionMode.WRITE_ALLOWED,
            environment=Environment.PROD,
        )
    ),

    # Concurrency limits
    ConcurrencyGuard(
        config=ConcurrencyConfig(
            global_max=100,
            per_tool_max={"expensive_api": 5},
        )
    ),

    # Time budget
    TimeoutBudgetGuard(
        config=TimeoutBudgetConfig(
            per_turn_budget_ms=30000,
        )
    ),

    # Output size limits
    OutputSizeGuard(
        config=OutputSizeConfig(
            max_bytes=500_000,
            max_array_length=10000,
        )
    ),
])

# Use in tool execution
async def execute_with_guards(tool_name: str, args: dict):
    # Pre-execution check
    pre_result = await chain.check_all_async(tool_name, args)

    if pre_result.blocked:
        return {"error": pre_result.reason, "blocked_by": pre_result.stopped_at}

    # Use repaired args if available
    final_args = pre_result.repaired_args or args

    # Execute tool
    output = await execute_tool(tool_name, final_args)

    # Post-execution check
    post_result = await chain.check_output_async(tool_name, final_args, output)

    if post_result.blocked:
        return {"error": post_result.reason}

    return post_result.repaired_output or output
```

---

## Running the Demo

See all guards in action:

```bash
python examples/guards_demo.py
```

This demonstrates each guard with various scenarios showing ALLOWED, BLOCKED, WARNING, and REPAIRED verdicts.
