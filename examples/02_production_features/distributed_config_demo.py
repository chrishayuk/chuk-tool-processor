#!/usr/bin/env python3
"""
Distributed Configuration Demo

This example demonstrates how to configure chuk-tool-processor for distributed
deployments using Redis-backed registry, rate limiting, and circuit breakers.

Configuration can be done via:
1. Environment variables (recommended for production)
2. Programmatic configuration (for testing or dynamic config)

Environment Variables:
    CHUK_REGISTRY_BACKEND=redis
    CHUK_RESILIENCE_BACKEND=redis
    CHUK_REDIS_URL=redis://localhost:6379/0
    CHUK_CIRCUIT_BREAKER_ENABLED=true
    CHUK_RATE_LIMIT_ENABLED=true
    CHUK_RATE_LIMIT_GLOBAL=100

Run with:
    # Using environment variables
    CHUK_REGISTRY_BACKEND=memory CHUK_RESILIENCE_BACKEND=memory python distributed_config_demo.py

    # With Redis (requires running Redis server)
    CHUK_REGISTRY_BACKEND=redis CHUK_RESILIENCE_BACKEND=redis \
    CHUK_REDIS_URL=redis://localhost:6379/0 \
    CHUK_CIRCUIT_BREAKER_ENABLED=true \
    CHUK_RATE_LIMIT_ENABLED=true \
    python distributed_config_demo.py
"""

import asyncio
import os

from chuk_tool_processor import (
    BackendType,
    ProcessorConfig,
    RegistryConfig,
    ToolProcessor,
    register_tool,
)
from chuk_tool_processor.config import (
    CacheConfig,
    CircuitBreakerConfig,
    RateLimitConfig,
    RetryConfig,
)


# =============================================================================
# Sample Tools
# =============================================================================
class Calculator:
    """Simple calculator tool."""

    async def execute(self, operation: str, a: float, b: float) -> dict:
        ops = {
            "add": a + b,
            "subtract": a - b,
            "multiply": a * b,
            "divide": a / b if b != 0 else float("inf"),
        }
        return {"operation": operation, "a": a, "b": b, "result": ops.get(operation, 0)}


class WeatherAPI:
    """Simulated weather API with rate limiting."""

    async def execute(self, city: str) -> dict:
        # Simulate API call
        await asyncio.sleep(0.1)
        return {"city": city, "temperature": 72, "conditions": "sunny"}


class FlakyAPI:
    """API that sometimes fails (for circuit breaker demo)."""

    _call_count = 0

    async def execute(self, action: str) -> dict:
        FlakyAPI._call_count += 1
        # Fail every 3rd call
        if FlakyAPI._call_count % 3 == 0:
            raise RuntimeError("Simulated API failure")
        return {"action": action, "status": "success", "call": FlakyAPI._call_count}


async def register_tools(registry):
    """Register all tools with the given registry."""
    await registry.register_tool(Calculator, name="math.calculator")
    await registry.register_tool(WeatherAPI, name="api.weather")
    await registry.register_tool(FlakyAPI, name="api.flaky")


# =============================================================================
# Demo Functions
# =============================================================================
async def demo_environment_config():
    """Demo: Load configuration from environment variables."""
    print("\n" + "=" * 60)
    print("Demo 1: Environment Variable Configuration")
    print("=" * 60)

    # Load from environment
    config = ProcessorConfig.from_env()

    print(f"\nLoaded configuration:")
    print(f"  Registry backend: {config.registry.backend.value}")
    print(f"  Resilience backend: {config.resilience_backend.value}")
    print(f"  Redis URL: {config.redis_url}")
    print(f"  Circuit breaker enabled: {config.circuit_breaker.enabled}")
    print(f"  Rate limit enabled: {config.rate_limit.enabled}")
    print(f"  Rate limit global: {config.rate_limit.global_limit}")

    # Create processor from config
    processor = await config.create_processor()

    async with processor:
        # Register tools with the processor's registry
        await register_tools(processor.registry)

        # Execute some tool calls
        print("\nExecuting tool calls...")
        results = await processor.process(
            [
                {"tool": "math.calculator", "arguments": {"operation": "multiply", "a": 7, "b": 8}},
                {"tool": "api.weather", "arguments": {"city": "San Francisco"}},
            ]
        )

        for r in results:
            print(f"  {r.tool}: {r.result}")


async def demo_programmatic_config():
    """Demo: Programmatic configuration for Redis deployment."""
    print("\n" + "=" * 60)
    print("Demo 2: Programmatic Configuration")
    print("=" * 60)

    # Check if Redis is available
    redis_available = False
    try:
        import redis

        redis_available = True
    except ImportError:
        pass

    # Choose backend based on availability
    backend = BackendType.MEMORY
    if redis_available and os.environ.get("CHUK_REDIS_URL"):
        backend = BackendType.REDIS
        print("\nUsing Redis backend")
    else:
        print("\nUsing in-memory backend (Redis not available or not configured)")

    config = ProcessorConfig(
        # Backend configuration
        registry=RegistryConfig(
            backend=backend,
            redis_url=os.environ.get("CHUK_REDIS_URL", "redis://localhost:6379/0"),
            key_prefix="demo",
        ),
        resilience_backend=backend,
        redis_url=os.environ.get("CHUK_REDIS_URL", "redis://localhost:6379/0"),
        redis_key_prefix="demo",
        # Execution settings
        default_timeout=30.0,
        max_concurrency=10,
        # Circuit breaker - opens after 3 failures
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=5.0,  # Short for demo
            failure_window=60.0,
        ),
        # Rate limiting - 10 requests per minute globally
        rate_limit=RateLimitConfig(
            enabled=True,
            global_limit=10,
            global_period=60.0,
            tool_limits={
                "api.weather": (5, 60.0),  # 5 requests per minute
            },
        ),
        # Caching
        cache=CacheConfig(enabled=True, ttl=300),
        # Retries
        retry=RetryConfig(enabled=True, max_retries=2),
    )

    print(f"\nConfiguration:")
    print(f"  Backend: {config.resilience_backend.value}")
    print(f"  Circuit breaker: {config.circuit_breaker.enabled}")
    print(f"  Rate limit: {config.rate_limit.global_limit} req/min")

    # Create processor
    processor = await config.create_processor()

    async with processor:
        # Register tools
        await register_tools(processor.registry)

        print("\nExecuting tool calls...")
        results = await processor.process(
            [
                {"tool": "math.calculator", "arguments": {"operation": "add", "a": 100, "b": 200}},
                {"tool": "api.weather", "arguments": {"city": "New York"}},
            ]
        )

        for r in results:
            if r.error:
                print(f"  {r.tool}: ERROR - {r.error}")
            else:
                print(f"  {r.tool}: {r.result}")


async def demo_rate_limiting():
    """Demo: Rate limiting in action."""
    print("\n" + "=" * 60)
    print("Demo 3: Rate Limiting")
    print("=" * 60)

    config = ProcessorConfig(
        resilience_backend=BackendType.MEMORY,
        rate_limit=RateLimitConfig(
            enabled=True,
            global_limit=3,  # Only 3 requests per minute
            global_period=60.0,
        ),
        cache=CacheConfig(enabled=False),  # Disable cache to see rate limiting
    )

    processor = await config.create_processor()

    async with processor:
        await processor.registry.register_tool(Calculator, name="math.calculator")

        print("\nMaking 5 rapid requests (limit is 3/min)...")
        print("First 3 should succeed, rest should be rate-limited.")

        for i in range(5):
            try:
                results = await processor.process(
                    {"tool": "math.calculator", "arguments": {"operation": "add", "a": i, "b": 1}}
                )
                r = results[0]
                if r.error:
                    print(f"  Request {i + 1}: Rate limited - {r.error[:50]}...")
                else:
                    print(f"  Request {i + 1}: Success - {r.result}")
            except Exception as e:
                print(f"  Request {i + 1}: Error - {e}")


async def demo_circuit_breaker():
    """Demo: Circuit breaker in action."""
    print("\n" + "=" * 60)
    print("Demo 4: Circuit Breaker")
    print("=" * 60)

    config = ProcessorConfig(
        resilience_backend=BackendType.MEMORY,
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=2,  # Open after 2 failures
            reset_timeout=2.0,  # Try again after 2 seconds
        ),
        retry=RetryConfig(enabled=False),  # Disable retries for demo
        cache=CacheConfig(enabled=False),
    )

    processor = await config.create_processor()

    async with processor:
        await processor.registry.register_tool(FlakyAPI, name="api.flaky")

        print("\nMaking requests to flaky API (fails every 3rd call)...")
        print("Circuit should open after 2 failures.")

        for i in range(6):
            results = await processor.process({"tool": "api.flaky", "arguments": {"action": f"request_{i + 1}"}})
            r = results[0]
            if r.error:
                if "circuit" in r.error.lower():
                    print(f"  Request {i + 1}: CIRCUIT OPEN - {r.error[:40]}...")
                else:
                    print(f"  Request {i + 1}: FAILED - {r.error[:40]}...")
            else:
                print(f"  Request {i + 1}: SUCCESS - {r.result}")

            await asyncio.sleep(0.5)


async def demo_multi_tenant():
    """Demo: Multi-tenant isolation with key prefixes."""
    print("\n" + "=" * 60)
    print("Demo 5: Multi-Tenant Isolation")
    print("=" * 60)

    print("\nCreating separate configurations for two tenants...")

    # Tenant A config
    config_a = ProcessorConfig(
        registry=RegistryConfig(backend=BackendType.MEMORY),
        redis_key_prefix="tenant_a",
        rate_limit=RateLimitConfig(enabled=True, global_limit=10),
    )

    # Tenant B config (different limits)
    config_b = ProcessorConfig(
        registry=RegistryConfig(backend=BackendType.MEMORY),
        redis_key_prefix="tenant_b",
        rate_limit=RateLimitConfig(enabled=True, global_limit=100),  # Higher limit
    )

    processor_a = await config_a.create_processor()
    processor_b = await config_b.create_processor()

    async with processor_a, processor_b:
        # Register tools for each tenant
        await processor_a.registry.register_tool(Calculator, name="math.calculator")
        await processor_b.registry.register_tool(Calculator, name="math.calculator")

        print("\nTenant A (10 req/min limit):")
        results_a = await processor_a.process(
            {"tool": "math.calculator", "arguments": {"operation": "add", "a": 1, "b": 1}}
        )
        print(f"  Result: {results_a[0].result}")

        print("\nTenant B (100 req/min limit):")
        results_b = await processor_b.process(
            {"tool": "math.calculator", "arguments": {"operation": "multiply", "a": 5, "b": 5}}
        )
        print(f"  Result: {results_b[0].result}")

        print("\nEach tenant has isolated:")
        print("  - Tool registry")
        print("  - Rate limit counters")
        print("  - Circuit breaker states")


# =============================================================================
# Main
# =============================================================================
async def main():
    """Run all demos."""
    print("=" * 60)
    print("CHUK Tool Processor - Distributed Configuration Demo")
    print("=" * 60)

    # Show current environment config
    print("\nCurrent environment:")
    print(f"  CHUK_REGISTRY_BACKEND: {os.environ.get('CHUK_REGISTRY_BACKEND', 'memory (default)')}")
    print(f"  CHUK_RESILIENCE_BACKEND: {os.environ.get('CHUK_RESILIENCE_BACKEND', 'memory (default)')}")
    print(f"  CHUK_REDIS_URL: {os.environ.get('CHUK_REDIS_URL', 'not set')}")

    await demo_environment_config()
    await demo_programmatic_config()
    await demo_rate_limiting()
    await demo_circuit_breaker()
    await demo_multi_tenant()

    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
