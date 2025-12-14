#!/usr/bin/env python
# examples/02_production_features/structured_errors_demo.py
"""
Demonstration of structured error taxonomy in chuk_tool_processor.

This script shows how planners can use machine-readable error categories
and retry hints to make intelligent decisions about:
- When to retry (and how long to wait)
- When to use a fallback tool
- When to report permanent failure

The structured error system enables planners to distinguish between:
- Rate limits (slow down, retry after delay)
- Circuit breaker open (service unhealthy, use fallback)
- Bulkhead full (system at capacity, backpressure)
- Timeout (retry, possibly with longer timeout)
- Validation errors (don't retry, fix the request)
- Not found (don't retry, wrong tool name)
"""

import asyncio

from chuk_tool_processor.core.exceptions import (
    BulkheadFullError,
    ErrorCategory,
    ErrorInfo,
    ToolCircuitOpenError,
    ToolRateLimitedError,
)
from chuk_tool_processor.models.tool_result import ToolResult


# -----------------------------------------------------------------------------
# Demo: Error Categories and Retryability
# -----------------------------------------------------------------------------
async def demo_error_categories() -> None:
    """Show all error categories and their retryability."""
    print("=" * 60)
    print("ERROR CATEGORIES AND RETRYABILITY")
    print("=" * 60)

    print("\nRetryable categories (may succeed if retried):")
    retryable = [
        (ErrorCategory.RATE_LIMIT, "Too many requests - wait and retry"),
        (ErrorCategory.CIRCUIT_OPEN, "Service unhealthy - wait for recovery"),
        (ErrorCategory.BULKHEAD_FULL, "System at capacity - backpressure"),
        (ErrorCategory.TIMEOUT, "Operation slow - retry, maybe longer timeout"),
        (ErrorCategory.EXECUTION, "Tool logic failed - retry if transient"),
        (ErrorCategory.CONNECTION, "Network error - retry with backoff"),
    ]
    for cat, desc in retryable:
        print(f"  {cat.value:15} - {desc}")

    print("\nNon-retryable categories (fix the request, don't retry):")
    non_retryable = [
        (ErrorCategory.VALIDATION, "Bad input/output - fix the request"),
        (ErrorCategory.NOT_FOUND, "Tool doesn't exist - check tool name"),
        (ErrorCategory.CANCELLED, "Operation cancelled - don't retry"),
        (ErrorCategory.CONFIGURATION, "System misconfigured - fix config"),
    ]
    for cat, desc in non_retryable:
        print(f"  {cat.value:15} - {desc}")


# -----------------------------------------------------------------------------
# Demo: Creating Structured Errors
# -----------------------------------------------------------------------------
async def demo_creating_errors() -> None:
    """Show how to create structured error information."""
    print("\n" + "=" * 60)
    print("CREATING STRUCTURED ERRORS")
    print("=" * 60)

    # From specific exception types
    print("\n1. From ToolCircuitOpenError:")
    circuit_err = ToolCircuitOpenError(
        tool_name="external_api",
        failure_count=5,
        reset_timeout=30.0,
    )
    info = circuit_err.to_error_info()
    print(f"   code: {info.code}")
    print(f"   category: {info.category}")
    print(f"   retryable: {info.retryable}")
    print(f"   retry_after_ms: {info.retry_after_ms}")
    print(f"   message: {info.message}")

    print("\n2. From ToolRateLimitedError:")
    rate_err = ToolRateLimitedError(
        tool_name="api_tool",
        retry_after=10.0,
        limit=100,
        period=60.0,
    )
    info = rate_err.to_error_info()
    print(f"   code: {info.code}")
    print(f"   category: {info.category}")
    print(f"   retryable: {info.retryable}")
    print(f"   retry_after_ms: {info.retry_after_ms}")

    print("\n3. From error string (backwards compatibility):")
    info = ErrorInfo.from_error_string(
        "Connection timeout after 30s",
        tool_name="slow_api",
    )
    print(f"   code: {info.code}")
    print(f"   category: {info.category}")
    print(f"   retryable: {info.retryable}")


# -----------------------------------------------------------------------------
# Demo: ToolResult with Structured Errors
# -----------------------------------------------------------------------------
async def demo_tool_result_errors() -> None:
    """Show how ToolResult exposes structured error information."""
    print("\n" + "=" * 60)
    print("TOOLRESULT WITH STRUCTURED ERRORS")
    print("=" * 60)

    # Create error result using factory method
    print("\n1. Using ToolResult.create_error() factory:")
    err = ToolCircuitOpenError("api", failure_count=5, reset_timeout=60.0)
    result = ToolResult.create_error(
        tool="api",
        error=err,
        attempts=3,
    )
    print(f"   result.error: {result.error[:50]}...")
    print(f"   result.error_category: {result.error_category}")
    print(f"   result.error_code: {result.error_code}")
    print(f"   result.retryable: {result.retryable}")
    print(f"   result.retry_after_ms: {result.retry_after_ms}")

    # Create with string error (auto-parsed)
    print("\n2. ToolResult with string error (auto-parsed):")
    result = ToolResult(
        tool="test",
        error="Rate limit exceeded, retry after 30 seconds",
    )
    print(f"   result.error: {result.error}")
    print(f"   result.error_category: {result.error_category}")
    print(f"   result.retryable: {result.retryable}")

    # Access full error_info
    print("\n3. Accessing full error_info:")
    if result.error_info:
        print(f"   error_info.code: {result.error_info.code}")
        print(f"   error_info.category: {result.error_info.category}")
        print(f"   error_info.details: {result.error_info.details}")
        print(f"   error_info.model_dump(): {result.error_info.model_dump()}")


# -----------------------------------------------------------------------------
# Demo: Planner Decision Making
# -----------------------------------------------------------------------------
async def demo_planner_decisions() -> None:
    """Show how a planner can use structured errors for decisions."""
    print("\n" + "=" * 60)
    print("PLANNER DECISION MAKING")
    print("=" * 60)

    # Simulate various error scenarios
    scenarios = [
        ToolResult.create_error(
            tool="api",
            error=ToolRateLimitedError("api", retry_after=5.0, limit=100),
        ),
        ToolResult.create_error(
            tool="api",
            error=ToolCircuitOpenError("api", failure_count=5, reset_timeout=30.0),
        ),
        ToolResult(tool="api", error="Tool 'unknown_tool' not found"),
        ToolResult(tool="api", error="Validation failed: missing required field 'query'"),
        ToolResult(tool="api", error="Connection timeout after 10s"),
    ]

    print("\nSimulating planner handling different error types:\n")

    for i, result in enumerate(scenarios, 1):
        print(f"Scenario {i}: {result.error[:50]}...")
        action = handle_error_like_planner(result)
        print(f"  Category: {result.error_category}")
        print(f"  Retryable: {result.retryable}")
        print(f"  Retry after: {result.retry_after_ms}ms" if result.retry_after_ms else "  Retry after: None")
        print(f"  Action: {action}")
        print()


def handle_error_like_planner(result: ToolResult) -> str:
    """
    Demonstrate how a planner would handle errors.

    This is the pattern planners should use for intelligent error handling.
    """
    if result.is_success:
        return "SUCCESS - use result"

    if result.error_info is None:
        return "UNKNOWN - treat as transient, retry with backoff"

    match result.error_info.category:
        case ErrorCategory.RATE_LIMIT:
            delay = result.retry_after_ms or 5000
            return f"RATE_LIMITED - wait {delay}ms, then retry"

        case ErrorCategory.CIRCUIT_OPEN:
            delay = result.retry_after_ms or 60000
            return f"CIRCUIT_OPEN - use fallback tool, or wait {delay}ms"

        case ErrorCategory.BULKHEAD_FULL:
            return "BULKHEAD_FULL - queue for later, apply backpressure"

        case ErrorCategory.TIMEOUT:
            return "TIMEOUT - retry with longer timeout"

        case ErrorCategory.EXECUTION:
            return "EXECUTION - retry if transient, report if persistent"

        case ErrorCategory.CONNECTION:
            return "CONNECTION - retry with exponential backoff"

        case ErrorCategory.VALIDATION:
            return "VALIDATION - report to user, don't retry"

        case ErrorCategory.NOT_FOUND:
            return "NOT_FOUND - check tool name, don't retry"

        case ErrorCategory.CANCELLED:
            return "CANCELLED - don't retry"

        case ErrorCategory.CONFIGURATION:
            return "CONFIGURATION - alert ops team, don't retry"

        case _:
            return "UNKNOWN - treat as transient, retry with backoff"


# -----------------------------------------------------------------------------
# Demo: Creating ToolResult with Different Error Types
# -----------------------------------------------------------------------------
async def demo_creating_tool_results() -> None:
    """Show how to create ToolResult with various error types."""
    print("\n" + "=" * 60)
    print("CREATING TOOLRESULT WITH VARIOUS ERROR TYPES")
    print("=" * 60)

    print("\nThis shows what planners would see from real middleware:")

    # Simulate circuit breaker error (from CircuitBreakerExecutor)
    cb_err = ToolCircuitOpenError("api", failure_count=5, reset_timeout=30.0)
    cb_result = ToolResult(
        tool="api",
        error=str(cb_err),
        error_info=cb_err.to_error_info(),
        machine="circuit_breaker",
        pid=0,
    )
    print("\n1. Circuit Breaker Error:")
    print(f"   Category: {cb_result.error_category}")
    print(f"   Retryable: {cb_result.retryable}")
    print(f"   Retry after: {cb_result.retry_after_ms}ms")

    # Simulate rate limit error
    rl_err = ToolRateLimitedError("api", retry_after=10.0, limit=100)
    rl_result = ToolResult(
        tool="api",
        error=str(rl_err),
        error_info=rl_err.to_error_info(),
    )
    print("\n2. Rate Limit Error:")
    print(f"   Category: {rl_result.error_category}")
    print(f"   Retryable: {rl_result.retryable}")
    print(f"   Retry after: {rl_result.retry_after_ms}ms")

    # Simulate bulkhead full error
    bh_err = BulkheadFullError("api", limit_type="global", limit=10, timeout=5.0)
    bh_result = ToolResult.create_error(tool="api", error=bh_err)
    print("\n3. Bulkhead Full Error:")
    print(f"   Category: {bh_result.error_category}")
    print(f"   Retryable: {bh_result.retryable}")

    # Simulate timeout error (auto-parsed from string)
    timeout_result = ToolResult(tool="api", error="Timeout after 30s")
    print("\n4. Timeout Error (from string):")
    print(f"   Category: {timeout_result.error_category}")
    print(f"   Retryable: {timeout_result.retryable}")

    # Simulate validation error (auto-parsed from string)
    validation_result = ToolResult(tool="api", error="Validation failed: invalid input")
    print("\n5. Validation Error (from string):")
    print(f"   Category: {validation_result.error_category}")
    print(f"   Retryable: {validation_result.retryable}")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
async def main() -> None:
    """Run all demos."""
    print("STRUCTURED ERROR TAXONOMY DEMO")
    print("=" * 60)
    print()
    print("This demo shows how planners can use machine-readable error")
    print("categories and retry hints to make intelligent decisions.")
    print()

    await demo_error_categories()
    await demo_creating_errors()
    await demo_tool_result_errors()
    await demo_planner_decisions()
    await demo_creating_tool_results()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("Key takeaways:")
    print("  1. Use result.error_category for high-level decisions")
    print("  2. Use result.retryable to know if retry makes sense")
    print("  3. Use result.retry_after_ms for smart backoff")
    print("  4. Use result.error_info.details for debugging")
    print()
    print("See docs/ERRORS.md for complete error taxonomy reference.")


if __name__ == "__main__":
    asyncio.run(main())
