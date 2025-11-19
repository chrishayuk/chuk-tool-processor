#!/usr/bin/env python3
"""
Tool Processing Performance Benchmark

Measures end-to-end performance of the tool processor with and without orjson.
Tests realistic scenarios:
- Parsing OpenAI tool calls
- Parsing JSON tool calls
- Tool execution and result serialization
- Batch processing
"""

import asyncio
import logging
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

# Suppress noisy logging BEFORE any imports
os.environ["CHUK_LOG_LEVEL"] = "ERROR"

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Now suppress all chuk_tool_processor logging
logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("chuk_tool_processor").setLevel(logging.CRITICAL)

from chuk_tool_processor.core.processor import ToolProcessor  # noqa: E402
from chuk_tool_processor.registry import ToolRegistryProvider  # noqa: E402
from chuk_tool_processor.utils import fast_json  # noqa: E402


# Sample tools for benchmarking
class Calculator:
    """Simple calculator tool."""

    async def execute(self, operation: str, a: float, b: float) -> dict[str, Any]:
        """Execute a calculation."""
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            result = a / b if b != 0 else None
        else:
            result = None

        return {"operation": operation, "a": a, "b": b, "result": result}


class SearchTool:
    """Simulated search tool with complex results."""

    async def execute(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Execute a search."""
        # Simulate complex search results
        results = [
            {
                "id": i,
                "title": f"Result {i} for query: {query}",
                "score": 1.0 - (i * 0.1),
                "metadata": {
                    "source": f"source_{i}",
                    "tags": [f"tag_{j}" for j in range(3)],
                    "nested": {"data": list(range(5))},
                },
            }
            for i in range(limit)
        ]

        return {"query": query, "total_results": limit, "results": results, "execution_time_ms": 42.5}


# Test payloads
OPENAI_SIMPLE = """
{
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": "{\\"operation\\": \\"add\\", \\"a\\": 5, \\"b\\": 3}"
            }
        }
    ]
}
"""

OPENAI_BATCH = """
{
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": "{\\"operation\\": \\"add\\", \\"a\\": 5, \\"b\\": 3}"
            }
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": "{\\"operation\\": \\"multiply\\", \\"a\\": 4, \\"b\\": 7}"
            }
        },
        {
            "id": "call_3",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": "{\\"query\\": \\"test search\\", \\"limit\\": 20}"
            }
        }
    ]
}
"""

JSON_TOOL_CALL = """
{
    "name": "search",
    "arguments": {
        "query": "complex query with nested data",
        "limit": 50
    }
}
"""


async def benchmark_simple_parsing(iterations: int = 1000) -> tuple[float, float]:
    """Benchmark simple tool call parsing."""
    print("\n" + "-" * 80)
    print("Simple Tool Call Parsing")
    print("-" * 80)

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(Calculator(), name="calculator")
    await registry.register_tool(SearchTool(), name="search")

    async with ToolProcessor() as processor:
        # Warm-up
        for _ in range(10):
            await processor.process(OPENAI_SIMPLE)

        # Benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            await processor.process(OPENAI_SIMPLE)
        elapsed = time.perf_counter() - start

    throughput = iterations / elapsed if elapsed > 0 else 0
    print(f"  Iterations:  {iterations:,}")
    print(f"  Time:        {elapsed:.4f}s")
    print(f"  Throughput:  {throughput:,.0f} ops/sec")

    return elapsed, throughput


async def benchmark_batch_processing(iterations: int = 500) -> tuple[float, float]:
    """Benchmark batch tool call processing."""
    print("\n" + "-" * 80)
    print("Batch Tool Call Processing (3 tools)")
    print("-" * 80)

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(Calculator(), name="calculator")
    await registry.register_tool(SearchTool(), name="search")

    async with ToolProcessor() as processor:
        # Warm-up
        for _ in range(5):
            await processor.process(OPENAI_BATCH)

        # Benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            await processor.process(OPENAI_BATCH)
        elapsed = time.perf_counter() - start

    total_calls = iterations * 3  # 3 tool calls per iteration
    throughput = total_calls / elapsed if elapsed > 0 else 0
    print(f"  Iterations:      {iterations:,}")
    print(f"  Total calls:     {total_calls:,}")
    print(f"  Time:            {elapsed:.4f}s")
    print(f"  Throughput:      {throughput:,.0f} calls/sec")

    return elapsed, throughput


async def benchmark_json_parsing(iterations: int = 1000) -> tuple[float, float]:
    """Benchmark JSON format tool call parsing."""
    print("\n" + "-" * 80)
    print("JSON Tool Call Parsing")
    print("-" * 80)

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(Calculator(), name="calculator")
    await registry.register_tool(SearchTool(), name="search")

    async with ToolProcessor() as processor:
        # Warm-up
        for _ in range(10):
            await processor.process(JSON_TOOL_CALL)

        # Benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            await processor.process(JSON_TOOL_CALL)
        elapsed = time.perf_counter() - start

    throughput = iterations / elapsed if elapsed > 0 else 0
    print(f"  Iterations:  {iterations:,}")
    print(f"  Time:        {elapsed:.4f}s")
    print(f"  Throughput:  {throughput:,.0f} ops/sec")

    return elapsed, throughput


async def benchmark_concurrent_processing(num_concurrent: int = 100) -> tuple[float, float]:
    """Benchmark concurrent tool processing."""
    print("\n" + "-" * 80)
    print(f"Concurrent Processing ({num_concurrent} parallel requests)")
    print("-" * 80)

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(Calculator(), name="calculator")
    await registry.register_tool(SearchTool(), name="search")

    async with ToolProcessor() as processor:
        # Create concurrent tasks
        tasks = [processor.process(OPENAI_BATCH if i % 2 == 0 else OPENAI_SIMPLE) for i in range(num_concurrent)]

        # Benchmark
        start = time.perf_counter()
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

    throughput = num_concurrent / elapsed if elapsed > 0 else 0
    print(f"  Concurrent:  {num_concurrent}")
    print(f"  Time:        {elapsed:.4f}s")
    print(f"  Throughput:  {throughput:,.0f} batches/sec")

    return elapsed, throughput


async def benchmark_memory_usage(iterations: int = 1000) -> dict[str, float]:
    """Benchmark memory usage during processing."""
    print("\n" + "-" * 80)
    print("Memory Usage Analysis")
    print("-" * 80)

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(Calculator(), name="calculator")
    await registry.register_tool(SearchTool(), name="search")

    tracemalloc.start()

    async with ToolProcessor() as processor:
        # Process multiple iterations
        for _ in range(iterations):
            await processor.process(OPENAI_BATCH)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    current_mb = current / 1024 / 1024
    peak_mb = peak / 1024 / 1024

    print(f"  Iterations:     {iterations:,}")
    print(f"  Current memory: {current_mb:.2f} MB")
    print(f"  Peak memory:    {peak_mb:.2f} MB")

    return {"current_mb": current_mb, "peak_mb": peak_mb}


async def main():
    print("\n" + "=" * 80)
    print("CHUK-TOOL-PROCESSOR PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"Using orjson: {fast_json.HAS_ORJSON}")

    # Run benchmarks
    simple_time, simple_throughput = await benchmark_simple_parsing(1000)
    batch_time, batch_throughput = await benchmark_batch_processing(500)
    json_time, json_throughput = await benchmark_json_parsing(1000)
    concurrent_time, concurrent_throughput = await benchmark_concurrent_processing(100)
    memory_stats = await benchmark_memory_usage(1000)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nJSON Implementation: {'orjson (optimized)' if fast_json.HAS_ORJSON else 'stdlib json'}")
    print("\nThroughput:")
    print(f"  Simple parsing:     {simple_throughput:,.0f} ops/sec")
    print(f"  Batch processing:   {batch_throughput:,.0f} calls/sec")
    print(f"  JSON parsing:       {json_throughput:,.0f} ops/sec")
    print(f"  Concurrent (100):   {concurrent_throughput:,.0f} batches/sec")
    print("\nMemory:")
    print(f"  Peak usage:         {memory_stats['peak_mb']:.2f} MB")
    print(f"  Current usage:      {memory_stats['current_mb']:.2f} MB")

    if not fast_json.HAS_ORJSON:
        print("\nPERFORMANCE TIP:")
        print("  Install orjson for 2-3x faster JSON operations:")
        print("    pip install 'chuk-tool-processor[fast-json]'")
        print("    or: uv add --optional fast-json orjson")
    else:
        print("\nPerformance is optimized with orjson!")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
