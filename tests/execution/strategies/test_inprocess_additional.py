#!/usr/bin/env python
"""
Additional tests to improve coverage for InProcessStrategy.

Target uncovered lines:
- Lines 94, 98, 116, 164: Initialization and lock handling
- Lines 184-185, 211, 215-226: Stream execution paths
- Lines 233-244, 258, 264-290: Direct streaming functionality
- Lines 311-383: stream_with_timeout method
- Lines 393-397: Error handling in execute_to_queue
- Lines 426, 461-485: Timeout and error paths
- Lines 573-574, 621-633, 645-649: Tool resolution
- Lines 657-683, 694, 704-731: Shutdown and cleanup
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, Mock

import pytest

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall


# Test Tools
class StreamingTool:
    """Tool that supports streaming."""

    def __init__(self):
        self.supports_streaming = True

    async def stream_execute(self, **kwargs):
        """Yield results one at a time."""
        for i in range(3):
            await asyncio.sleep(0.01)
            yield f"item_{i}"

    async def execute(self, **kwargs):
        """Regular execute method."""
        return "non-streaming-result"


class StreamingErrorTool:
    """Streaming tool that raises an error."""

    def __init__(self):
        self.supports_streaming = True

    async def stream_execute(self, **kwargs):
        yield "first"
        raise RuntimeError("Stream failed")


class SlowStreamingTool:
    """Streaming tool that's slow."""

    def __init__(self):
        self.supports_streaming = True

    async def stream_execute(self, **kwargs):
        for i in range(10):
            await asyncio.sleep(0.5)
            yield f"slow_{i}"


class NamespacedRegistry:
    """Registry with namespace support."""

    def __init__(self):
        self.tools = {
            "default": {"tool1": StreamingTool},
            "custom": {"tool2": StreamingTool},
            "other": {"tool1": SlowStreamingTool},  # Same name, different namespace
        }

    async def get_tool(self, name: str, namespace: str = "default"):
        return self.tools.get(namespace, {}).get(name)

    async def list_namespaces(self):
        return list(self.tools.keys())

    async def list_tools(self):
        result = []
        for ns, tools in self.tools.items():
            for name in tools:
                result.append((ns, name))
        return result


# ============================================================================
# Tests for initialization (lines 94, 98, 116)
# ============================================================================


@pytest.mark.asyncio
async def test_execute_multiple_calls():
    """Test that execute handles multiple concurrent calls properly."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Execute multiple calls
    calls = [ToolCall(tool="tool1", arguments={}), ToolCall(tool="tool1", arguments={})]

    results = await strategy.run(calls)

    # Should have results for both
    assert len(results) == 2
    assert all(r.error is None for r in results)


# ============================================================================
# Tests for streaming (lines 184-185, 211, 215-226, 233-244, 258, 264-290)
# ============================================================================


@pytest.mark.asyncio
async def test_mark_and_clear_direct_streaming():
    """Test marking and clearing direct streaming calls."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    # Mark some calls
    strategy.mark_direct_streaming({"call1", "call2"})
    assert "call1" in strategy._direct_streaming_calls
    assert "call2" in strategy._direct_streaming_calls

    # Clear them
    strategy.clear_direct_streaming()
    assert len(strategy._direct_streaming_calls) == 0


@pytest.mark.asyncio
async def test_stream_run_with_direct_streaming_marked():
    """Test stream_run skips calls marked for direct streaming."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Mark a call as being handled directly
    call1 = ToolCall(tool="tool1", arguments={}, id="marked")
    call2 = ToolCall(tool="tool1", arguments={}, id="not_marked")

    strategy.mark_direct_streaming({"marked"})

    # Stream run should skip the marked call
    results = []
    async for result in strategy.stream_run([call1, call2]):
        results.append(result)

    # Should have results only for unmarked call (which streams 3 items)
    assert len(results) == 3  # StreamingTool yields 3 items
    assert all(r.tool == "tool1" for r in results)


@pytest.mark.asyncio
async def test_stream_tool_call_when_shutting_down():
    """Test stream_tool_call returns early when shutting down."""
    registry = Mock()
    strategy = InProcessStrategy(registry)
    strategy._shutting_down = True

    queue = asyncio.Queue()
    call = ToolCall(tool="test", arguments={})

    await strategy._stream_tool_call(call, queue, timeout=1.0)

    result = await queue.get()
    assert result.error == "System is shutting down"


@pytest.mark.asyncio
async def test_stream_tool_call_with_streaming_tool():
    """Test streaming with a tool that supports streaming."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=StreamingTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="streaming", arguments={})

    await strategy._stream_tool_call(call, queue, timeout=5.0)

    # Collect results
    results = []
    while not queue.empty():
        results.append(await queue.get())

    # Should have multiple streaming results
    assert len(results) == 3
    assert all(r.tool == "streaming" for r in results)
    assert [r.result for r in results] == ["item_0", "item_1", "item_2"]


@pytest.mark.asyncio
async def test_stream_tool_call_non_streaming_tool():
    """Test streaming with a regular non-streaming tool."""

    class NonStreamingTool:
        async def execute(self, **kwargs):
            return "regular_result"

    registry = Mock()
    registry.get_tool = AsyncMock(return_value=NonStreamingTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="regular", arguments={})

    await strategy._stream_tool_call(call, queue, timeout=5.0)

    # Should have single result
    result = await queue.get()
    assert result.tool == "regular"
    assert result.result == "regular_result"


@pytest.mark.asyncio
async def test_stream_tool_call_cancelled():
    """Test handling of cancellation in stream_tool_call."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=SlowStreamingTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="slow", arguments={})

    # Create task and cancel it
    task = asyncio.create_task(strategy._stream_tool_call(call, queue, timeout=10.0))
    await asyncio.sleep(0.1)
    task.cancel()

    # Wait for task to complete
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Should have cancellation result in queue
    if not queue.empty():
        result = await queue.get()
        assert "cancelled" in result.error.lower() or "cancel" in result.error.lower()


# ============================================================================
# Tests for stream_with_timeout (lines 311-383)
# ============================================================================


@pytest.mark.asyncio
async def test_stream_with_timeout_success():
    """Test successful streaming with timeout."""
    tool = StreamingTool()
    call = ToolCall(tool="test", arguments={})
    queue = asyncio.Queue()

    strategy = InProcessStrategy(Mock())
    await strategy._stream_with_timeout(tool, call, queue, timeout=5.0)

    # Collect all results
    results = []
    while not queue.empty():
        results.append(await queue.get())

    assert len(results) == 3
    assert all(r.error is None for r in results)


@pytest.mark.asyncio
async def test_stream_with_timeout_timeout():
    """Test streaming timeout."""
    tool = SlowStreamingTool()
    call = ToolCall(tool="slow", arguments={})
    queue = asyncio.Queue()

    strategy = InProcessStrategy(Mock())
    await strategy._stream_with_timeout(tool, call, queue, timeout=0.1)

    # Should have timeout result
    result = await queue.get()
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_stream_with_timeout_error():
    """Test streaming error handling."""
    tool = StreamingErrorTool()
    call = ToolCall(tool="error", arguments={})
    queue = asyncio.Queue()

    strategy = InProcessStrategy(Mock())
    await strategy._stream_with_timeout(tool, call, queue, timeout=5.0)

    # Collect results
    results = []
    while not queue.empty():
        results.append(await queue.get())

    # Should have first result and error
    assert len(results) == 2
    assert results[0].result == "first"
    assert "Stream failed" in results[1].error


# ============================================================================
# Tests for tool resolution (lines 573-574, 621-633, 645-649, 657-683)
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_tool_info_namespaced():
    """Test resolving namespaced tool names."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Test namespaced format
    tool, ns = await strategy._resolve_tool_info("custom.tool2")
    assert tool == StreamingTool
    assert ns == "custom"


@pytest.mark.asyncio
async def test_resolve_tool_info_preferred_namespace():
    """Test resolution with preferred namespace."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Should find in preferred namespace first
    tool, ns = await strategy._resolve_tool_info("tool1", preferred_namespace="other")
    assert tool == SlowStreamingTool  # Different implementation in 'other'
    assert ns == "other"


@pytest.mark.asyncio
async def test_resolve_tool_info_fallback_to_default():
    """Test fallback to default namespace."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Not in custom, should fall back to default
    tool, ns = await strategy._resolve_tool_info("tool1", preferred_namespace="custom")
    assert tool == StreamingTool
    assert ns == "default"


@pytest.mark.asyncio
async def test_resolve_tool_info_search_all_namespaces():
    """Test searching all namespaces when not in preferred/default."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # tool2 only exists in 'custom' namespace
    tool, ns = await strategy._resolve_tool_info("tool2", preferred_namespace="default")
    assert tool == StreamingTool
    assert ns == "custom"


@pytest.mark.asyncio
async def test_resolve_tool_info_not_found():
    """Test when tool is not found in any namespace."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    tool, ns = await strategy._resolve_tool_info("nonexistent")
    assert tool is None
    assert ns is None


@pytest.mark.asyncio
async def test_resolve_tool_info_error_handling():
    """Test error handling during namespace search."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=None)
    registry.list_namespaces = AsyncMock(side_effect=RuntimeError("Registry error"))

    strategy = InProcessStrategy(registry)

    tool, ns = await strategy._resolve_tool_info("test")
    assert tool is None
    assert ns is None


# ============================================================================
# Tests for shutdown (lines 704-731)
# ============================================================================


@pytest.mark.asyncio
async def test_shutdown_with_active_tasks():
    """Test shutdown with active tasks."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    # Create some mock active tasks
    async def dummy_task():
        await asyncio.sleep(0.1)

    task1 = asyncio.create_task(dummy_task())
    task2 = asyncio.create_task(dummy_task())

    strategy._active_tasks.add(task1)
    strategy._active_tasks.add(task2)

    # Shutdown should handle them
    await strategy.shutdown()

    assert strategy._shutting_down
    assert strategy._shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_already_shutting_down():
    """Test that shutdown returns early if already shutting down."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    strategy._shutting_down = True

    # Should return immediately
    await strategy.shutdown()

    # Event should not be set (since we returned early)
    assert not strategy._shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_with_exception_in_task():
    """Test shutdown handles exceptions in tasks gracefully."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    # Create a task that raises an exception
    async def failing_task():
        raise RuntimeError("Task failed")

    task = asyncio.create_task(failing_task())
    strategy._active_tasks.add(task)

    # Shutdown should handle it gracefully
    await strategy.shutdown()

    assert strategy._shutting_down


# ============================================================================
# Tests for edge cases in _execute_single_call (lines 461-485)
# ============================================================================


@pytest.mark.asyncio
async def test_execute_single_call_when_shutting_down():
    """Test execute returns early when shutting down."""
    registry = Mock()
    strategy = InProcessStrategy(registry)
    strategy._shutting_down = True

    call = ToolCall(tool="test", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert result.error == "System is shutting down"


@pytest.mark.asyncio
async def test_execute_single_call_cancelled():
    """Test handling of cancellation in execute."""
    registry = Mock()
    registry.get_tool = AsyncMock(side_effect=asyncio.CancelledError())
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    call = ToolCall(tool="test", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert "cancelled" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_single_call_setup_error():
    """Test handling of setup errors."""
    registry = Mock()
    registry.get_tool = AsyncMock(side_effect=RuntimeError("Setup failed"))
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    call = ToolCall(tool="test", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert "Setup error" in result.error or "Setup failed" in result.error


# ============================================================================
# Additional edge case tests to reach 90%+ coverage
# ============================================================================


@pytest.mark.asyncio
async def test_legacy_execute_method():
    """Test the legacy execute() method that forwards to run()."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    calls = [ToolCall(tool="tool1", arguments={})]
    results = await strategy.execute(calls, timeout=1.0)

    assert len(results) == 1
    assert results[0].error is None


@pytest.mark.asyncio
async def test_stream_run_with_empty_calls():
    """Test stream_run with empty calls list."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    results = []
    async for result in strategy.stream_run([]):
        results.append(result)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_stream_run_cancellation():
    """Test stream_run handles cancellation."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Create a slow streaming tool
    calls = [ToolCall(tool="tool1", arguments={})] * 5

    task = asyncio.create_task(strategy.stream_run(calls).__anext__())
    await asyncio.sleep(0.05)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stream_tool_call_tool_not_found():
    """Test _stream_tool_call with non-existent tool."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=None)
    registry.list_namespaces = AsyncMock(return_value=["default"])
    registry.list_tools = AsyncMock(return_value=[])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="nonexistent", arguments={})

    await strategy._stream_tool_call(call, queue, timeout=1.0)

    result = await queue.get()
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_stream_tool_call_exception():
    """Test _stream_tool_call with exception during setup."""
    registry = Mock()
    registry.get_tool = AsyncMock(side_effect=RuntimeError("Registry error"))
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="test", arguments={})

    await strategy._stream_tool_call(call, queue, timeout=1.0)

    result = await queue.get()
    assert "Error setting up execution" in result.error


@pytest.mark.asyncio
async def test_stream_with_timeout_general_exception():
    """Test _stream_with_timeout with general exception."""

    class FailingTool:
        supports_streaming = True

        async def stream_execute(self, **kwargs):
            raise RuntimeError("Unexpected error")
            yield  # Make this an async generator

    tool = FailingTool()
    call = ToolCall(tool="failing", arguments={})
    queue = asyncio.Queue()

    strategy = InProcessStrategy(Mock())
    await strategy._stream_with_timeout(tool, call, queue, timeout=5.0)

    # Should have error result
    result = await queue.get()
    assert "Streaming error" in result.error or "Unexpected error" in result.error


@pytest.mark.asyncio
async def test_execute_to_queue():
    """Test _execute_to_queue method."""

    class SimpleTool:
        async def execute(self, **kwargs):
            return "result"

    registry = Mock()
    registry.get_tool = AsyncMock(return_value=SimpleTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="simple", arguments={})

    await strategy._execute_to_queue(call, queue, timeout=1.0)

    result = await queue.get()
    assert result.result == "result"


@pytest.mark.asyncio
async def test_execute_to_queue_with_direct_streaming():
    """Test _execute_to_queue skips direct streaming calls."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    queue = asyncio.Queue()
    call = ToolCall(tool="test", arguments={}, id="marked")

    strategy.mark_direct_streaming({"marked"})

    await strategy._execute_to_queue(call, queue, timeout=1.0)

    # Should not add anything to queue
    assert queue.empty()


@pytest.mark.asyncio
async def test_run_with_timeout_exception_in_semaphore():
    """Test exception handling in _execute_single_call within semaphore."""

    class FailingTool:
        async def execute(self, **kwargs):
            raise ValueError("Tool execution failed")

    registry = Mock()
    registry.get_tool = AsyncMock(return_value=FailingTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    call = ToolCall(tool="failing", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert "Tool execution failed" in result.error or "Unexpected error" in result.error


@pytest.mark.asyncio
async def test_run_with_timeout_cancelled_error():
    """Test CancelledError in _run_with_timeout."""

    class CancellingTool:
        async def execute(self, **kwargs):
            raise asyncio.CancelledError()

    registry = Mock()
    registry.get_tool = AsyncMock(return_value=CancellingTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = InProcessStrategy(registry)

    call = ToolCall(tool="cancelling", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert "cancelled" in result.error.lower()


@pytest.mark.asyncio
async def test_resolve_namespaced_tool_not_found():
    """Test namespaced tool lookup when tool not found."""
    registry = NamespacedRegistry()
    strategy = InProcessStrategy(registry)

    # Try to find nonexistent tool with namespace prefix
    tool, ns = await strategy._resolve_tool_info("custom.nonexistent")
    assert tool is None
    assert ns is None


@pytest.mark.asyncio
async def test_resolve_fuzzy_matching():
    """Test fuzzy matching in tool resolution."""

    class SimpleTool:
        async def execute(self, **kwargs):
            return "fuzzy_result"

    class FuzzyRegistry:
        async def get_tool(self, name: str, namespace: str = "default"):
            # Return the tool only when fuzzy match calls with correct namespace
            if name == "special_tool" and namespace == "custom":
                return SimpleTool
            return None

        async def list_namespaces(self):
            return ["default", "custom"]

        async def list_tools(self):
            # Return tools with namespace, name tuples
            return [("custom", "special_tool")]

    registry = FuzzyRegistry()
    strategy = InProcessStrategy(registry)

    # This should trigger fuzzy matching
    tool, ns = await strategy._resolve_tool_info("special_tool", preferred_namespace="default")

    # Fuzzy match should find it in custom namespace
    assert tool == SimpleTool
    assert ns == "custom"


@pytest.mark.asyncio
async def test_supports_streaming_property():
    """Test supports_streaming property."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    assert strategy.supports_streaming is True


@pytest.mark.asyncio
async def test_shutdown_with_task_cancellation_error():
    """Test shutdown handles task cancellation exceptions."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    # Create a task that's already done but cancelled
    async def cancelled_task():
        raise asyncio.CancelledError()

    task = asyncio.create_task(cancelled_task())
    await asyncio.sleep(0.01)  # Let it cancel

    strategy._active_tasks.add(task)

    # Shutdown should handle it gracefully
    await strategy.shutdown()

    assert strategy._shutting_down


@pytest.mark.asyncio
async def test_shutdown_timeout_handling():
    """Test shutdown with timeout during gather."""
    registry = Mock()
    strategy = InProcessStrategy(registry)

    # Create a task that takes longer than shutdown timeout
    async def long_task():
        await asyncio.sleep(10)

    task = asyncio.create_task(long_task())
    strategy._active_tasks.add(task)

    # Shutdown should handle timeout gracefully
    await strategy.shutdown()

    assert strategy._shutting_down
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
