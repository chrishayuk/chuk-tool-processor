#!/usr/bin/env python
# examples/quickstart_demo.py
#!/usr/bin/env python
"""
Quick Start Demo for chuk_tool_processor

This script demonstrates the essential features of the chuk_tool_processor framework:
1. Registering simple tools with the async registry
2. Executing tools with the ToolExecutor
3. Using streaming tools for incremental results
4. Processing multiple tools concurrently

To run this script:
```
python quickstart_demo.py
```
"""

from chuk_tool_processor import (
    InProcessStrategy,
    get_default_registry,
    initialize,
    register_tool
)
import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.streaming_tool import StreamingTool
from chuk_tool_processor.models.tool_call import ToolCall

# ----------------------------------------
# Define simple tools
# ----------------------------------------


@register_tool(name="calculator", description="Perform basic arithmetic operations")
class CalculatorTool:
    """Simple calculator tool."""

    async def execute(self, operation: str, x: float, y: float) -> dict[str, Any]:
        """
        Perform a basic arithmetic operation.

        Args:
            operation: One of "add", "subtract", "multiply", "divide"
            x: First operand
            y: Second operand

        Returns:
            Dictionary with the result and operation details
        """
        if operation == "add":
            result = x + y
        elif operation == "subtract":
            result = x - y
        elif operation == "multiply":
            result = x * y
        elif operation == "divide":
            if y == 0:
                raise ValueError("Cannot divide by zero")
            result = x / y
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {"operation": operation, "x": x, "y": y, "result": result, "timestamp": datetime.now().isoformat()}


@register_tool(name="greeter", description="Generate personalized greetings")
class GreeterTool:
    """Tool to generate personalized greetings."""

    async def execute(self, name: str, formal: bool = False) -> str:
        """
        Generate a personalized greeting.

        Args:
            name: Name to greet
            formal: Whether to use formal greeting style

        Returns:
            Greeting message
        """
        # Simulate a short processing delay
        await asyncio.sleep(0.5)

        if formal:
            return f"Good day, {name}. It is a pleasure to make your acquaintance."
        else:
            return f"Hey {name}! What's up?"


@register_tool(name="counter", description="Stream a sequence of numbers")
class CounterTool(StreamingTool):
    """A streaming tool that counts numbers with a delay."""

    class Arguments(BaseModel):
        """Arguments for the counter tool."""

        start: int = Field(1, description="Starting number")
        end: int = Field(10, description="Ending number (inclusive)")
        delay: float = Field(0.5, description="Delay between numbers in seconds")

    class Result(BaseModel):
        """Result for a single count."""

        number: int = Field(..., description="Current count")
        timestamp: str = Field(..., description="Timestamp")

    async def _stream_execute(self, start: int, end: int, delay: float) -> AsyncIterator[Result]:
        """
        Count from start to end, yielding each number with a delay.

        Args:
            start: Starting number
            end: Ending number (inclusive)
            delay: Delay between numbers in seconds

        Yields:
            Each number in the sequence with timestamp
        """
        for i in range(start, end + 1):
            await asyncio.sleep(delay)
            yield self.Result(number=i, timestamp=datetime.now().isoformat())


# ----------------------------------------
# Setup helper functions
# ----------------------------------------


async def setup_executor():
    """Set up and return a properly configured executor."""
    # Get the registry
    registry = await get_default_registry()

    # Create execution strategy
    strategy = InProcessStrategy(registry)

    # Create executor with the strategy
    executor = ToolExecutor(registry=registry, strategy=strategy)

    return executor


# ----------------------------------------
# Demo functions
# ----------------------------------------


async def basic_execution():
    """Demonstrate basic tool execution."""
    print("\n=== Basic Tool Execution ===")

    # Set up executor
    executor = await setup_executor()

    # Define a tool call for the calculator
    calc_call = ToolCall(tool="calculator", arguments={"operation": "add", "x": 10, "y": 5})

    # Execute the tool
    print("Executing calculator tool...")
    start = time.time()
    results = await executor.execute([calc_call])
    duration = time.time() - start

    # Display result
    result = results[0].result
    print(f"Result: {result['x']} {result['operation']} {result['y']} = {result['result']}")
    print(f"Execution time: {duration:.3f}s")

    # Define a tool call for the greeter
    greet_call = ToolCall(tool="greeter", arguments={"name": "Developer", "formal": True})

    # Execute the tool
    print("\nExecuting greeter tool...")
    start = time.time()
    results = await executor.execute([greet_call])
    duration = time.time() - start

    # Display result
    print(f"Greeting: {results[0].result}")
    print(f"Execution time: {duration:.3f}s")


async def streaming_execution():
    """Demonstrate streaming tool execution."""
    print("\n=== Streaming Tool Execution ===")

    # Set up executor
    executor = await setup_executor()

    # Define a tool call for the counter
    counter_call = ToolCall(tool="counter", arguments={"start": 1, "end": 5, "delay": 0.3})

    # Execute with streaming
    print("Executing counter tool with streaming...")
    print("(Results will arrive incrementally)")
    start = time.time()

    async for result in executor.stream_execute([counter_call]):
        number = result.result.number
        timestamp = result.result.timestamp
        elapsed = time.time() - start
        print(f"  Received: {number} at {elapsed:.2f}s - {timestamp}")

    print(f"\nStreaming completed in {time.time() - start:.2f}s")


async def concurrent_execution():
    """Demonstrate concurrent tool execution."""
    print("\n=== Concurrent Tool Execution ===")

    # Set up executor
    executor = await setup_executor()

    # Define multiple tool calls
    tool_calls = [
        ToolCall(tool="calculator", arguments={"operation": "multiply", "x": 7, "y": 6}),
        ToolCall(tool="greeter", arguments={"name": "Team", "formal": False}),
        ToolCall(tool="calculator", arguments={"operation": "subtract", "x": 100, "y": 42}),
    ]

    # Execute concurrently
    print(f"Executing {len(tool_calls)} tools concurrently...")
    start = time.time()
    results = await executor.execute(tool_calls)
    duration = time.time() - start

    # Display results
    print("\nResults:")
    for i, result in enumerate(results):
        if i == 0 or i == 2:  # Calculator results
            res = result.result
            print(f"  Tool {i + 1}: {res['x']} {res['operation']} {res['y']} = {res['result']}")
        else:  # Greeter result
            print(f"  Tool {i + 1}: {result.result}")

    print(f"\nConcurrent execution time: {duration:.3f}s")

    # For comparison, execute them sequentially
    print("\nExecuting the same tools sequentially for comparison...")
    start = time.time()
    sequential_results = []
    for call in tool_calls:
        result = await executor.execute([call])
        sequential_results.extend(result)
    sequential_duration = time.time() - start

    print(f"Sequential execution time: {sequential_duration:.3f}s")
    print(f"Speedup from concurrency: {sequential_duration / duration:.2f}x")


async def error_handling():
    """Demonstrate error handling."""
    print("\n=== Error Handling ===")

    # Set up executor
    executor = await setup_executor()

    # Define a tool call that will fail (division by zero)
    error_call = ToolCall(tool="calculator", arguments={"operation": "divide", "x": 10, "y": 0})

    # Execute and handle error
    print("Executing calculator with invalid arguments (division by zero)...")
    try:
        results = await executor.execute([error_call])

        # The execution won't fail at the processor level; instead, the error
        # will be included in the ToolResult
        result = results[0]
        if result.error:
            print(f"Tool execution failed as expected with error: {result.error}")
            print("The error was properly captured in the ToolResult object")
        else:
            print("Tool execution unexpectedly succeeded")
    except Exception as e:
        print(f"Unexpected exception: {e}")


async def main():
    """Main function to run all demos."""
    print("=== chuk_tool_processor Quick Start Demo ===\n")

    # Initialize the registry (this will ensure all decorated tools are registered)
    print("Initializing tool registry...")
    await initialize()
    print("Registry initialized successfully!")

    # Run demonstration functions
    await basic_execution()
    await streaming_execution()
    await concurrent_execution()
    await error_handling()

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    # Run the event loop
    asyncio.run(main())
