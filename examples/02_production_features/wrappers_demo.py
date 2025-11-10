#!/usr/bin/env python
# examples/wrappers_demo.py
"""
Demonstration of execution wrappers in chuk_tool_processor.

This script shows:
1. Retry wrapper for handling transient failures
2. Rate limiting wrapper for controlling execution frequency
3. Caching wrapper for performance optimization
4. Combining multiple wrappers
"""

from chuk_tool_processor import InProcessStrategy, initialize, register_tool
import asyncio
import random
import time
from datetime import UTC, datetime
from typing import Any

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.wrappers.caching import CachingToolExecutor, InMemoryCache, cacheable
from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimitedToolExecutor, RateLimiter, rate_limited
from chuk_tool_processor.execution.wrappers.retry import RetryableToolExecutor, RetryConfig, retryable
from chuk_tool_processor.models.tool_call import ToolCall

# ----------------------------------------
# Define example tools with wrapper decorators
# ----------------------------------------


@retryable(max_retries=3, base_delay=0.5)
@register_tool(name="flaky_api", namespace="demo")
class FlakyApiTool:
    """Simulates an unreliable API that occasionally fails."""

    def __init__(self):
        self.call_count = 0

    async def execute(self, fail_rate: float = 0.5, data: str = "test") -> dict[str, Any]:
        """
        Call an unreliable API that occasionally fails.

        Args:
            fail_rate: Probability of failure (0.0 to 1.0)
            data: Data to process

        Returns:
            API response data
        """
        self.call_count += 1

        # Simulate API latency
        await asyncio.sleep(0.2)

        # Simulate occasional failures
        if random.random() < fail_rate:
            raise ConnectionError(f"API request failed (attempt {self.call_count})")

        return {
            "status": "success",
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
            "attempts": self.call_count,
        }


@rate_limited(limit=2, period=5.0)  # 2 requests per 5 seconds
@register_tool(name="rate_limited_api", namespace="demo")
class RateLimitedApiTool:
    """Simulates an API with rate limits."""

    async def execute(self, query: str = "example") -> dict[str, Any]:
        """
        Call a rate-limited API.

        Args:
            query: Search query

        Returns:
            API response data
        """
        # Simulate API call
        await asyncio.sleep(0.3)

        return {
            "query": query,
            "results": [f"Result {i} for '{query}'" for i in range(1, 4)],
            "timestamp": datetime.now(UTC).isoformat(),
        }


@cacheable(ttl=30)  # Cache results for 30 seconds
@register_tool(name="expensive_computation", namespace="demo")
class ExpensiveComputationTool:
    """Performs an expensive computation that benefits from caching."""

    async def execute(self, input_value: int = 42) -> dict[str, Any]:
        """
        Perform an expensive computation.

        Args:
            input_value: Input for computation

        Returns:
            Computation results
        """
        # Simulate expensive computation
        print(f"  Computing result for input_value={input_value}...")
        await asyncio.sleep(2.0)  # This would be a CPU-intensive task

        result = sum(i * input_value for i in range(1000))

        return {"input": input_value, "result": result, "computed_at": datetime.now(UTC).isoformat()}


# ----------------------------------------
# Demo functions for each wrapper
# ----------------------------------------


async def retry_wrapper_demo(registry) -> None:
    """Demonstrate the retry wrapper."""
    print("\n=== Retry Wrapper Demo ===")

    # Create base strategy and executor
    strategy = InProcessStrategy(registry)
    base_executor = ToolExecutor(registry=registry, strategy=strategy)

    # Wrap with RetryableToolExecutor
    executor = RetryableToolExecutor(
        executor=base_executor,
        default_config=RetryConfig(
            max_retries=3,
            base_delay=0.5,
            max_delay=5.0,
            jitter=True,
            retry_on_exceptions=[ConnectionError, TimeoutError],
            retry_on_error_substrings=["API request failed"],
        ),
    )

    # Create high failure rate call
    high_fail_call = ToolCall(
        tool="flaky_api", namespace="demo", arguments={"fail_rate": 0.8, "data": "high failure test"}
    )

    # Create low failure rate call
    low_fail_call = ToolCall(
        tool="flaky_api", namespace="demo", arguments={"fail_rate": 0.3, "data": "low failure test"}
    )

    # Run with high failure rate
    print("\nTesting with high failure rate (80%):")
    start = time.time()
    high_results = await executor.execute([high_fail_call])
    high_duration = time.time() - start

    for i, result in enumerate(high_results):
        print(f"  Result {i + 1}:")
        if result.error:
            print(f"    Error: {result.error}")
            print(f"    Attempts: {getattr(result, 'attempts', 'unknown')}")
        else:
            print(f"    Success after {result.result.get('attempts', '?')} attempts")
        print(f"    Time taken: {high_duration:.2f}s")

    # Run with low failure rate
    print("\nTesting with low failure rate (30%):")
    start = time.time()
    low_results = await executor.execute([low_fail_call])
    low_duration = time.time() - start

    for i, result in enumerate(low_results):
        print(f"  Result {i + 1}:")
        if result.error:
            print(f"    Error: {result.error}")
            print(f"    Attempts: {getattr(result, 'attempts', 'unknown')}")
        else:
            print(f"    Success after {result.result.get('attempts', '?')} attempts")
        print(f"    Time taken: {low_duration:.2f}s")

    # Show how retry wrapper can be used with tool classes directly
    print("\nRetry wrapper can also be applied as a decorator:")
    print("  @retryable(max_retries=3, base_delay=0.5)")
    print("  @register_tool(name='flaky_api', namespace='demo')")
    print("  class FlakyApiTool:")
    print("      ...")


async def rate_limiting_wrapper_demo(registry) -> None:
    """Demonstrate the rate limiting wrapper."""
    print("\n=== Rate Limiting Wrapper Demo ===")

    # Create base strategy and executor
    strategy = InProcessStrategy(registry)
    base_executor = ToolExecutor(registry=registry, strategy=strategy)

    # Create rate limiter with 2 requests per 5 seconds
    rate_limiter = RateLimiter(
        global_limit=2,  # 2 requests...
        global_period=5.0,  # ...per 5 seconds
        tool_limits={
            "rate_limited_api": (1, 3.0)  # 1 request per 3 seconds for this specific tool
        },
    )

    # Wrap with RateLimitedToolExecutor
    executor = RateLimitedToolExecutor(executor=base_executor, limiter=rate_limiter)

    # Create several tool calls
    calls = [
        ToolCall(tool="rate_limited_api", namespace="demo", arguments={"query": f"query {i}"})
        for i in range(5)  # 5 calls that should be rate-limited
    ]

    # Execute and measure timing
    print("\nExecuting 5 rate-limited API calls (limit: 2 per 5 seconds globally, 1 per 3 seconds per tool):")
    start = time.time()

    # Execute first two calls - these should go through immediately
    print("\nFirst two calls should execute immediately:")
    await executor.execute(calls[:2])
    first_duration = time.time() - start
    print(f"  First two calls completed in {first_duration:.2f}s")

    # Execute remaining calls - these should be rate-limited
    print("\nRemaining calls should be rate-limited:")
    next_start = time.time()
    await executor.execute(calls[2:])
    remaining_duration = time.time() - next_start
    total_duration = time.time() - start

    print(f"  Remaining calls completed in {remaining_duration:.2f}s")
    print(f"  Total execution time: {total_duration:.2f}s")
    print("  Expected minimum time with rate limiting: ~9s")

    print("\nRate limiting wrapper can also be applied as a decorator:")
    print("  @rate_limited(limit=2, period=5.0)")
    print("  @register_tool(name='rate_limited_api', namespace='demo')")
    print("  class RateLimitedApiTool:")
    print("      ...")


async def caching_wrapper_demo(registry) -> None:
    """Demonstrate the caching wrapper."""
    print("\n=== Caching Wrapper Demo ===")

    # Create base strategy and executor
    strategy = InProcessStrategy(registry)
    base_executor = ToolExecutor(registry=registry, strategy=strategy)

    # Create cache
    cache = InMemoryCache(default_ttl=30)  # 30 second TTL by default

    # Wrap with CachingToolExecutor
    executor = CachingToolExecutor(
        executor=base_executor,
        cache=cache,
        default_ttl=30,
        tool_ttls={
            "expensive_computation": 60  # 60 second TTL for this specific tool
        },
    )

    # Create tool calls with same and different parameters
    same_param_calls = [
        ToolCall(tool="expensive_computation", namespace="demo", arguments={"input_value": 42}),
        ToolCall(
            tool="expensive_computation",
            namespace="demo",
            arguments={"input_value": 42},  # Same parameters should hit cache
        ),
    ]

    different_param_call = ToolCall(
        tool="expensive_computation",
        namespace="demo",
        arguments={"input_value": 100},  # Different parameters should miss cache
    )

    # First execution - should compute and cache
    print("\nFirst execution (should compute and cache):")
    start = time.time()
    first_results = await executor.execute(same_param_calls[:1])
    first_duration = time.time() - start

    for result in first_results:
        is_cached = getattr(result, "cached", False)
        print(f"  Cached: {is_cached}")
        print(f"  Computation time: {first_duration:.2f}s")
        print(f"  Computed at: {result.result.get('computed_at', 'unknown')}")

    # Second execution with same parameters - should hit cache
    print("\nSecond execution with same parameters (should hit cache):")
    start = time.time()
    second_results = await executor.execute(same_param_calls[1:])
    second_duration = time.time() - start

    for result in second_results:
        is_cached = getattr(result, "cached", False)
        print(f"  Cached: {is_cached}")
        print(f"  Retrieval time: {second_duration:.2f}s")
        print(f"  Computed at: {result.result.get('computed_at', 'unknown')}")
        print(f"  Cache speedup: {first_duration / second_duration:.1f}x faster")

    # Third execution with different parameters - should miss cache
    print("\nExecution with different parameters (should miss cache):")
    start = time.time()
    third_results = await executor.execute([different_param_call])
    third_duration = time.time() - start

    for result in third_results:
        is_cached = getattr(result, "cached", False)
        print(f"  Cached: {is_cached}")
        print(f"  Computation time: {third_duration:.2f}s")
        print(f"  Computed at: {result.result.get('computed_at', 'unknown')}")

    # Show cache statistics
    cache_stats = await cache.get_stats()
    print("\nCache statistics:")
    print(f"  Hits: {cache_stats.get('hits', 0)}")
    print(f"  Misses: {cache_stats.get('misses', 0)}")
    print(f"  Hit rate: {cache_stats.get('hit_rate', 0):.1%}")
    print(f"  Entry count: {cache_stats.get('entry_count', 0)}")

    print("\nCaching wrapper can also be applied as a decorator:")
    print("  @cacheable(ttl=30)")
    print("  @register_tool(name='expensive_computation', namespace='demo')")
    print("  class ExpensiveComputationTool:")
    print("      ...")


async def combined_wrappers_demo(registry) -> None:
    """Demonstrate combining multiple wrappers."""
    print("\n=== Combined Wrappers Demo ===")

    # Create base strategy and executor
    strategy = InProcessStrategy(registry)
    base_executor = ToolExecutor(registry=registry, strategy=strategy)

    # Stack wrappers (innermost first)
    # 1. First, retry failed executions
    retry_executor = RetryableToolExecutor(
        executor=base_executor, default_config=RetryConfig(max_retries=2, base_delay=0.5)
    )

    # 2. Then, cache successful results (including retried successes)
    cache = InMemoryCache(default_ttl=30)
    cache_executor = CachingToolExecutor(executor=retry_executor, cache=cache)

    # 3. Finally, apply rate limiting (operates on cache hits too)
    rate_limiter = RateLimiter(global_limit=5, global_period=10.0)
    combined_executor = RateLimitedToolExecutor(executor=cache_executor, limiter=rate_limiter)

    print("\nWrappers are stacked in the following order:")
    print("  1. RetryableToolExecutor (innermost)")
    print("  2. CachingToolExecutor (middle)")
    print("  3. RateLimitedToolExecutor (outermost)")

    # Create a flaky API call
    flaky_call = ToolCall(tool="flaky_api", namespace="demo", arguments={"fail_rate": 0.7, "data": "test combined"})

    # Execute twice to demonstrate all wrappers in action
    print("\nFirst execution (may retry, then cache):")
    start = time.time()
    first_results = await combined_executor.execute([flaky_call])
    first_duration = time.time() - start

    for result in first_results:
        print(f"  Result: {'Success' if result.error is None else 'Error: ' + result.error}")
        if not result.error:
            print(f"  Attempts: {result.result.get('attempts', '?')}")
        print(f"  Cached: {getattr(result, 'cached', False)}")
        print(f"  Duration: {first_duration:.2f}s")

    # Second execution should hit cache if first was successful
    print("\nSecond execution (should hit cache if first was successful):")
    start = time.time()
    second_results = await combined_executor.execute([flaky_call])
    second_duration = time.time() - start

    for result in second_results:
        print(f"  Result: {'Success' if result.error is None else 'Error: ' + result.error}")
        if not result.error:
            print(f"  Attempts: {result.result.get('attempts', '?')}")
        print(f"  Cached: {getattr(result, 'cached', False)}")
        print(f"  Duration: {second_duration:.2f}s")
        if not result.error and getattr(result, "cached", False):
            print(f"  Cache speedup: {first_duration / second_duration:.1f}x faster")

    print("\nThis demonstrates how wrappers can be combined to provide:")
    print("  - Reliability (retry logic)")
    print("  - Performance (caching)")
    print("  - Resource management (rate limiting)")
    print("  All in a single unified executor")


# ----------------------------------------
# Main demo function
# ----------------------------------------


async def main():
    """Run the wrappers demo."""
    print("=== Execution Wrappers Demo ===")

    # Initialize registry
    registry = await initialize()
    print("Registry initialized!")

    # Run demos for each wrapper
    await retry_wrapper_demo(registry)
    await rate_limiting_wrapper_demo(registry)
    await caching_wrapper_demo(registry)
    await combined_wrappers_demo(registry)

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
