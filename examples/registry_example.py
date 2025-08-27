#!/usr/bin/env python
# examples/registry_example.py
"""
Demonstration of the async-native registry capabilities.

This script shows:
1. Tool registration with decorators
2. Registry initialization
3. Tool discovery and lookup
4. Concurrent tool execution
5. Metadata inspection
6. Namespaced tools
"""

import asyncio
import random
import time
from datetime import datetime
from typing import Any

from chuk_tool_processor.registry import (
    initialize,
    register_tool,
)

# ----------------------------------------
# Define some example tools
# ----------------------------------------


@register_tool(name="add", namespace="math", description="Add two numbers")
class AddTool:
    """Add two numbers together."""

    async def execute(self, x: int, y: int) -> int:
        """Add x and y."""
        return x + y


@register_tool(name="multiply", namespace="math", description="Multiply two numbers")
class MultiplyTool:
    """Multiply two numbers together."""

    async def execute(self, x: int, y: int) -> int:
        """Multiply x and y."""
        return x * y


@register_tool(name="hello", namespace="text", description="Generate a greeting")
class HelloTool:
    """Generate a greeting message."""

    async def execute(self, person_name: str, formal: bool = False) -> str:
        """Generate a greeting for the given person_name."""
        if formal:
            return f"Good day, {person_name}. It is a pleasure to meet you."
        return f"Hey {person_name}! How's it going?"


@register_tool(namespace="data", tags={"async", "data", "io"})
class DataTool:
    """Fetch and process data asynchronously."""

    async def execute(self, url: str, timeout: float = 5.0) -> dict[str, Any]:
        """Simulate fetching data from a URL with a delay."""
        # Simulate network delay
        await asyncio.sleep(random.uniform(0.1, timeout / 2))

        # Simulate data processing
        return {
            "source": url,
            "timestamp": datetime.now().isoformat(),
            "data": {"values": [random.randint(1, 100) for _ in range(5)], "labels": ["A", "B", "C", "D", "E"]},
        }


@register_tool(name="stream", namespace="io", supports_streaming=True)
class StreamingTool:
    """Tool that supports streaming responses."""

    async def execute(self, count: int = 5, delay: float = 0.5) -> list[str]:
        """Generate a sequence of timestamped messages with delays."""
        results = []
        for i in range(count):
            await asyncio.sleep(delay)
            message = f"Message {i + 1} at {datetime.now().isoformat()}"
            results.append(message)

            # In a real streaming implementation, you would yield each result
            # Here we're just collecting them for demonstration

        return results


# ----------------------------------------
# Helper functions for the demo
# ----------------------------------------


async def print_tools(registry):
    """Print all available tools and their metadata."""
    print("\n=== Available Tools ===")

    tools = await registry.list_tools()
    for namespace, name in tools:
        metadata = await registry.get_metadata(name, namespace)
        description = metadata.description or "No description"
        is_async = "✓" if metadata.is_async else "✗"
        tags = ", ".join(metadata.tags) if metadata.tags else "none"

        print(f"  • {namespace}.{name}")
        print(f"    Description: {description}")
        print(f"    Async: {is_async}")
        print(f"    Tags: {tags}")

        # Check if it's a streaming tool
        if hasattr(metadata, "supports_streaming") and metadata.supports_streaming:
            print("    Supports Streaming: ✓")


async def execute_tool(registry, tool_name: str, namespace: str, **kwargs):
    """Execute a tool and print the result."""
    print(f"\n>>> Executing {namespace}.{tool_name}({', '.join(f'{k}={v}' for k, v in kwargs.items())})")

    start_time = time.time()

    # Get the tool
    tool_impl = await registry.get_tool(tool_name, namespace)
    if not tool_impl:
        print(f"Tool {namespace}.{tool_name} not found!")
        return

    # Create an instance and execute
    tool = tool_impl()
    try:
        result = await tool.execute(**kwargs)
        elapsed = time.time() - start_time
        print(f"Result: {result}")
        print(f"Time: {elapsed:.3f}s")
        return result
    except Exception as e:
        print(f"Error: {e}")


async def concurrent_execution(registry):
    """Demonstrate concurrent tool execution."""
    print("\n=== Concurrent Execution ===")
    print("Executing multiple tools concurrently...")

    start_time = time.time()

    # Define a list of tool executions
    executions = [
        execute_tool(registry, "add", "math", x=10, y=20),
        execute_tool(registry, "multiply", "math", x=5, y=7),
        execute_tool(registry, "hello", "text", person_name="World"),
        execute_tool(registry, "DataTool", "data", url="https://example.com/api/data"),
        execute_tool(registry, "stream", "io", count=3, delay=0.2),
    ]

    # Execute all concurrently
    results = await asyncio.gather(*executions)

    elapsed = time.time() - start_time
    print(f"\nAll executions completed in {elapsed:.3f}s")

    return results


async def namespace_operations(registry):
    """Demonstrate namespace operations."""
    print("\n=== Namespace Operations ===")

    # List all namespaces
    namespaces = await registry.list_namespaces()
    print(f"Available namespaces: {', '.join(namespaces)}")

    # List tools in specific namespace
    for namespace in namespaces:
        tools = await registry.list_tools(namespace=namespace)
        tool_names = [name for _, name in tools]
        print(f"Tools in '{namespace}' namespace: {', '.join(tool_names)}")


async def metadata_operations(registry):
    """Demonstrate metadata operations."""
    print("\n=== Metadata Operations ===")

    # Get all metadata
    all_metadata = await registry.list_metadata()
    print(f"Total registered tools: {len(all_metadata)}")

    # Find tools with specific tags
    async_tools = [meta for meta in all_metadata if "async" in meta.tags]
    print(f"Tools tagged with 'async': {', '.join(meta.name for meta in async_tools)}")

    # Find streaming tools
    streaming_tools = [meta for meta in all_metadata if hasattr(meta, "supports_streaming") and meta.supports_streaming]
    print(f"Tools that support streaming: {', '.join(meta.name for meta in streaming_tools)}")


# ----------------------------------------
# Main demo function
# ----------------------------------------


async def main():
    """Run the demo."""
    print("=== Async Registry Capabilities Demo ===")
    print("Initializing registry...")

    # Initialize the registry
    registry = await initialize()
    print("Registry initialized!")

    # Show available tools
    await print_tools(registry)

    # Execute individual tools
    await execute_tool(registry, "add", "math", x=5, y=3)
    await execute_tool(registry, "hello", "text", person_name="Alice", formal=True)

    # Execute tools concurrently
    await concurrent_execution(registry)

    # Demonstrate namespace operations
    await namespace_operations(registry)

    # Demonstrate metadata operations
    await metadata_operations(registry)

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
