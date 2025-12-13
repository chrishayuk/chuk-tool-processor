#!/usr/bin/env python3
"""
MCP Middleware Stack Demo

Demonstrates the MiddlewareStack for adding production-grade resilience
to MCP tool calls:
- Retry with exponential backoff
- Circuit breaker pattern
- Rate limiting

This example uses a mock StreamManager to show middleware behavior
without requiring an actual MCP server connection.

Usage:
    python examples/04_mcp_integration/middleware_demo.py
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from chuk_tool_processor.mcp.middleware import (
    CircuitBreakerSettings,
    MiddlewareConfig,
    MiddlewareStack,
    RateLimitSettings,
    RetrySettings,
)


def create_mock_stream_manager():
    """Create a mock StreamManager for demonstration."""
    manager = MagicMock()
    manager._direct_call_tool = AsyncMock()
    return manager


async def demo_basic_middleware():
    """Demonstrate basic middleware configuration and usage."""
    print("=" * 70)
    print("Demo 1: Basic Middleware Configuration")
    print("=" * 70)

    # Create mock stream manager
    stream_manager = create_mock_stream_manager()
    stream_manager._direct_call_tool.return_value = {
        "pages": [{"title": "Meeting Notes"}, {"title": "Project Plan"}]
    }

    # Configure middleware with all layers
    config = MiddlewareConfig(
        retry=RetrySettings(
            enabled=True,
            max_retries=3,
            base_delay=0.1,  # Short delay for demo
            max_delay=1.0,
            jitter=True,
        ),
        circuit_breaker=CircuitBreakerSettings(
            enabled=True,
            failure_threshold=5,
            success_threshold=2,
            reset_timeout=30.0,
        ),
        rate_limiting=RateLimitSettings(
            enabled=True,
            global_limit=100,
            period=60.0,
        ),
    )

    # Create middleware stack
    middleware = MiddlewareStack(stream_manager, config=config)

    print("\nMiddleware Configuration:")
    print(f"  Retry: enabled={config.retry.enabled}, max_retries={config.retry.max_retries}")
    print(f"  Circuit Breaker: enabled={config.circuit_breaker.enabled}, threshold={config.circuit_breaker.failure_threshold}")
    print(f"  Rate Limiting: enabled={config.rate_limiting.enabled}, limit={config.rate_limiting.global_limit}/min")

    # Execute a tool call
    print("\nExecuting tool call through middleware...")
    result = await middleware.call_tool(
        tool_name="notion.search_pages",
        arguments={"query": "meeting"},
        timeout=30.0,
    )

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Duration: {result.duration_ms:.2f}ms")
    print(f"  Attempts: {result.attempts}")
    if result.success:
        print(f"  Data: {result.result}")

    return middleware


async def demo_retry_behavior():
    """Demonstrate retry behavior on transient failures."""
    print("\n" + "=" * 70)
    print("Demo 2: Retry on Transient Failures")
    print("=" * 70)

    stream_manager = create_mock_stream_manager()

    # First call fails, second succeeds (simulating transient failure)
    stream_manager._direct_call_tool.side_effect = [
        Exception("Connection reset"),  # First attempt fails
        {"result": "success after retry"},  # Retry succeeds
    ]

    config = MiddlewareConfig(
        retry=RetrySettings(
            enabled=True,
            max_retries=3,
            base_delay=0.05,  # Very short for demo
        ),
        circuit_breaker=CircuitBreakerSettings(enabled=False),
    )

    middleware = MiddlewareStack(stream_manager, config=config)

    print("\nSimulating transient failure (connection reset)...")
    print("  First attempt: will fail")
    print("  Second attempt: will succeed")

    result = await middleware.call_tool("api.call", {"data": "test"})

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts}")
    if result.success:
        print(f"  Data: {result.result}")
    else:
        print(f"  Error: {result.error}")


async def demo_non_retryable_errors():
    """Demonstrate that auth errors skip retry."""
    print("\n" + "=" * 70)
    print("Demo 3: Non-Retryable Errors (Auth Failures)")
    print("=" * 70)

    stream_manager = create_mock_stream_manager()
    stream_manager._direct_call_tool.side_effect = Exception("OAuth validation failed: invalid token")

    config = MiddlewareConfig(
        retry=RetrySettings(
            enabled=True,
            max_retries=3,
            base_delay=0.05,
        ),
        circuit_breaker=CircuitBreakerSettings(enabled=False),
    )

    middleware = MiddlewareStack(stream_manager, config=config)

    print("\nSimulating OAuth error (should NOT retry)...")

    result = await middleware.call_tool("api.protected", {"action": "read"})

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts}")  # Should be 1 (no retries for auth errors)
    print(f"  Error: {result.error}")


async def demo_circuit_breaker():
    """Demonstrate circuit breaker state transitions."""
    print("\n" + "=" * 70)
    print("Demo 4: Circuit Breaker Pattern")
    print("=" * 70)

    stream_manager = create_mock_stream_manager()

    # All calls fail
    stream_manager._direct_call_tool.side_effect = Exception("Service unavailable")

    config = MiddlewareConfig(
        retry=RetrySettings(enabled=False),  # Disable retry to see circuit breaker clearly
        circuit_breaker=CircuitBreakerSettings(
            enabled=True,
            failure_threshold=3,  # Open after 3 failures
            reset_timeout=5.0,
        ),
    )

    middleware = MiddlewareStack(stream_manager, config=config)

    print("\nSimulating multiple failures to trigger circuit breaker...")
    print(f"  Failure threshold: {config.circuit_breaker.failure_threshold}")

    for i in range(5):
        result = await middleware.call_tool("failing.service", {})
        status = middleware.get_status()

        cb_state = "unknown"
        if status.circuit_breaker and status.circuit_breaker.tool_states:
            for tool, state in status.circuit_breaker.tool_states.items():
                cb_state = state.state

        print(f"\n  Call {i + 1}: success={result.success}, circuit={cb_state}")
        if result.error:
            error_preview = result.error[:50] + "..." if len(result.error) > 50 else result.error
            print(f"          error: {error_preview}")


async def demo_middleware_status():
    """Demonstrate middleware status monitoring."""
    print("\n" + "=" * 70)
    print("Demo 5: Middleware Status Monitoring")
    print("=" * 70)

    stream_manager = create_mock_stream_manager()
    stream_manager._direct_call_tool.return_value = {"ok": True}

    config = MiddlewareConfig(
        retry=RetrySettings(enabled=True, max_retries=5),
        circuit_breaker=CircuitBreakerSettings(enabled=True, failure_threshold=10),
        rate_limiting=RateLimitSettings(enabled=True, global_limit=50, period=30.0),
    )

    middleware = MiddlewareStack(stream_manager, config=config)

    # Make a few calls to populate state
    for _ in range(3):
        await middleware.call_tool("test.tool", {})

    # Get status
    status = middleware.get_status()

    print("\nMiddleware Status:")

    if status.retry:
        print(f"\n  Retry Layer:")
        print(f"    Enabled: {status.retry.enabled}")
        print(f"    Max Retries: {status.retry.max_retries}")
        print(f"    Base Delay: {status.retry.base_delay}s")
        print(f"    Max Delay: {status.retry.max_delay}s")

    if status.circuit_breaker:
        print(f"\n  Circuit Breaker Layer:")
        print(f"    Enabled: {status.circuit_breaker.enabled}")
        print(f"    Failure Threshold: {status.circuit_breaker.failure_threshold}")
        print(f"    Reset Timeout: {status.circuit_breaker.reset_timeout}s")
        if status.circuit_breaker.tool_states:
            print(f"    Tool States:")
            for tool, state in status.circuit_breaker.tool_states.items():
                print(f"      {tool}: state={state.state}, failures={state.failure_count}")

    if status.rate_limiting:
        print(f"\n  Rate Limiting Layer:")
        print(f"    Enabled: {status.rate_limiting.enabled}")
        print(f"    Global Limit: {status.rate_limiting.global_limit}/{status.rate_limiting.period}s")


async def demo_per_tool_rate_limits():
    """Demonstrate per-tool rate limiting."""
    print("\n" + "=" * 70)
    print("Demo 6: Per-Tool Rate Limits")
    print("=" * 70)

    stream_manager = create_mock_stream_manager()
    stream_manager._direct_call_tool.return_value = {"ok": True}

    config = MiddlewareConfig(
        retry=RetrySettings(enabled=False),
        circuit_breaker=CircuitBreakerSettings(enabled=False),
        rate_limiting=RateLimitSettings(
            enabled=True,
            global_limit=100,
            period=60.0,
            per_tool_limits={
                "expensive.api": (5, 60.0),  # Only 5 requests per minute
                "cheap.api": (50, 60.0),  # 50 requests per minute
            },
        ),
    )

    middleware = MiddlewareStack(stream_manager, config=config)

    print("\nPer-Tool Rate Limits:")
    print(f"  Global: {config.rate_limiting.global_limit}/min")
    for tool, (limit, period) in config.rate_limiting.per_tool_limits.items():
        print(f"  {tool}: {limit}/{period}s")

    # Execute some calls
    print("\nExecuting calls...")
    for tool in ["expensive.api", "cheap.api", "other.api"]:
        result = await middleware.call_tool(tool, {})
        print(f"  {tool}: success={result.success}")


async def main():
    """Run all middleware demos."""
    print("""
    MCP Middleware Stack Demo
    =========================

    This demo shows how to use the MiddlewareStack for production-grade
    resilience when making MCP tool calls.

    Middleware layers (applied in order):
    1. Rate Limiting (outermost) - Controls request rate
    2. Circuit Breaker - Prevents cascading failures
    3. Retry (innermost) - Handles transient failures
    """)

    await demo_basic_middleware()
    await demo_retry_behavior()
    await demo_non_retryable_errors()
    await demo_circuit_breaker()
    await demo_middleware_status()
    await demo_per_tool_rate_limits()

    print("\n" + "=" * 70)
    print("Demo Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  - MiddlewareStack wraps StreamManager with resilience patterns")
    print("  - RetrySettings: Configure retry behavior for transient failures")
    print("  - CircuitBreakerSettings: Prevent cascading failures")
    print("  - RateLimitSettings: Control request rates globally and per-tool")
    print("  - Use get_status() to monitor middleware state in production")
    print("\nSee docs/MCP_INTEGRATION.md for more details.")


if __name__ == "__main__":
    asyncio.run(main())
