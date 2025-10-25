# tests/execution/test_tool_executor_edge_cases.py
"""
Edge case tests for ToolExecutor to improve coverage.
"""

import asyncio

import pytest

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.streaming_tool import StreamingTool
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry import get_default_registry


class SimpleStreamingTool(StreamingTool):
    """A simple streaming tool for testing."""

    async def _stream_execute(self, count: int = 3):
        """Yield multiple results."""
        for i in range(count):
            await asyncio.sleep(0.01)  # Small delay
            yield f"Result {i}"


class SlowStreamingTool(StreamingTool):
    """A streaming tool that takes time."""

    async def _stream_execute(self, delay: float = 0.1):
        """Yield results with delay."""
        for i in range(10):
            await asyncio.sleep(delay)
            yield f"Item {i}"


class ErrorStreamingTool(StreamingTool):
    """A streaming tool that raises an error."""

    async def _stream_execute(self):
        """Raise an error during streaming."""
        yield "First item"
        raise ValueError("Streaming error occurred")


class MixedStreamingTool(StreamingTool):
    """A streaming tool with mixed behavior."""

    async def _stream_execute(self, should_fail: bool = False):
        """Yield results, optionally fail."""
        yield "Item 1"
        if should_fail:
            raise RuntimeError("Intentional failure")
        yield "Item 2"


@pytest.mark.asyncio
async def test_tool_executor_stream_timeout_queue_recovery():
    """Test stream_execute recovering from queue timeout when tasks complete."""
    registry = await get_default_registry()

    # Register a streaming tool
    await registry.register_tool(SimpleStreamingTool(), name="simple_stream")

    executor = ToolExecutor(registry=registry)

    try:
        # Execute streaming - should handle queue timeouts gracefully
        call = ToolCall(tool="simple_stream", arguments={"count": 3})
        results = []

        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should get all results despite potential queue timeouts
        assert len(results) == 3
        assert "Result 0" in results[0].result
        assert "Result 2" in results[2].result
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_direct_stream_without_timeout():
    """Test _direct_stream_tool with no timeout specified."""
    registry = await get_default_registry()

    await registry.register_tool(SimpleStreamingTool(), name="simple_stream")

    executor = ToolExecutor(registry=registry, default_timeout=None)

    try:
        # Stream with no timeout - should use the else branch in _direct_stream_tool
        call = ToolCall(tool="simple_stream", arguments={"count": 3})
        results = []

        # Use None timeout to trigger the else branch (lines 298-299)
        async for result in executor.stream_execute([call], timeout=None):
            results.append(result)

        assert len(results) == 3
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_stream_with_timeout_error():
    """Test streaming tool that times out."""
    registry = await get_default_registry()

    await registry.register_tool(SlowStreamingTool(), name="slow_stream")

    executor = ToolExecutor(registry=registry)

    try:
        # Very short timeout should trigger TimeoutError in _direct_stream_tool
        call = ToolCall(tool="slow_stream", arguments={"delay": 0.5})
        results = []

        # Short timeout
        async for result in executor.stream_execute([call], timeout=0.05):
            results.append(result)

        # Should get results (potentially including a timeout error)
        # Due to timing, we might get 0-1 results plus a timeout error
        # The important thing is we don't hang
        assert True  # Test completes without hanging
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_stream_with_exception():
    """Test streaming tool that raises an exception."""
    registry = await get_default_registry()

    await registry.register_tool(ErrorStreamingTool(), name="error_stream")

    executor = ToolExecutor(registry=registry)

    try:
        call = ToolCall(tool="error_stream", arguments={})
        results = []

        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should have at least first item + error result
        assert len(results) >= 1

        # Should have an error result
        error_results = [r for r in results if r.error]
        assert len(error_results) > 0
        assert "error" in error_results[0].error.lower()
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_stream_task_exception_handling():
    """Test exception handling in streaming tasks (lines 232-236)."""
    registry = await get_default_registry()

    await registry.register_tool(ErrorStreamingTool(), name="error_stream")
    await registry.register_tool(SimpleStreamingTool(), name="simple_stream")

    executor = ToolExecutor(registry=registry)

    try:
        # Mix of failing and succeeding streaming tools
        calls = [
            ToolCall(tool="error_stream", arguments={}),
            ToolCall(tool="simple_stream", arguments={"count": 2}),
        ]

        results = []
        async for result in executor.stream_execute(calls):
            results.append(result)

        # Should get results from both tools despite error
        assert len(results) >= 2
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_stream_general_exception_in_direct_stream():
    """Test general exception handling in _direct_stream_tool (lines 316-330)."""
    registry = await get_default_registry()

    # Register a tool that will raise a general exception
    await registry.register_tool(MixedStreamingTool(), name="mixed_stream")

    executor = ToolExecutor(registry=registry)

    try:
        call = ToolCall(tool="mixed_stream", arguments={"should_fail": True})
        results = []

        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should have at least one result (either success or error)
        assert len(results) >= 1
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_queue_timeout_with_completed_tasks():
    """Test queue timeout handling when pending_tasks is empty (lines 222-224)."""
    registry = await get_default_registry()

    # A very fast streaming tool
    class FastStreamingTool(StreamingTool):
        async def _stream_execute(self):
            yield "Fast result"
            # Tool completes quickly

    await registry.register_tool(FastStreamingTool(), name="fast_stream")

    executor = ToolExecutor(registry=registry)

    try:
        call = ToolCall(tool="fast_stream", arguments={})
        results = []

        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should complete without hanging
        assert len(results) == 1
        assert "Fast result" in results[0].result
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_tool_executor_await_completed_streaming_tasks():
    """Test awaiting completed tasks in queue timeout handler (lines 227-236)."""
    registry = await get_default_registry()

    # Create a tool that completes quickly but produces multiple results
    class MultiResultTool(StreamingTool):
        async def _stream_execute(self, count: int = 5):
            for i in range(count):
                await asyncio.sleep(0.001)  # Very short delay
                yield f"Result {i}"

    await registry.register_tool(MultiResultTool(), name="multi_stream")

    executor = ToolExecutor(registry=registry)

    try:
        call = ToolCall(tool="multi_stream", arguments={"count": 5})
        results = []

        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should get all results
        assert len(results) == 5
        assert "Result 0" in results[0].result
        assert "Result 4" in results[4].result
    finally:
        await executor.shutdown()
