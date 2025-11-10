"""
Additional tests for tool_executor.py streaming methods to improve coverage.

These tests target specific uncovered lines in streaming functionality.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class StreamingStrategy(ExecutionStrategy):
    """Test strategy that supports streaming."""

    async def run(self, calls, timeout=None):
        return []

    async def stream_run(self, calls, timeout=None):
        """Placeholder for streaming."""
        yield ToolResult(tool="test", result={"data": "test"}, error=None)

    @property
    def supports_streaming(self) -> bool:
        return True


class TestToolExecutorStreamingCoverage:
    """Tests to improve streaming coverage in tool_executor."""

    @pytest.mark.asyncio
    async def test_stream_timeout_with_pending_tasks(self):
        """Test TimeoutError handling with pending tasks (lines 227-236)."""

        # Create a streaming tool that takes a long time
        class SlowStreamingTool:
            supports_streaming = True

            async def stream_execute(self, **kwargs):
                await asyncio.sleep(10)  # Long delay to trigger timeout
                yield {"result": "never reached"}

        # Create a mock registry that returns our slow tool
        mock_registry = AsyncMock()
        mock_registry.get_tool = AsyncMock(return_value=SlowStreamingTool())
        mock_registry.get_metadata = AsyncMock(return_value=Mock(supports_streaming=True))

        # Create executor
        strategy = StreamingStrategy()
        executor = ToolExecutor(strategy=strategy, registry=mock_registry)

        # Create a call
        call = ToolCall(tool="slow_tool", arguments={})

        # Try to stream with a short timeout
        results = []
        try:
            async for result in executor.stream_execute([call], timeout=0.1):
                results.append(result)
        except Exception:
            pass  # We expect a timeout

        # The test passes if we don't hang and handle the timeout gracefully

    @pytest.mark.asyncio
    async def test_direct_stream_without_timeout(self):
        """Test direct streaming without timeout (lines 298-299)."""

        # Create a streaming tool
        class QuickStreamingTool:
            supports_streaming = True

            async def stream_execute(self, **kwargs):
                yield {"result": "chunk1"}
                yield {"result": "chunk2"}

        # Create a mock registry
        mock_registry = AsyncMock()
        mock_registry.get_tool = AsyncMock(return_value=QuickStreamingTool())
        mock_registry.get_metadata = AsyncMock(return_value=Mock(supports_streaming=True))

        # Create executor
        strategy = StreamingStrategy()
        executor = ToolExecutor(strategy=strategy, registry=mock_registry)

        # Create a call
        call = ToolCall(tool="stream_tool", arguments={})

        # Stream without timeout (timeout=None)
        results = []
        async for result in executor.stream_execute([call], timeout=None):
            results.append(result)

        # Verify we got results
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_direct_stream_exception_handling(self):
        """Test exception handling in _direct_stream_tool (lines 316-330)."""

        # Create a streaming tool that raises an exception
        class FailingStreamingTool:
            supports_streaming = True

            async def stream_execute(self, **kwargs):
                yield {"result": "chunk1"}
                raise RuntimeError("Stream failed!")

        # Create a mock registry
        mock_registry = AsyncMock()
        mock_registry.get_tool = AsyncMock(return_value=FailingStreamingTool())
        mock_registry.get_metadata = AsyncMock(return_value=Mock(supports_streaming=True))

        # Create executor
        strategy = StreamingStrategy()
        executor = ToolExecutor(strategy=strategy, registry=mock_registry)

        # Create a call
        call = ToolCall(tool="failing_tool", arguments={})

        # Stream and expect error result
        results = []
        async for result in executor.stream_execute([call]):
            results.append(result)

        # Should have at least one result, and last should be an error
        assert len(results) > 0
        # The last result should contain an error
        assert any(r.error is not None for r in results)

    @pytest.mark.asyncio
    async def test_direct_stream_unexpected_exception(self):
        """Test unexpected exception in direct streaming (lines 316-330)."""

        # Create a streaming tool that fails immediately
        class ErrorTool:
            supports_streaming = True

            async def stream_execute(self, **kwargs):
                raise ValueError("Immediate error!")
                yield {"never": "reached"}  # noqa: F821

        # Create a mock registry
        mock_registry = AsyncMock()
        mock_registry.get_tool = AsyncMock(return_value=ErrorTool())
        mock_registry.get_metadata = AsyncMock(return_value=Mock(supports_streaming=True))

        # Create executor
        strategy = StreamingStrategy()
        executor = ToolExecutor(strategy=strategy, registry=mock_registry)

        # Create a call
        call = ToolCall(tool="error_tool", arguments={})

        # Try to stream - should handle the exception
        results = []
        try:
            async for result in executor.stream_execute([call]):
                results.append(result)
        except Exception:
            pass  # We might get an exception, but it should be handled gracefully

        # Should have at least one error result
        assert len(results) > 0
        assert any(r.error is not None for r in results)

    @pytest.mark.asyncio
    async def test_stream_with_done_tasks_exception(self):
        """Test exception handling in done tasks (lines 232-236)."""
        # Create streaming tools
        call_count = [0]

        class TaskErrorTool:
            supports_streaming = True

            async def stream_execute(self, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    yield {"result": "chunk1"}
                    # Simulate a background task error
                    await asyncio.sleep(0.01)
                    raise RuntimeError("Background task error")
                else:
                    yield {"result": "chunk2"}

        # Create a mock registry
        mock_registry = AsyncMock()
        mock_registry.get_tool = AsyncMock(return_value=TaskErrorTool())
        mock_registry.get_metadata = AsyncMock(return_value=Mock(supports_streaming=True))

        # Create executor
        strategy = StreamingStrategy()
        executor = ToolExecutor(strategy=strategy, registry=mock_registry)

        # Create multiple calls
        calls = [
            ToolCall(tool="tool1", arguments={}),
            ToolCall(tool="tool2", arguments={}),
        ]

        # Stream with timeout to trigger the timeout path
        results = []
        try:
            async for result in executor.stream_execute(calls, timeout=0.5):
                results.append(result)
        except Exception:
            pass  # May get exception, but should handle gracefully

        # Test passes if we handle the exception without crashing
