#!/usr/bin/env python3
"""Demonstration of all runtime constitution guards.

This example shows how to use each guard individually and how to compose
them together using GuardChain for comprehensive runtime protection.

Run with: python examples/guards_demo.py
"""

from __future__ import annotations

import asyncio

from chuk_tool_processor.guards import (
    ConcurrencyConfig,
    ConcurrencyGuard,
    # Default constants for customization
    DEFAULT_LOCALHOST_PATTERNS,
    DEFAULT_METADATA_IPS,
    EnforcementLevel,
    Environment,
    ExecutionMode,
    GuardChain,
    # Base types
    GuardVerdict,
    NetworkPolicyConfig,
    NetworkPolicyGuard,
    OutputSizeConfig,
    OutputSizeGuard,
    PlanShapeConfig,
    PlanShapeGuard,
    ProvenanceConfig,
    ProvenanceGuard,
    RedactMode,
    RetrySafetyConfig,
    RetrySafetyGuard,
    SaturationGuard,
    SaturationGuardConfig,
    SchemaStrictnessConfig,
    # Guards
    SchemaStrictnessGuard,
    SensitiveDataConfig,
    SensitiveDataGuard,
    SideEffectConfig,
    SideEffectGuard,
    TimeoutBudgetConfig,
    TimeoutBudgetGuard,
    ToolCallSpec,
    TruncationMode,
)


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print("=" * 60)


def print_result(description: str, result) -> None:
    """Print a guard result."""
    # Handle both GuardResult and GuardChainResult
    verdict = getattr(result, "verdict", None) or getattr(result, "final_verdict", None)
    reason = getattr(result, "reason", None) or getattr(result, "final_reason", None)

    status = "ALLOWED" if result.allowed else "BLOCKED"
    if verdict == GuardVerdict.WARN:
        status = "WARNING"
    elif verdict == GuardVerdict.REPAIR:
        status = "REPAIRED"

    print(f"\n  {description}")
    print(f"    Status: {status}")
    if reason:
        print(f"    Reason: {reason}")
    if hasattr(result, "repaired_args") and result.repaired_args:
        print(f"    Repaired args: {result.repaired_args}")


# =============================================================================
# 1. SchemaStrictnessGuard
# =============================================================================
def demo_schema_strictness():
    """Demonstrate schema validation guard."""
    print_section("1. SchemaStrictnessGuard - Validates arguments against JSON schemas")

    # Define a schema for a user creation tool
    user_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "email": {"type": "string"},
            "role": {"type": "string", "enum": ["admin", "user", "guest"]},
        },
        "required": ["name", "age"],
    }

    # Create guard with schema lookup
    guard = SchemaStrictnessGuard(
        config=SchemaStrictnessConfig(
            mode=EnforcementLevel.BLOCK,
            coerce_types=False,
            allow_extra_fields=False,
        ),
    )
    guard._schema_cache["create_user"] = user_schema

    # Test cases
    print_result(
        "Valid arguments",
        guard.check("create_user", {"name": "Alice", "age": 30, "role": "admin"}),
    )

    print_result(
        "Missing required field (age)",
        guard.check("create_user", {"name": "Bob"}),
    )

    print_result(
        "Wrong type (age as string)",
        guard.check("create_user", {"name": "Charlie", "age": "thirty"}),
    )

    print_result(
        "Invalid enum value",
        guard.check("create_user", {"name": "Dave", "age": 25, "role": "superuser"}),
    )

    print_result(
        "Unknown field",
        guard.check("create_user", {"name": "Eve", "age": 28, "extra": "field"}),
    )

    # With type coercion enabled
    guard_coerce = SchemaStrictnessGuard(
        config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK, coerce_types=True),
    )
    guard_coerce._schema_cache["create_user"] = user_schema

    print_result(
        "Type coercion (age '25' -> 25)",
        guard_coerce.check("create_user", {"name": "Frank", "age": "25"}),
    )


# =============================================================================
# 2. OutputSizeGuard
# =============================================================================
def demo_output_size():
    """Demonstrate output size limiting guard."""
    print_section("2. OutputSizeGuard - Prevents pathological payload sizes")

    guard = OutputSizeGuard(
        config=OutputSizeConfig(
            max_bytes=1000,
            max_array_length=10,
            max_depth=3,
            truncation_mode=TruncationMode.ERROR,
        )
    )

    # Test cases (using check_output for post-execution)
    print_result(
        "Small result (OK)",
        guard.check_output("tool", {}, {"status": "success", "data": [1, 2, 3]}),
    )

    print_result(
        "Array too long",
        guard.check_output("tool", {}, {"items": list(range(100))}),
    )

    print_result(
        "Too deeply nested",
        guard.check_output("tool", {}, {"a": {"b": {"c": {"d": {"e": "deep"}}}}}),
    )

    large_data = "x" * 2000
    print_result(
        "Result too large (bytes)",
        guard.check_output("tool", {}, {"data": large_data}),
    )

    # With truncation mode
    guard_truncate = OutputSizeGuard(
        config=OutputSizeConfig(
            max_bytes=100,
            truncation_mode=TruncationMode.TRUNCATE,
        )
    )
    print_result(
        "Truncation mode (repairs instead of blocking)",
        guard_truncate.check_output("tool", {}, {"data": "x" * 200}),
    )


# =============================================================================
# 3. SensitiveDataGuard
# =============================================================================
def demo_sensitive_data():
    """Demonstrate sensitive data detection guard."""
    print_section("3. SensitiveDataGuard - Detects and blocks secrets")

    guard = SensitiveDataGuard(
        config=SensitiveDataConfig(
            mode=EnforcementLevel.BLOCK,
            redact_mode=RedactMode.BLOCK,
        )
    )

    # Test cases
    print_result(
        "Clean arguments (OK)",
        guard.check("tool", {"name": "Alice", "count": 5}),
    )

    print_result(
        "API key detected",
        guard.check("tool", {"config": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"}),
    )

    print_result(
        "AWS access key detected",
        guard.check("tool", {"key": "AKIAIOSFODNN7EXAMPLE"}),
    )

    print_result(
        "Password in URL detected",
        guard.check("tool", {"url": "postgres://user:secret123@localhost/db"}),
    )

    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
    print_result(
        "JWT token detected",
        guard.check("tool", {"token": jwt}),
    )

    # With redaction mode
    guard_redact = SensitiveDataGuard(
        config=SensitiveDataConfig(
            mode=EnforcementLevel.BLOCK,
            redact_mode=RedactMode.REDACT,
        )
    )
    print_result(
        "Redaction mode (repairs by redacting)",
        guard_redact.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"}),
    )


# =============================================================================
# 4. ConcurrencyGuard
# =============================================================================
async def demo_concurrency():
    """Demonstrate concurrency limiting guard."""
    print_section("4. ConcurrencyGuard - Limits simultaneous in-flight calls")

    guard = ConcurrencyGuard(
        config=ConcurrencyConfig(
            global_max=3,
            default_tool_max=2,
            default_namespace_max=5,
        )
    )

    print(f"\n  Initial state: {guard.get_state().global_in_flight} in flight")

    # Acquire some slots
    await guard.acquire("tool_a")
    await guard.acquire("tool_b")
    print(f"  After 2 acquires: {guard.get_state().global_in_flight} in flight")

    result = await guard.acquire("tool_c")
    print_result("Third acquire (at limit)", result)

    result = await guard.acquire("tool_d")
    print_result("Fourth acquire (exceeds global limit)", result)

    # Release and try again
    await guard.release("tool_a")
    result = await guard.acquire("tool_d")
    print_result("After release, fourth acquire", result)

    # Per-tool limit
    guard.reset()
    await guard.acquire("heavy_tool")
    await guard.acquire("heavy_tool")
    result = await guard.acquire("heavy_tool")
    print_result("Per-tool limit exceeded", result)

    # Using context manager
    guard.reset()
    print("\n  Using async context manager:")
    async with guard.slot("my_tool"):
        print(f"    Inside slot: {guard.get_state().global_in_flight} in flight")
    print(f"    After slot: {guard.get_state().global_in_flight} in flight")


# =============================================================================
# 5. NetworkPolicyGuard
# =============================================================================
def demo_network_policy():
    """Demonstrate network policy guard (SSRF defense)."""
    print_section("5. NetworkPolicyGuard - SSRF defense and network policies")

    guard = NetworkPolicyGuard(
        config=NetworkPolicyConfig(
            mode=EnforcementLevel.BLOCK,
            block_private_ips=True,
            block_metadata_ips=True,
            require_https=False,
        )
    )

    # Test cases
    print_result(
        "Public URL (OK)",
        guard.check("http_get", {"url": "https://api.example.com/v1/users"}),
    )

    print_result(
        "Localhost blocked",
        guard.check("http_get", {"url": "http://localhost:8080/admin"}),
    )

    print_result(
        "Private IP blocked (192.168.x.x)",
        guard.check("http_get", {"url": "http://192.168.1.1/internal"}),
    )

    print_result(
        "Cloud metadata IP blocked",
        guard.check("http_get", {"url": "http://169.254.169.254/latest/meta-data"}),
    )

    # With HTTPS requirement
    guard_https = NetworkPolicyGuard(
        config=NetworkPolicyConfig(
            mode=EnforcementLevel.BLOCK,
            require_https=True,
        )
    )
    print_result(
        "HTTP blocked (HTTPS required)",
        guard_https.check("http_get", {"url": "http://api.example.com/data"}),
    )

    # With domain whitelist
    guard_whitelist = NetworkPolicyGuard(
        config=NetworkPolicyConfig(
            mode=EnforcementLevel.BLOCK,
            allowed_domains={"api.trusted.com", "cdn.trusted.com"},
        )
    )
    print_result(
        "Whitelisted domain (OK)",
        guard_whitelist.check("http_get", {"url": "https://api.trusted.com/data"}),
    )
    print_result(
        "Non-whitelisted domain blocked",
        guard_whitelist.check("http_get", {"url": "https://api.other.com/data"}),
    )

    # Custom patterns (extending defaults)
    print("\n  Custom patterns example:")
    custom_guard = NetworkPolicyGuard(
        config=NetworkPolicyConfig(
            mode=EnforcementLevel.BLOCK,
            # Extend default patterns with custom ones
            metadata_ips=set(DEFAULT_METADATA_IPS) | {"custom.metadata.internal"},
            localhost_patterns=set(DEFAULT_LOCALHOST_PATTERNS) | {"dev.local"},
            url_argument_names={"url", "endpoint", "webhook_url", "callback"},
        )
    )
    print(f"    Default metadata IPs: {len(DEFAULT_METADATA_IPS)}")
    print(f"    Custom metadata IPs: {len(custom_guard.config.metadata_ips)}")
    print(f"    Custom localhost patterns: {custom_guard.config.localhost_patterns}")


# =============================================================================
# 6. SideEffectGuard
# =============================================================================
def demo_side_effect():
    """Demonstrate side effect classification guard."""
    print_section("6. SideEffectGuard - Controls read/write/destructive operations")

    # Read-only mode (for evals, demos)
    guard_readonly = SideEffectGuard(
        config=SideEffectConfig(
            mode=ExecutionMode.READ_ONLY,
            environment=Environment.DEV,
        )
    )

    print("\n  Mode: READ_ONLY")
    print_result(
        "Read operation (get_user) - OK",
        guard_readonly.check("get_user", {"id": 123}),
    )
    print_result(
        "Write operation (create_user) - blocked",
        guard_readonly.check("create_user", {"name": "Alice"}),
    )

    # Write-allowed mode
    guard_write = SideEffectGuard(
        config=SideEffectConfig(
            mode=ExecutionMode.WRITE_ALLOWED,
            environment=Environment.DEV,
        )
    )

    print("\n  Mode: WRITE_ALLOWED")
    print_result(
        "Write operation (create_user) - OK",
        guard_write.check("create_user", {"name": "Alice"}),
    )
    print_result(
        "Destructive operation (delete_user) - blocked",
        guard_write.check("delete_user", {"id": 123}),
    )

    # Production environment blocks destructive even if allowed
    guard_prod = SideEffectGuard(
        config=SideEffectConfig(
            mode=ExecutionMode.DESTRUCTIVE_ALLOWED,
            environment=Environment.PROD,
        )
    )

    print("\n  Mode: DESTRUCTIVE_ALLOWED, Environment: PROD")
    print_result(
        "Destructive in production - blocked",
        guard_prod.check("delete_user", {"id": 123}),
    )


# =============================================================================
# 7. TimeoutBudgetGuard
# =============================================================================
def demo_timeout_budget():
    """Demonstrate timeout budget guard."""
    print_section("7. TimeoutBudgetGuard - Enforces wall-clock time limits")

    import time

    guard = TimeoutBudgetGuard(
        config=TimeoutBudgetConfig(
            per_turn_budget_ms=100,  # 100ms for demo
            soft_budget_ratio=0.5,  # 50ms soft limit
        )
    )

    print("\n  Budget: 100ms (soft limit at 50ms)")

    guard.start_turn()
    print(f"  Remaining: {guard.get_remaining_budget_ms()}ms")

    result = guard.check("tool", {})
    print_result("Immediate check (OK)", result)

    time.sleep(0.06)  # 60ms - past soft limit
    result = guard.check("tool", {})
    print_result("After 60ms (past soft limit)", result)
    print(f"    Degraded: {guard.is_degraded()}")

    time.sleep(0.05)  # Total ~110ms - past hard limit
    result = guard.check("tool", {})
    print_result("After 110ms (past hard limit)", result)

    # End turn and check stats
    stats = guard.end_turn()
    print(f"\n  Turn stats: {stats.turn_elapsed_ms}ms elapsed")


# =============================================================================
# 8. RetrySafetyGuard
# =============================================================================
def demo_retry_safety():
    """Demonstrate retry safety guard."""
    print_section("8. RetrySafetyGuard - Guards retry behavior")

    from chuk_tool_processor.guards.retry_safety import ErrorClass

    guard = RetrySafetyGuard(
        config=RetrySafetyConfig(
            max_same_signature_retries=3,
            enforce_backoff=False,  # Disable for demo
        )
    )

    args = {"query": "SELECT * FROM users"}

    print("\n  Max retries: 3")

    # Simulate retries
    for i in range(4):
        guard.record_attempt("db_query", args)
        result = guard.check("db_query", args)
        print_result(f"Attempt {i + 1}", result)
        if result.blocked:
            break

    # Non-retryable errors
    guard.reset()
    guard.record_attempt("api_call", {"x": 1}, error_class=ErrorClass.VALIDATION)
    result = guard.check_retry_after_error("api_call", {"x": 1}, ErrorClass.VALIDATION)
    print_result("Retry after validation error (non-retryable)", result)

    # Retryable errors
    guard.reset()
    guard.record_attempt("api_call", {"x": 1}, error_class=ErrorClass.TIMEOUT)
    result = guard.check_retry_after_error("api_call", {"x": 1}, ErrorClass.TIMEOUT)
    print_result("Retry after timeout error (retryable)", result)

    # Idempotency key requirement
    guard_idem = RetrySafetyGuard(
        config=RetrySafetyConfig(
            require_idempotency_key=True,
            non_idempotent_tools={"create_order"},
        )
    )
    guard_idem.record_attempt("create_order", {"item": "product"})
    result = guard_idem.check("create_order", {"item": "product"})
    print_result("Non-idempotent tool without key", result)

    result = guard_idem.check("create_order", {"item": "product", "_idempotency_key": "order-123"})
    print_result("Non-idempotent tool with key", result)


# =============================================================================
# 9. ProvenanceGuard
# =============================================================================
def demo_provenance():
    """Demonstrate provenance tracking guard."""
    print_section("9. ProvenanceGuard - Tracks output attribution")

    guard = ProvenanceGuard(
        config=ProvenanceConfig(
            require_attribution=True,
            track_lineage=True,
            enforcement_level=EnforcementLevel.WARN,
        )
    )

    # Record some outputs
    ref1 = guard.record_output("fetch_data", {"source": "api"}, {"users": [1, 2, 3]})
    print(f"\n  Recorded output, ref: {ref1}")

    ref2 = guard.record_output(
        "transform_data",
        {"_ref": ref1},  # References first output
        {"transformed": True},
    )
    print(f"  Recorded dependent output, ref: {ref2}")

    # Check provenance
    record = guard.get_provenance(ref1)
    print(f"\n  Provenance for {ref1}:")
    print(f"    Tool: {record.tool_name}")
    print(f"    Timestamp: {record.timestamp_ms}")

    # Get lineage
    lineage = guard.get_lineage(ref2)
    print(f"\n  Lineage for {ref2}: {len(lineage)} records")
    for rec in lineage:
        print(f"    - {rec.tool_name}: {rec.reference_id}")

    # Check with valid reference
    result = guard.check("use_data", {"_ref": ref1})
    print_result("Using valid reference", result)

    # Check with invalid reference
    result = guard.check("use_data", {"_ref": "fake:abc123def456:1234567890"})
    print_result("Using invalid reference", result)


# =============================================================================
# 10. PlanShapeGuard
# =============================================================================
def demo_plan_shape():
    """Demonstrate plan shape guard."""
    print_section("10. PlanShapeGuard - Detects pathological execution patterns")

    guard = PlanShapeGuard(
        config=PlanShapeConfig(
            max_chain_length=5,
            max_unique_tools=3,
            max_fan_out=10,
            max_batch_size=20,
        )
    )

    print("\n  Limits: chain=5, unique_tools=3, fan_out=10, batch=20")

    # Valid plan
    valid_plan = [
        ToolCallSpec(tool_name="fetch"),
        ToolCallSpec(tool_name="transform", depends_on=["fetch"]),
        ToolCallSpec(tool_name="save", depends_on=["transform"]),
    ]
    result = guard.check_plan(valid_plan)
    print_result("Valid plan (3 tools, chain=3)", result)

    # Too many unique tools
    many_tools_plan = [ToolCallSpec(tool_name=f"tool_{i}") for i in range(5)]
    result = guard.check_plan(many_tools_plan)
    print_result("Too many unique tools (5 > 3)", result)

    # Excessive fan-out
    fan_out_plan = [ToolCallSpec(tool_name="worker", depends_on=["source"]) for _ in range(15)]
    result = guard.check_plan(fan_out_plan)
    print_result("Excessive fan-out (15 parallel calls)", result)

    # Check batch
    large_batch = [("tool", {}) for _ in range(25)]
    result = guard.check_batch(large_batch)
    print_result("Batch too large (25 > 20)", result)

    # Track execution
    guard.reset()
    for i in range(6):
        guard.record_call(f"step_{i % 2}")  # Alternating tools
    result = guard.check("another_tool", {})
    print_result("Chain too long (6 calls)", result)


# =============================================================================
# 11. SaturationGuard
# =============================================================================
def demo_saturation():
    """Demonstrate saturation sanity guard for statistical outputs."""
    print_section("11. SaturationGuard - Detects degenerate statistical outputs")

    guard = SaturationGuard(
        config=SaturationGuardConfig(
            cdf_tools={"normal_cdf", "t_cdf", "chi2_cdf"},
            z_threshold=8.0,
            block_on_extreme=False,  # Warn instead of block
            max_consecutive_degenerate=3,
            degenerate_values={0.0, 1.0},
        )
    )

    print("\n  Configuration:")
    print(f"    CDF tools: {guard.config.cdf_tools}")
    print(f"    Z-threshold: {guard.config.z_threshold}")
    print(f"    Degenerate values: {guard.config.degenerate_values}")

    # Test pre-execution check (extreme Z-scores)
    print("\n  Pre-execution checks (input validation):")

    print_result(
        "Normal Z-score (x=1.5, mean=0, std=1) - OK",
        guard.check("normal_cdf", {"x": 1.5, "mean": 0, "std": 1}),
    )

    print_result(
        "Extreme Z-score (x=100, mean=0, std=1) - Warning",
        guard.check("normal_cdf", {"x": 100, "mean": 0, "std": 1}),
    )

    print_result(
        "Extreme Z-score (x=-50, mean=0, std=1) - Warning",
        guard.check("normal_cdf", {"x": -50, "mean": 0, "std": 1}),
    )

    # Non-CDF tool passes through
    print_result(
        "Non-CDF tool (ignored)",
        guard.check("calculate_mean", {"values": [1, 2, 3]}),
    )

    # Test post-execution check (degenerate outputs)
    print("\n  Post-execution checks (output validation):")
    guard.reset()

    print_result(
        "Normal output (0.84) - OK",
        guard.check_output("normal_cdf", {}, 0.8413),
    )

    print_result(
        "Degenerate output (1.0) - tracked",
        guard.check_output("normal_cdf", {}, 1.0),
    )

    print_result(
        "Second degenerate (1.0) - tracked",
        guard.check_output("normal_cdf", {}, 1.0),
    )

    print_result(
        "Third degenerate (1.0) - Warning triggered",
        guard.check_output("normal_cdf", {}, 1.0),
    )

    # Reset and test mixed outputs
    guard.reset()
    print("\n  Mixed outputs reset the counter:")
    guard.check_output("normal_cdf", {}, 1.0)  # First degenerate
    guard.check_output("normal_cdf", {}, 0.5)  # Normal - resets counter
    print(f"    After normal output, consecutive count: {guard.get_status()['consecutive_degenerate']}")

    # Block mode
    guard_block = SaturationGuard(
        config=SaturationGuardConfig(
            cdf_tools={"normal_cdf"},
            z_threshold=8.0,
            block_on_extreme=True,
        )
    )
    print("\n  Block mode (block_on_extreme=True):")
    print_result(
        "Extreme input blocked",
        guard_block.check("normal_cdf", {"x": 100, "mean": 0, "std": 1}),
    )


# =============================================================================
# GuardChain - Composing Guards
# =============================================================================
def demo_guard_chain():
    """Demonstrate composing guards with GuardChain."""
    print_section("GuardChain - Composing multiple guards")

    # Create individual guards
    schema_guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK))
    schema_guard._schema_cache["api_call"] = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "enum": ["GET", "POST"]},
        },
        "required": ["url"],
    }

    network_guard = NetworkPolicyGuard(config=NetworkPolicyConfig(mode=EnforcementLevel.BLOCK))

    sensitive_guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK))

    # Create chain
    chain = GuardChain(
        [
            ("schema", schema_guard),
            ("network", network_guard),
            ("sensitive", sensitive_guard),
        ]
    )

    print(f"\n  Chain has {len(chain)} guards")

    # Test various scenarios
    result = chain.check_all("api_call", {"url": "https://api.example.com/users", "method": "GET"})
    print_result("Valid call (passes all guards)", result)

    result = chain.check_all("api_call", {"method": "GET"})  # Missing url
    print_result("Missing required field (blocked by schema)", result)
    if result.stopped_at:
        print(f"    Stopped at: {result.stopped_at}")

    result = chain.check_all("api_call", {"url": "http://localhost:8080/admin"})
    print_result("Localhost URL (blocked by network)", result)
    if result.stopped_at:
        print(f"    Stopped at: {result.stopped_at}")

    result = chain.check_all(
        "api_call",
        {"url": "https://api.example.com", "auth": "api_key=sk_fake_secretkey123456789"},
    )
    print_result("Contains API key (blocked by sensitive)", result)
    if result.stopped_at:
        print(f"    Stopped at: {result.stopped_at}")

    # Using default chain
    print("\n  Creating default guard chain:")
    default_chain = GuardChain.create_default()
    print(f"    Contains {len(default_chain)} guards:")
    for name, _ in default_chain:
        print(f"      - {name}")


# =============================================================================
# Main
# =============================================================================
async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print(" RUNTIME CONSTITUTION GUARDS DEMONSTRATION")
    print("=" * 60)

    demo_schema_strictness()
    demo_output_size()
    demo_sensitive_data()
    await demo_concurrency()
    demo_network_policy()
    demo_side_effect()
    demo_timeout_budget()
    demo_retry_safety()
    demo_provenance()
    demo_plan_shape()
    demo_saturation()
    demo_guard_chain()

    print("\n" + "=" * 60)
    print(" DEMONSTRATION COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
