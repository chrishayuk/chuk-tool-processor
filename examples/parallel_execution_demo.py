#!/usr/bin/env python3
"""
Parallel Execution Demo - Tool-Processor Concurrent Tool Execution

Demonstrates the tool-processor's parallel execution capabilities:
- Multiple tools executing concurrently
- Results returning in COMPLETION ORDER (faster tools return first)
- The on_tool_start callback for tracking when tools begin
- Streaming results as they complete

Usage:
    python examples/parallel_execution_demo.py
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Use local source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall


# =============================================================================
# Sample Tools with different execution times
# =============================================================================

class FastTool:
    """A tool that completes quickly."""

    async def execute(self, message: str = "fast") -> dict:
        await asyncio.sleep(0.05)  # 50ms
        return {"tool": "fast", "message": message, "duration_ms": 50}


class MediumTool:
    """A tool that takes a medium amount of time."""

    async def execute(self, message: str = "medium") -> dict:
        await asyncio.sleep(0.2)  # 200ms
        return {"tool": "medium", "message": message, "duration_ms": 200}


class SlowTool:
    """A tool that takes longer to complete."""

    async def execute(self, message: str = "slow") -> dict:
        await asyncio.sleep(0.5)  # 500ms
        return {"tool": "slow", "message": message, "duration_ms": 500}


class ComputeTool:
    """A tool that simulates computation."""

    async def execute(self, iterations: int = 100000) -> dict:
        start = time.time()
        total = 0
        for i in range(iterations):
            total += i
            if i % 10000 == 0:
                await asyncio.sleep(0)  # Yield to event loop
        duration = time.time() - start
        return {"tool": "compute", "result": total, "duration_s": round(duration, 3)}


# =============================================================================
# Mock Registry for the demo
# =============================================================================

class DemoRegistry:
    """Simple registry for demo tools."""

    def __init__(self):
        self._tools = {
            "fast": FastTool,
            "medium": MediumTool,
            "slow": SlowTool,
            "compute": ComputeTool,
        }

    async def get_tool(self, name: str, namespace: str = "default"):
        return self._tools.get(name)

    async def get_metadata(self, name: str, namespace: str = "default"):
        if name in self._tools:
            return {"description": f"Demo {name} tool"}
        return None

    async def list_tools(self, namespace: str | None = None):
        return [("default", name) for name in self._tools]

    async def list_namespaces(self):
        return ["default"]


# =============================================================================
# Demo Functions
# =============================================================================

async def demo_parallel_execution():
    """Demonstrate parallel execution with completion order results."""
    print("=" * 80)
    print("DEMO 1: Parallel Execution - Completion Order Results")
    print("=" * 80)
    print()
    print("Running 3 tools with different execution times:")
    print("  - fast:   50ms")
    print("  - medium: 200ms")
    print("  - slow:   500ms")
    print()
    print("With parallel execution, results return as each tool completes,")
    print("NOT in the order they were submitted.")
    print()

    registry = DemoRegistry()
    strategy = InProcessStrategy(registry, default_timeout=5.0)

    calls = [
        ToolCall(tool="slow", arguments={"message": "I was submitted first but finish last"}),
        ToolCall(tool="medium", arguments={"message": "I was submitted second"}),
        ToolCall(tool="fast", arguments={"message": "I was submitted last but finish first"}),
    ]

    print("Submitting tools in order: slow, medium, fast")
    print("-" * 60)

    start_time = time.time()
    results = await strategy.run(calls)
    total_duration = time.time() - start_time

    print(f"\nResults returned in COMPLETION ORDER:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result.tool}: {result.result['message']}")

    print(f"\nTotal execution time: {total_duration*1000:.0f}ms")
    print(f"  (Sequential would be ~750ms, parallel is ~500ms)")
    print()


async def demo_streaming_results():
    """Demonstrate streaming results as they complete."""
    print("=" * 80)
    print("DEMO 2: Streaming Results - Process as They Arrive")
    print("=" * 80)
    print()
    print("Using stream_run() to yield results as each tool completes.")
    print("This allows processing results immediately without waiting for all tools.")
    print()

    registry = DemoRegistry()
    strategy = InProcessStrategy(registry, default_timeout=5.0)

    calls = [
        ToolCall(tool="slow", arguments={"message": "slow result"}),
        ToolCall(tool="medium", arguments={"message": "medium result"}),
        ToolCall(tool="fast", arguments={"message": "fast result"}),
    ]

    print("Streaming results as they complete:")
    print("-" * 60)

    start_time = time.time()
    result_count = 0

    async for result in strategy.stream_run(calls):
        result_count += 1
        elapsed = (time.time() - start_time) * 1000
        print(f"  [{elapsed:6.0f}ms] Received result #{result_count}: {result.tool} -> {result.result}")

    print()


async def demo_on_tool_start_callback():
    """Demonstrate the on_tool_start callback."""
    print("=" * 80)
    print("DEMO 3: on_tool_start Callback - Track Tool Execution Start")
    print("=" * 80)
    print()
    print("The on_tool_start callback is invoked when each tool begins execution.")
    print("Useful for logging, UI updates, or emitting start events.")
    print()

    registry = DemoRegistry()
    strategy = InProcessStrategy(registry, default_timeout=5.0)

    calls = [
        ToolCall(tool="slow", arguments={}),
        ToolCall(tool="medium", arguments={}),
        ToolCall(tool="fast", arguments={}),
    ]

    start_time = time.time()
    started_tools = []

    async def on_start(call: ToolCall):
        """Callback invoked when a tool starts."""
        elapsed = (time.time() - start_time) * 1000
        started_tools.append((elapsed, call.tool))
        print(f"  [{elapsed:6.0f}ms] STARTED: {call.tool}")

    print("Tracking tool execution starts and completions:")
    print("-" * 60)

    async for result in strategy.stream_run(calls, on_tool_start=on_start):
        elapsed = (time.time() - start_time) * 1000
        status = "SUCCESS" if result.error is None else f"ERROR: {result.error}"
        print(f"  [{elapsed:6.0f}ms] COMPLETED: {result.tool} -> {status}")

    print()
    print(f"Note: All tools started nearly simultaneously due to parallel execution.")
    print()


async def demo_parallel_vs_sequential():
    """Compare parallel vs sequential execution times."""
    print("=" * 80)
    print("DEMO 4: Parallel vs Sequential - Performance Comparison")
    print("=" * 80)
    print()

    registry = DemoRegistry()
    parallel_strategy = InProcessStrategy(registry, default_timeout=5.0)
    sequential_strategy = InProcessStrategy(registry, default_timeout=5.0, max_concurrency=1)

    calls = [
        ToolCall(tool="medium", arguments={"message": "tool1"}),
        ToolCall(tool="medium", arguments={"message": "tool2"}),
        ToolCall(tool="medium", arguments={"message": "tool3"}),
    ]

    # Parallel execution
    print("Running 3 x 200ms tools in PARALLEL:")
    start = time.time()
    await parallel_strategy.run(calls)
    parallel_time = time.time() - start
    print(f"  Time: {parallel_time*1000:.0f}ms (expected ~200ms)")

    print()

    # Sequential execution (using max_concurrency=1)
    print("Running 3 x 200ms tools SEQUENTIALLY (max_concurrency=1):")
    start = time.time()
    await sequential_strategy.run(calls)
    sequential_time = time.time() - start
    print(f"  Time: {sequential_time*1000:.0f}ms (expected ~600ms)")

    print()
    speedup = sequential_time / parallel_time
    print(f"Parallel speedup: {speedup:.1f}x faster")
    print()


async def demo_matching_results_to_calls():
    """Show how to match results back to original calls."""
    print("=" * 80)
    print("DEMO 5: Matching Results to Calls")
    print("=" * 80)
    print()
    print("Since results return in completion order, use the 'tool' attribute")
    print("to match results back to their original calls.")
    print()

    registry = DemoRegistry()
    strategy = InProcessStrategy(registry, default_timeout=5.0)

    # Create calls with unique arguments to track them
    calls = [
        ToolCall(tool="medium", arguments={"message": "call_A"}),
        ToolCall(tool="fast", arguments={"message": "call_B"}),
        ToolCall(tool="slow", arguments={"message": "call_C"}),
    ]

    results = await strategy.run(calls)

    print("Original call order vs result order:")
    print("-" * 60)
    print("Original calls:")
    for i, call in enumerate(calls, 1):
        print(f"  {i}. tool={call.tool}, message={call.arguments['message']}")

    print()
    print("Results (completion order):")
    for i, result in enumerate(results, 1):
        print(f"  {i}. tool={result.tool}, message={result.result['message']}")

    print()
    print("To match results to calls, create a lookup by tool name or call ID:")
    print()

    # Create lookup by message (unique identifier)
    results_by_message = {r.result['message']: r for r in results}

    print("Matched results:")
    for call in calls:
        result = results_by_message[call.arguments['message']]
        print(f"  {call.arguments['message']}: tool={result.tool}, duration={result.result['duration_ms']}ms")

    print()


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Run all demos."""
    print()
    print("CHUK TOOL PROCESSOR - PARALLEL EXECUTION DEMO")
    print("=" * 80)
    print()
    print("This demo showcases the parallel execution features:")
    print("  1. Multiple tools execute concurrently")
    print("  2. Results return in COMPLETION ORDER (not submission order)")
    print("  3. The on_tool_start callback tracks execution start")
    print("  4. Streaming yields results as each tool finishes")
    print()

    await demo_parallel_execution()
    await demo_streaming_results()
    await demo_on_tool_start_callback()
    await demo_parallel_vs_sequential()
    await demo_matching_results_to_calls()

    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()
    print("Key takeaways:")
    print("  - Tools execute in parallel by default")
    print("  - Results come back in completion order, not submission order")
    print("  - Use ToolResult.tool to match results to original calls")
    print("  - Use on_tool_start callback for tracking/logging tool starts")
    print("  - Use stream_run() to process results as they arrive")
    print()


if __name__ == "__main__":
    asyncio.run(main())
