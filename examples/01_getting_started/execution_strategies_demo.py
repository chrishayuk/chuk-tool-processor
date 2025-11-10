#!/usr/bin/env python
# examples/execution_strategies_demo.py
"""
Demonstration of execution strategies in chuk_tool_processor.

This script shows:
1. Setting up and using InProcessStrategy
2. Setting up and using SubprocessStrategy
3. Comparing performance and isolation characteristics
4. Handling tool execution errors and timeouts
"""

from chuk_tool_processor import (
    InProcessStrategy,
    IsolatedStrategy,
    initialize,
    register_tool
)
import asyncio
import os
import time
from datetime import datetime
from typing import Any

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# ----------------------------------------
# Define some example tools
# ----------------------------------------


@register_tool(name="calculator", namespace="demo")
class CalculatorTool:
    """Perform basic arithmetic operations."""

    async def execute(self, operation: str, a: float, b: float) -> dict[str, Any]:
        """
        Perform an arithmetic operation on two numbers.

        Args:
            operation: One of "add", "subtract", "multiply", "divide"
            a: First number
            b: Second number

        Returns:
            Dictionary with the operation and result
        """
        result = None
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Cannot divide by zero")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {"operation": operation, "a": a, "b": b, "result": result}


@register_tool(name="cpu_intensive", namespace="demo")
class CPUIntensiveTool:
    """Perform a CPU-intensive calculation."""

    async def execute(self, iterations: int = 1000000) -> dict[str, Any]:
        """
        Perform a CPU-intensive calculation.

        Args:
            iterations: Number of iterations for the calculation

        Returns:
            Dictionary with result and stats
        """
        # This is deliberately CPU-intensive
        start = time.time()

        # Simulate CPU-bound work by calculating Fibonacci numbers
        result = 0
        a, b = 0, 1
        for _ in range(iterations):
            a, b = b, a + b
            result = b

        end = time.time()

        return {"result": result, "iterations": iterations, "duration": end - start, "process_id": os.getpid()}


@register_tool(name="memory_intensive", namespace="demo")
class MemoryIntensiveTool:
    """Perform a memory-intensive operation."""

    async def execute(self, size_mb: int = 100, hold_seconds: float = 1.0) -> dict[str, Any]:
        """
        Allocate a large amount of memory.

        Args:
            size_mb: Size in MB to allocate
            hold_seconds: Time to hold the memory

        Returns:
            Dictionary with stats
        """
        # Allocate memory
        start = time.time()
        chunk_size = 1024 * 1024  # 1 MB
        data = bytearray(size_mb * chunk_size)

        # Fill with random data to ensure it's actually allocated
        for i in range(0, len(data), chunk_size):
            end = min(i + chunk_size, len(data))
            data[i:end] = os.urandom(end - i)

        # Hold for requested time
        await asyncio.sleep(hold_seconds)

        # Release memory
        data = None
        end = time.time()

        return {"size_mb": size_mb, "hold_seconds": hold_seconds, "duration": end - start, "process_id": os.getpid()}


@register_tool(name="slow_tool", namespace="demo")
class SlowTool:
    """A tool that takes a long time to execute."""

    async def execute(self, delay: float = 2.0, fail: bool = False) -> dict[str, Any]:
        """
        Sleep for a specified time.

        Args:
            delay: Time to sleep in seconds
            fail: Whether to fail after sleeping

        Returns:
            Dictionary with stats
        """
        start = time.time()

        # Sleep for requested time
        await asyncio.sleep(delay)

        # Optionally fail
        if fail:
            raise ValueError("Tool execution failed as requested")

        end = time.time()

        return {
            "delay": delay,
            "actual_duration": end - start,
            "process_id": os.getpid(),
            "timestamp": datetime.now().isoformat(),
        }


# ----------------------------------------
# Helper functions for the demo
# ----------------------------------------


async def run_with_strategy(strategy_name: str, registry, tools_to_run: list[dict]) -> list[ToolResult]:
    """Run tools with the specified strategy."""
    print(f"\n=== Running with {strategy_name} ===")

    # Create appropriate strategy
    if strategy_name == "inprocess":
        strategy = InProcessStrategy(registry, default_timeout=10.0, max_concurrency=4)
    elif strategy_name == "subprocess":
        strategy = SubprocessStrategy(registry, max_workers=4, default_timeout=10.0)
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    # Create executor
    executor = ToolExecutor(registry=registry, strategy=strategy)

    # Convert to tool calls
    calls = []
    for tool_info in tools_to_run:
        call = ToolCall(
            tool=tool_info["name"],
            namespace=tool_info.get("namespace", "demo"),
            arguments=tool_info.get("arguments", {}),
        )
        calls.append(call)

    # Measure execution time
    start = time.time()
    results = await executor.execute(calls)
    duration = time.time() - start

    # Display results
    print(f"Executed {len(calls)} tools in {duration:.3f} seconds")
    for i, (call, result) in enumerate(zip(calls, results, strict=False)):
        if result.error:
            print(f"  {i + 1}. {call.tool} - ERROR: {result.error}")
        else:
            if isinstance(result.result, dict) and "process_id" in result.result:
                print(f"  {i + 1}. {call.tool} - Success (PID: {result.result['process_id']})")
            else:
                print(f"  {i + 1}. {call.tool} - Success")

    # Graceful shutdown
    await executor.strategy.shutdown()

    return results


async def compare_strategies_isolation(registry) -> None:
    """Compare isolation characteristics of different strategies."""
    print("\n=== Strategy Isolation Comparison ===")

    # Define a set of tools to run
    tools = [
        {"name": "cpu_intensive", "arguments": {"iterations": 500000}},  # Reduced iterations
        {"name": "memory_intensive", "arguments": {"size_mb": 20, "hold_seconds": 0.5}},  # Reduced memory and time
        {"name": "slow_tool", "arguments": {"delay": 0.7}},  # Reduced delay
    ]

    # Run with each strategy
    print("\nRunning CPU, memory, and I/O intensive tools to compare isolation:")
    inprocess_results = await run_with_strategy("inprocess", registry, tools)

    # Check if subprocess strategy is available
    try:
        subprocess_results = await run_with_strategy("subprocess", registry, tools)

        # Compare PIDs
        inprocess_pids = set()
        subprocess_pids = set()

        for result in inprocess_results:
            if isinstance(result.result, dict) and "process_id" in result.result:
                inprocess_pids.add(result.result["process_id"])

        for result in subprocess_results:
            if isinstance(result.result, dict) and "process_id" in result.result:
                subprocess_pids.add(result.result["process_id"])

        print("\nProcess Isolation:")
        print(f"  InProcess PIDs: {inprocess_pids}")
        print(f"  Subprocess PIDs: {subprocess_pids}")
        print(f"  Main process PID: {os.getpid()}")

        if len(subprocess_pids) > 1:
            print("  ✓ Subprocess strategy provides true process isolation")
        else:
            print("  ✗ Subprocess strategy did not demonstrate multiple processes")

    except Exception as e:
        print(f"\nSubprocess strategy not available: {e}")
        print("Skipping subprocess comparison")


async def timeout_test(registry) -> None:
    """Test timeout behavior of different strategies."""
    print("\n=== Timeout Handling Test ===")

    # Define a tool that will exceed our timeout
    tools = [
        {"name": "slow_tool", "arguments": {"delay": 3.0}},
    ]

    # Strategy itself has a 1-second default timeout
    strategy = InProcessStrategy(registry, default_timeout=1.0)

    # Give the executor a strategy and call-level timeout of 1 s
    executor = ToolExecutor(registry=registry, strategy=strategy)

    # Build ToolCall list
    calls = [
        ToolCall(
            tool=tool["name"],
            namespace="demo",
            arguments=tool["arguments"],
        )
        for tool in tools
    ]

    print("\nTest with 1 second timeout for a tool that takes 3 seconds:")
    # ⬇️ forward the timeout explicitly
    results = await executor.execute(calls, timeout=1.0)

    # Check the outcome
    for _call, result in zip(calls, results, strict=False):
        if result.error and "timeout" in result.error.lower():
            print(f"  ✓ Timeout detected properly: {result.error}")
        else:
            print(f"  ✗ Expected timeout, got: {result.error if result.error else 'success'}")

    # Clean up
    await executor.strategy.shutdown()


async def error_handling_test(registry) -> None:
    """Test error handling in different strategies."""
    print("\n=== Error Handling Test ===")

    # Define tools that will fail
    tools = [
        {"name": "calculator", "arguments": {"operation": "divide", "a": 10, "b": 0}},
        {"name": "slow_tool", "arguments": {"delay": 0.5, "fail": True}},
    ]

    # Test with InProcess strategy
    await run_with_strategy("inprocess", registry, tools)


async def streaming_test(registry) -> None:
    """Test streaming execution."""
    print("\n=== Streaming Execution Test ===")

    # Define tools to run
    tools = [
        {"name": "slow_tool", "arguments": {"delay": 0.5}},
        {"name": "slow_tool", "arguments": {"delay": 1.0}},
        {"name": "slow_tool", "arguments": {"delay": 1.5}},
    ]

    # Create calls
    calls = []
    for tool_info in tools:
        call = ToolCall(
            tool=tool_info["name"],
            namespace=tool_info.get("namespace", "demo"),
            arguments=tool_info.get("arguments", {}),
        )
        calls.append(call)

    # Create strategy and executor
    strategy = InProcessStrategy(registry)
    executor = ToolExecutor(registry=registry, strategy=strategy)

    print("\nStreaming execution (results will arrive as they complete):")
    start = time.time()

    # Use streaming execution
    results_seen = 0
    async for result in executor.stream_execute(calls):
        delay = result.result.get("delay", "unknown") if result.result else "unknown"
        duration = time.time() - start
        results_seen += 1
        print(f"  Received result {results_seen}/{len(calls)} at {duration:.3f}s (tool delay: {delay}s)")

    total_duration = time.time() - start
    print(f"\nAll results received in {total_duration:.3f}s")

    # Demonstrate parallel execution advantage
    sequential_time = sum(tool["arguments"]["delay"] for tool in tools)
    print(f"Sequential execution would take approximately {sequential_time:.3f}s")
    print(
        f"Parallel streaming saved approximately {sequential_time - total_duration:.3f}s ({(sequential_time - total_duration) / sequential_time * 100:.1f}%)"
    )

    # Clean up
    await executor.strategy.shutdown()


# ----------------------------------------
# Main demo function
# ----------------------------------------


async def main():
    """Run the execution strategies demo."""
    print("=== Execution Strategies Demo ===")

    # Initialize registry
    registry = await initialize()
    print("Registry initialized!")

    # Run basic tests with each strategy
    tools_to_run = [
        {"name": "calculator", "arguments": {"operation": "add", "a": 10, "b": 5}},
        {"name": "slow_tool", "arguments": {"delay": 0.5}},
    ]
    await run_with_strategy("inprocess", registry, tools_to_run)

    # Try subprocess strategy if available
    try:
        await run_with_strategy("subprocess", registry, tools_to_run)
    except Exception as e:
        print(f"\nSubprocess strategy not available: {e}")
        print("Skipping subprocess tests")

    # Run additional tests
    await compare_strategies_isolation(registry)
    await timeout_test(registry)
    await error_handling_test(registry)
    await streaming_test(registry)

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
