#!/usr/bin/env python3
"""
Execution Strategy Performance Benchmark

Compares InProcessStrategy vs SubprocessStrategy performance:
- Latency per call
- Throughput
- Memory usage
- Concurrent execution
- Overhead analysis
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
logging.getLogger("chuk_tool_processor.execution").setLevel(logging.CRITICAL)
logging.getLogger("chuk_tool_processor.execution.subprocess_strategy").setLevel(logging.CRITICAL)

from chuk_tool_processor.core.processor import ToolProcessor  # noqa: E402
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy  # noqa: E402
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy  # noqa: E402
from chuk_tool_processor.registry import ToolRegistryProvider  # noqa: E402
from chuk_tool_processor.utils import fast_json  # noqa: E402


# Sample tools for benchmarking
class FastTool:
    """Very fast tool - minimal computation."""

    async def execute(self, value: int) -> dict[str, Any]:
        """Execute a fast operation."""
        return {"result": value * 2}


class SlowTool:
    """Slow tool - simulates I/O or computation."""

    async def execute(self, duration_ms: int = 100) -> dict[str, Any]:
        """Execute a slow operation."""
        await asyncio.sleep(duration_ms / 1000.0)
        return {"result": "completed", "duration_ms": duration_ms}


class CPUBoundTool:
    """CPU-intensive tool - simulates heavy computation."""

    async def execute(self, iterations: int = 10000) -> dict[str, Any]:
        """Execute CPU-intensive operation."""
        result = 0
        for i in range(iterations):
            result += i * i
        return {"result": result}


# Test payload
OPENAI_FAST = """
{
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "fast_tool",
                "arguments": "{\\"value\\": 42}"
            }
        }
    ]
}
"""

OPENAI_SLOW = """
{
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "slow_tool",
                "arguments": "{\\"duration_ms\\": 10}"
            }
        }
    ]
}
"""

OPENAI_CPU = """
{
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "cpu_bound_tool",
                "arguments": "{\\"iterations\\": 5000}"
            }
        }
    ]
}
"""


async def benchmark_strategy(
    strategy_name: str, strategy_class: type, payload: str, iterations: int = 100
) -> tuple[float, float, dict]:
    """
    Benchmark a specific strategy.

    Returns:
        (elapsed_time, throughput, metrics)
    """
    print(f"\n  Testing {strategy_name}...")

    # Register tools
    registry = await ToolRegistryProvider.get_registry()
    await registry.register_tool(FastTool(), name="fast_tool")
    await registry.register_tool(SlowTool(), name="slow_tool")
    await registry.register_tool(CPUBoundTool(), name="cpu_bound_tool")

    # Create processor with specific strategy
    strategy = strategy_class(registry=registry)
    processor = ToolProcessor(registry=registry, strategy=strategy, enable_retries=False, enable_caching=False)

    tracemalloc.start()
    start_mem = tracemalloc.get_traced_memory()[0]

    # Warm-up
    async with processor:
        for _ in range(5):
            await processor.process(payload)

        # Benchmark
        start = time.perf_counter()
        for _ in range(iterations):
            await processor.process(payload)
        elapsed = time.perf_counter() - start

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    throughput = iterations / elapsed if elapsed > 0 else 0
    avg_latency_ms = (elapsed / iterations) * 1000 if iterations > 0 else 0

    metrics = {
        "elapsed": elapsed,
        "throughput": throughput,
        "avg_latency_ms": avg_latency_ms,
        "memory_delta_mb": (current_mem - start_mem) / 1024 / 1024,
        "memory_peak_mb": peak_mem / 1024 / 1024,
    }

    print(f"    Throughput:   {throughput:,.0f} ops/sec")
    print(f"    Avg latency:  {avg_latency_ms:.2f}ms")
    print(f"    Memory delta: {metrics['memory_delta_mb']:.2f} MB")

    return elapsed, throughput, metrics


async def benchmark_fast_calls():
    """Benchmark fast, lightweight tool calls."""
    print("\n" + "=" * 80)
    print("FAST TOOL CALLS (minimal computation)")
    print("=" * 80)

    inprocess_time, inprocess_throughput, inprocess_metrics = await benchmark_strategy(
        "InProcess", InProcessStrategy, OPENAI_FAST, iterations=1000
    )

    subprocess_time, subprocess_throughput, subprocess_metrics = await benchmark_strategy(
        "Subprocess",
        SubprocessStrategy,
        OPENAI_FAST,
        iterations=100,  # Fewer iterations due to overhead
    )

    speedup = subprocess_time / inprocess_time if inprocess_time > 0 else 0

    print("\n  📊 Comparison:")
    print(f"    InProcess:   {inprocess_throughput:,.0f} ops/sec")
    print(f"    Subprocess:  {subprocess_throughput:,.0f} ops/sec")
    print(f"    Winner:      InProcess is {speedup:.1f}x faster")

    return {
        "inprocess": inprocess_metrics,
        "subprocess": subprocess_metrics,
        "speedup": speedup,
    }


async def benchmark_slow_calls():
    """Benchmark I/O-bound tool calls."""
    print("\n" + "=" * 80)
    print("SLOW TOOL CALLS (I/O-bound, 10ms sleep)")
    print("=" * 80)

    inprocess_time, inprocess_throughput, inprocess_metrics = await benchmark_strategy(
        "InProcess", InProcessStrategy, OPENAI_SLOW, iterations=100
    )

    subprocess_time, subprocess_throughput, subprocess_metrics = await benchmark_strategy(
        "Subprocess", SubprocessStrategy, OPENAI_SLOW, iterations=50
    )

    speedup = subprocess_time / inprocess_time if inprocess_time > 0 else 0

    print("\n  📊 Comparison:")
    print(f"    InProcess:   {inprocess_throughput:,.0f} ops/sec")
    print(f"    Subprocess:  {subprocess_throughput:,.0f} ops/sec")
    print(f"    Winner:      InProcess is {speedup:.1f}x faster")

    return {
        "inprocess": inprocess_metrics,
        "subprocess": subprocess_metrics,
        "speedup": speedup,
    }


async def benchmark_cpu_bound():
    """Benchmark CPU-intensive tool calls."""
    print("\n" + "=" * 80)
    print("CPU-BOUND TOOL CALLS (heavy computation)")
    print("=" * 80)

    inprocess_time, inprocess_throughput, inprocess_metrics = await benchmark_strategy(
        "InProcess", InProcessStrategy, OPENAI_CPU, iterations=50
    )

    subprocess_time, subprocess_throughput, subprocess_metrics = await benchmark_strategy(
        "Subprocess", SubprocessStrategy, OPENAI_CPU, iterations=50
    )

    speedup = inprocess_time / subprocess_time if subprocess_time > 0 else 0

    print("\n  📊 Comparison:")
    print(f"    InProcess:   {inprocess_throughput:,.0f} ops/sec")
    print(f"    Subprocess:  {subprocess_throughput:,.0f} ops/sec")
    if speedup >= 1:
        print(f"    Winner:      Subprocess is {speedup:.1f}x faster")
    else:
        print(f"    Winner:      InProcess is {1 / speedup:.1f}x faster")

    return {
        "inprocess": inprocess_metrics,
        "subprocess": subprocess_metrics,
        "speedup": speedup,
    }


async def main():
    print("\n" + "=" * 80)
    print("EXECUTION STRATEGY PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"Using orjson: {fast_json.HAS_ORJSON}")

    # Run benchmarks
    fast_results = await benchmark_fast_calls()
    slow_results = await benchmark_slow_calls()
    cpu_results = await benchmark_cpu_bound()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    print("\n📊 Performance Comparison:")
    print("\n  Fast Calls (lightweight):")
    print(f"    InProcess:   {fast_results['inprocess']['throughput']:,.0f} ops/sec")
    print(f"    Subprocess:  {fast_results['subprocess']['throughput']:,.0f} ops/sec")
    print(f"    Winner:      InProcess ({fast_results['speedup']:.1f}x faster)")

    print("\n  Slow Calls (I/O-bound):")
    print(f"    InProcess:   {slow_results['inprocess']['throughput']:,.0f} ops/sec")
    print(f"    Subprocess:  {slow_results['subprocess']['throughput']:,.0f} ops/sec")
    print(f"    Winner:      InProcess ({slow_results['speedup']:.1f}x faster)")

    print("\n  CPU-Bound Calls:")
    print(f"    InProcess:   {cpu_results['inprocess']['throughput']:,.0f} ops/sec")
    print(f"    Subprocess:  {cpu_results['subprocess']['throughput']:,.0f} ops/sec")
    if cpu_results["speedup"] >= 1:
        print(f"    Winner:      Subprocess ({cpu_results['speedup']:.1f}x faster)")
    else:
        print(f"    Winner:      InProcess ({1 / cpu_results['speedup']:.1f}x faster)")

    print("\n✅ Recommendations:")
    print("\n  Use InProcessStrategy when:")
    print("    • Tools are fast (< 100ms)")
    print("    • Tools are I/O-bound (async/await works)")
    print("    • Maximum throughput needed")
    print("    • Low latency required")

    print("\n  Use SubprocessStrategy when:")
    print("    • Tools are CPU-intensive")
    print("    • Tools may block event loop")
    print("    • Isolation is critical")
    print("    • Can tolerate higher latency")

    print("\n  Default: InProcessStrategy (best for most cases)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
