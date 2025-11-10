#!/usr/bin/env python
# examples/streaming_demo.py
"""
Demonstration of streaming tools with direct item-by-item streaming.

This example uses the updated StreamingTool implementation that provides
true streaming of individual results as they are produced, with proper
deduplication to prevent duplicate results.
"""

import asyncio
import random
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.streaming_tool import StreamingTool
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry import initialize, register_tool

# ----------------------------------------
# Define streaming tools
# ----------------------------------------


@register_tool(name="counter", namespace="stream")
class CounterTool(StreamingTool):
    """A simple counting tool that streams incremental counts."""

    class Arguments(BaseModel):
        """Arguments for the counter tool."""

        start: int = Field(0, description="Starting value")
        end: int = Field(10, description="Ending value (exclusive)")
        delay: float = Field(0.5, description="Delay between counts in seconds")

    class Result(BaseModel):
        """Result for a single count."""

        value: int = Field(..., description="Current count value")
        timestamp: str = Field(..., description="Timestamp of the count")

    async def _stream_execute(self, start: int, end: int, delay: float) -> AsyncIterator[Result]:
        """
        Count from start to end, yielding each value with a delay.

        Args:
            start: Starting value
            end: Ending value (exclusive)
            delay: Delay between counts in seconds

        Yields:
            Count results with timestamps
        """
        for i in range(start, end):
            # Simulate processing time
            await asyncio.sleep(delay)

            # Yield incremental result
            yield self.Result(value=i, timestamp=datetime.now().isoformat())


@register_tool(name="log_streamer", namespace="stream")
class LogStreamerTool(StreamingTool):
    """Streams simulated log entries."""

    class Arguments(BaseModel):
        """Arguments for the log streamer tool."""

        lines: int = Field(10, description="Number of log lines to generate")
        interval: float = Field(0.5, description="Interval between log lines in seconds")
        error_probability: float = Field(0.2, description="Probability of error log entries")

    class Result(BaseModel):
        """Result for a single log entry."""

        level: str = Field(..., description="Log level")
        message: str = Field(..., description="Log message")
        timestamp: str = Field(..., description="Timestamp of the log entry")

    async def _stream_execute(self, lines: int, interval: float, error_probability: float) -> AsyncIterator[Result]:
        """
        Stream simulated log entries.

        Args:
            lines: Number of log lines to generate
            interval: Interval between log lines in seconds
            error_probability: Probability of error log entries

        Yields:
            Log entry results
        """
        log_levels = ["INFO", "DEBUG", "WARNING", "ERROR"]
        services = ["api", "database", "auth", "worker"]
        messages = [
            "Request processed",
            "Connection established",
            "Cache hit",
            "Cache miss",
            "Rate limit reached",
            "Authentication successful",
            "Request validation failed",
            "Database query executed",
        ]

        for i in range(lines):
            # Simulate processing time
            await asyncio.sleep(interval)

            # Determine log level with error probability
            level = "ERROR" if random.random() < error_probability else random.choice(log_levels)

            # Generate log entry
            service = random.choice(services)
            message = f"{random.choice(messages)} in {service} (event {i + 1})"

            # Yield log entry
            yield self.Result(level=level, message=message, timestamp=datetime.now().isoformat())


@register_tool(name="search", namespace="stream")
class SearchTool(StreamingTool):
    """Simulates a streaming search API that returns results incrementally."""

    class Arguments(BaseModel):
        """Arguments for the search tool."""

        query: str = Field(..., description="Search query")
        max_results: int = Field(5, description="Maximum number of results to return")
        result_delay: float = Field(0.7, description="Delay between results in seconds")

    class Result(BaseModel):
        """Result for a single search result."""

        title: str = Field(..., description="Result title")
        snippet: str = Field(..., description="Result snippet")
        relevance: float = Field(..., description="Relevance score")
        position: int = Field(..., description="Result position")

    async def _stream_execute(self, query: str, max_results: int, result_delay: float) -> AsyncIterator[Result]:
        """
        Stream search results incrementally.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            result_delay: Delay between results in seconds

        Yields:
            Search result items
        """
        # Simulate different latencies for different results
        for i in range(max_results):
            # Calculate a delay - earlier results might come faster
            current_delay = result_delay * (1 + 0.2 * random.random())
            await asyncio.sleep(current_delay)

            # Generate a search result
            relevance = 1.0 - (i * 0.15) + (random.random() * 0.1)

            # Yield the search result
            yield self.Result(
                title=f"Result {i + 1} for '{query}'",
                snippet=f"This is a snippet of content that matches '{query}' with varying relevance...",
                relevance=round(max(0, min(1, relevance)), 2),
                position=i + 1,
            )


@register_tool(name="data_processor", namespace="stream")
class DataProcessorTool(StreamingTool):
    """Simulates processing a large dataset with streaming progress updates."""

    class Arguments(BaseModel):
        """Arguments for the data processor tool."""

        dataset_size: int = Field(100, description="Size of dataset to process")
        batch_size: int = Field(10, description="Size of batches to process")
        processing_time_per_batch: float = Field(0.5, description="Processing time per batch in seconds")

    class Result(BaseModel):
        """Result for a batch processing update."""

        items_processed: int = Field(..., description="Number of items processed so far")
        total_items: int = Field(..., description="Total items to process")
        percentage_complete: float = Field(..., description="Percentage complete")
        batch_number: int = Field(..., description="Current batch number")
        stats: dict[str, Any] = Field(default_factory=dict, description="Batch statistics")

    async def _stream_execute(
        self, dataset_size: int, batch_size: int, processing_time_per_batch: float
    ) -> AsyncIterator[Result]:
        """
        Process data in batches and stream progress updates.

        Args:
            dataset_size: Size of dataset to process
            batch_size: Size of batches to process
            processing_time_per_batch: Processing time per batch in seconds

        Yields:
            Batch processing results
        """
        # Calculate number of batches
        num_batches = (dataset_size + batch_size - 1) // batch_size
        items_processed = 0

        for batch_number in range(1, num_batches + 1):
            # Simulate batch processing
            await asyncio.sleep(processing_time_per_batch)

            # Calculate items processed in this batch
            batch_items = min(batch_size, dataset_size - items_processed)
            items_processed += batch_items

            # Calculate percentage complete
            percentage_complete = round(items_processed / dataset_size * 100, 1)

            # Generate random stats for this batch
            stats = {
                "avg_processing_time": round(processing_time_per_batch * (0.8 + 0.4 * random.random()), 3),
                "errors": random.randint(0, max(1, batch_items // 20)),
                "memory_usage_mb": round(10 + 5 * random.random(), 1),
            }

            # Yield progress update
            yield self.Result(
                items_processed=items_processed,
                total_items=dataset_size,
                percentage_complete=percentage_complete,
                batch_number=batch_number,
                stats=stats,
            )


# ----------------------------------------
# Helper functions for the demo
# ----------------------------------------


async def demonstrate_counter_tool(executor: ToolExecutor) -> None:
    """Demonstrate the counter tool with true streaming."""
    print("\n=== Counter Tool Demo ===")

    # Create a tool call
    call = ToolCall(tool="counter", namespace="stream", arguments={"start": 0, "end": 5, "delay": 0.3})

    # Execute in streaming mode
    print("\nStreaming execution (values arrive incrementally):")
    start_time = time.time()

    async for result in executor.stream_execute([call]):
        elapsed = time.time() - start_time
        value = result.result.value
        timestamp = result.result.timestamp
        print(f"  Received count {value} at {elapsed:.2f}s - {timestamp}")

    print(f"\nTotal streaming time: {time.time() - start_time:.2f}s")

    # Execute in non-streaming mode for comparison
    print("\nNon-streaming execution (all values arrive at once):")
    start_time = time.time()

    results = await executor.execute([call])
    elapsed = time.time() - start_time

    print(f"  Received {len(results[0].result)} values at once after {elapsed:.2f}s")
    for _i, item in enumerate(results[0].result):
        print(f"    Count {item.value} - {item.timestamp}")


async def demonstrate_log_streamer_tool(executor: ToolExecutor) -> None:
    """Demonstrate the log streamer tool with true streaming."""
    print("\n=== Log Streamer Tool Demo ===")

    # Create a tool call
    call = ToolCall(
        tool="log_streamer", namespace="stream", arguments={"lines": 8, "interval": 0.4, "error_probability": 0.25}
    )

    # Execute in streaming mode
    print("\nStreaming execution (log entries arrive incrementally):")
    start_time = time.time()

    # Track ERROR logs for demonstration
    error_count = 0

    async for result in executor.stream_execute([call]):
        elapsed = time.time() - start_time
        level = result.result.level
        message = result.result.message

        # Highlight ERROR logs
        if level == "ERROR":
            error_count += 1
            print(f"  {elapsed:.2f}s - [!] {level}: {message}")
            # Demonstrate real-time processing
            print(f"    ** Alert! Error detected in logs (error #{error_count}) **")
        else:
            print(f"  {elapsed:.2f}s - {level}: {message}")

    print(f"\nTotal streaming time: {time.time() - start_time:.2f}s")
    print(f"Detected {error_count} errors in real-time")


async def demonstrate_search_tool(executor: ToolExecutor) -> None:
    """Demonstrate the search tool with true streaming."""
    print("\n=== Search Tool Demo ===")

    # Create a tool call
    call = ToolCall(
        tool="search",
        namespace="stream",
        arguments={"query": "async python tools", "max_results": 5, "result_delay": 0.5},
    )

    # Execute in streaming mode
    print("\nStreaming search results (arrive incrementally):")
    start_time = time.time()

    # Track highest relevance result
    best_result = None
    best_relevance = -1

    async for result in executor.stream_execute([call]):
        elapsed = time.time() - start_time
        title = result.result.title
        relevance = result.result.relevance
        position = result.result.position

        print(f"  {elapsed:.2f}s - Result #{position}: {title} (relevance: {relevance:.2f})")

        # Track highest relevance result in real-time
        if relevance > best_relevance:
            best_relevance = relevance
            best_result = title
            print(f"    ** New best result found! Relevance: {relevance:.2f} **")

    print(f"\nTotal streaming time: {time.time() - start_time:.2f}s")
    print(f"Best result: {best_result} (relevance: {best_relevance:.2f})")


async def demonstrate_data_processor_tool(executor: ToolExecutor) -> None:
    """Demonstrate the data processor tool with true streaming."""
    print("\n=== Data Processor Tool Demo ===")

    # Create a tool call
    call = ToolCall(
        tool="data_processor",
        namespace="stream",
        arguments={"dataset_size": 100, "batch_size": 20, "processing_time_per_batch": 0.6},
    )

    # Execute in streaming mode
    print("\nProcessing large dataset with streaming updates:")
    start_time = time.time()

    # Track statistics for demonstration
    total_errors = 0

    print("\nProgress:")
    async for result in executor.stream_execute([call]):
        elapsed = time.time() - start_time
        items = result.result.items_processed
        total = result.result.total_items
        percentage = result.result.percentage_complete
        batch = result.result.batch_number
        errors = result.result.stats.get("errors", 0)

        # Update total errors
        total_errors += errors

        # Print progress bar
        bar_length = 30
        filled_length = int(bar_length * items / total)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)

        print(f"  [{bar}] {percentage}% - Batch {batch} ({items}/{total} items) - {elapsed:.2f}s")
        if errors > 0:
            print(f"    Warning: {errors} errors in batch {batch}")

    total_time = time.time() - start_time
    print(f"\nProcessing completed in {total_time:.2f}s")
    print(f"Total errors detected: {total_errors}")


async def demonstrate_parallel_streaming(executor: ToolExecutor) -> None:
    """Demonstrate parallel streaming of multiple tools."""
    print("\n=== Parallel Streaming Demo ===")

    # Create multiple tool calls
    calls = [
        ToolCall(tool="counter", namespace="stream", arguments={"start": 0, "end": 5, "delay": 0.5}),
        ToolCall(
            tool="log_streamer", namespace="stream", arguments={"lines": 5, "interval": 0.6, "error_probability": 0.2}
        ),
        ToolCall(
            tool="search",
            namespace="stream",
            arguments={"query": "parallel processing", "max_results": 3, "result_delay": 0.7},
        ),
    ]

    print("\nExecuting multiple streaming tools in parallel:")
    print("(Results will arrive as they become available from any tool)\n")
    start_time = time.time()

    # Create counters to track results from each tool
    counter_results = 0
    log_results = 0
    search_results = 0

    async for result in executor.stream_execute(calls):
        elapsed = time.time() - start_time
        tool_name = result.tool

        if tool_name == "counter":
            counter_results += 1
            value = result.result.value
            print(f"  {elapsed:.2f}s - Counter: value={value}")
        elif tool_name == "log_streamer":
            log_results += 1
            level = result.result.level
            message = result.result.message
            print(f"  {elapsed:.2f}s - Log: {level} - {message}")
        elif tool_name == "search":
            search_results += 1
            title = result.result.title
            relevance = result.result.relevance
            print(f"  {elapsed:.2f}s - Search: {title} (relevance: {relevance:.2f})")

    total_time = time.time() - start_time
    print(f"\nAll results received in {total_time:.2f}s")
    print(f"Counter results: {counter_results}")
    print(f"Log results: {log_results}")
    print(f"Search results: {search_results}")

    # Calculate theoretical sequential time
    sequential_time = (5 * 0.5) + (5 * 0.6) + (3 * 0.7)
    print(f"\nSequential execution would take approximately {sequential_time:.2f}s")
    print(
        f"Parallel streaming saved approximately {sequential_time - total_time:.2f}s ({(sequential_time - total_time) / sequential_time * 100:.1f}%)"
    )


# ----------------------------------------
# Custom ToolExecutor with deduplication
# ----------------------------------------


async def get_custom_executor(registry):
    """Create an executor with the fixed deduplication strategy."""
    # Create strategy
    strategy = InProcessStrategy(registry)

    # Create ToolExecutor with this strategy
    executor = ToolExecutor(registry=registry, strategy=strategy)

    # Use the InProcessStrategy's mark_direct_streaming method
    # to set up deduplication when it becomes available
    if hasattr(strategy, "mark_direct_streaming"):
        # Modern version with deduplication
        return executor
    else:
        # Fallback for older versions without deduplication
        return executor


# ----------------------------------------
# Main demo function
# ----------------------------------------


async def main():
    """Run the streaming tools demo with true item-by-item streaming."""
    print("=== True Streaming Tools Demo ===")
    print("This demo shows streaming tools with direct item-by-item streaming")

    # Initialize registry
    registry = await initialize()
    print("Registry initialized!")

    # Create executor with the deduplication-capable strategy
    executor = await get_custom_executor(registry)

    # Run demos
    await demonstrate_counter_tool(executor)
    await demonstrate_log_streamer_tool(executor)
    await demonstrate_search_tool(executor)
    await demonstrate_data_processor_tool(executor)
    await demonstrate_parallel_streaming(executor)

    # Graceful shutdown
    await executor.shutdown()

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
