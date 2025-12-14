#!/usr/bin/env python
"""
Additional tests to improve coverage for SubprocessStrategy.

Target uncovered lines:
- Lines 104, 108-114, 118, 122-124: Worker initialization
- Lines 135, 147-148: Pool initialization errors
- Lines 208-210, 219: Shutdown handling
- Lines 235-240, 258, 280: Stream execution edge cases
- Lines 330, 334-344: Execute to queue
- Lines 379-380, 445-447: Tool serialization failures
- Lines 506-515, 553-559: Process pool recovery
- Lines 591-603, 615-619, 627-653: Tool resolution
- Lines 664, 668-670, 675, 690-691, 699, 701, 720-728: Signal handling and shutdown
"""

import asyncio
import concurrent.futures
import pickle
import signal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from chuk_tool_processor.execution.strategies.subprocess_strategy import (
    SubprocessStrategy,
    _init_worker,
    _pool_test_func,
    _serialized_tool_worker,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# Test Tools
class UnpickleableTool:
    """Tool that cannot be pickled."""

    def __init__(self):
        self.unpickleable = lambda: None  # Lambda cannot be pickled

    async def execute(self, **kwargs):
        return "result"


class NoExecuteTool:
    """Tool without an execute method."""

    pass


class ToolWithoutName:
    """Tool that doesn't have a tool_name attribute."""

    async def execute(self, **kwargs):
        return "result"


class FailingInstantiationTool:
    """Tool class that fails to instantiate."""

    def __init__(self):
        raise RuntimeError("Cannot instantiate")

    async def execute(self, **kwargs):
        return "should not reach here"


class NamespacedRegistry:
    """Registry with namespace support."""

    def __init__(self):
        self.tools = {
            "default": {"tool1": ToolWithoutName},
            "custom": {"tool2": UnpickleableTool},
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


# Define tools at module level to make them pickleable
class SimpleTool:
    """Simple tool for testing."""

    tool_name = "test"

    async def execute(self, x: int):
        return x * 2


class ToolClass:
    """Tool class for testing."""

    async def execute(self, x: int):
        return x + 1


class SlowTool:
    """Slow tool for timeout testing."""

    async def execute(self):
        await asyncio.sleep(10)
        return "done"


class ErrorToolWorker:
    """Tool that raises an error."""

    async def execute(self):
        raise ValueError("Tool error")


# ============================================================================
# Tests for worker functions (lines 104, 108-114, 118)
# ============================================================================


def test_init_worker():
    """Test worker initialization."""
    # Save original handler
    original_handler = signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        _init_worker()
        # Should set SIGINT to SIG_IGN
        current_handler = signal.signal(signal.SIGINT, signal.SIG_DFL)
        assert current_handler == signal.SIG_IGN
    finally:
        # Restore original handler
        signal.signal(signal.SIGINT, original_handler)


def test_pool_test_func():
    """Test the pool test function."""
    assert _pool_test_func() == "ok"


def test_serialized_tool_worker_success():
    """Test successful tool worker execution."""
    tool = SimpleTool()
    serialized = pickle.dumps(tool)

    result = _serialized_tool_worker("test", "default", {"x": 5}, 1.0, serialized)

    assert result["tool"] == "test"
    assert result["namespace"] == "default"
    assert result["result"] == 10
    assert result["error"] is None


def test_serialized_tool_worker_with_class():
    """Test worker with a tool class instead of instance."""
    serialized = pickle.dumps(ToolClass)

    result = _serialized_tool_worker("test", "default", {"x": 5}, 1.0, serialized)

    assert result["result"] == 6
    assert result["error"] is None


def test_serialized_tool_worker_instantiation_failure():
    """Test worker when tool class fails to instantiate."""
    serialized = pickle.dumps(FailingInstantiationTool)

    result = _serialized_tool_worker("test", "default", {}, 1.0, serialized)

    assert result["error"] is not None
    assert "instantiate" in result["error"]


def test_serialized_tool_worker_no_execute():
    """Test worker when tool has no execute method."""
    tool = NoExecuteTool()
    serialized = pickle.dumps(tool)

    result = _serialized_tool_worker("test", "default", {}, 1.0, serialized)

    assert result["error"] == "Tool missing execute method"


def test_serialized_tool_worker_timeout():
    """Test worker with timeout."""
    tool = SlowTool()
    serialized = pickle.dumps(tool)

    result = _serialized_tool_worker("test", "default", {}, 0.01, serialized)

    assert result["error"] is not None
    assert "timed out" in result["error"]


def test_serialized_tool_worker_execution_error():
    """Test worker when tool raises an error."""
    tool = ErrorToolWorker()
    serialized = pickle.dumps(tool)

    result = _serialized_tool_worker("test", "default", {}, 1.0, serialized)

    assert result["error"] is not None
    assert "Tool error" in result["error"]


def test_serialized_tool_worker_deserialization_error():
    """Test worker with invalid serialized data."""
    result = _serialized_tool_worker("test", "default", {}, 1.0, b"invalid pickle data")

    assert result["error"] is not None
    assert "Worker error" in result["error"]


# ============================================================================
# Tests for pool initialization (lines 135, 147-148)
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_pool_initialization_error():
    """Test pool initialization failure."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=2)

    # Mock ProcessPoolExecutor to fail
    with patch("concurrent.futures.ProcessPoolExecutor") as mock_pool_class:
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool

        # Make the test function fail
        async def failing_test(*args, **kwargs):
            raise RuntimeError("Pool test failed")

        with patch.object(strategy, "_process_pool", None), patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=failing_test)

            with pytest.raises(RuntimeError, match="Failed to initialize process pool"):
                await strategy._ensure_pool()

                # Pool should be cleaned up
                mock_pool.shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_ensure_pool_already_initialized():
    """Test that ensure_pool returns early if already initialized."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Set up a mock pool
    strategy._process_pool = Mock()

    # Should return without doing anything
    await strategy._ensure_pool()

    # Pool should still be the same mock
    assert isinstance(strategy._process_pool, Mock)


# ============================================================================
# Tests for shutdown scenarios (lines 208-210, 219, 235-240)
# ============================================================================


@pytest.mark.asyncio
async def test_run_when_shutting_down():
    """Test run returns error results when shutting down."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)
    strategy._shutting_down = True

    calls = [ToolCall(tool="test1", arguments={}), ToolCall(tool="test2", arguments={})]

    results = await strategy.run(calls)

    assert len(results) == 2
    assert all(r.error == "System is shutting down" for r in results)


@pytest.mark.asyncio
async def test_stream_run_when_shutting_down():
    """Test stream_run yields error results when shutting down."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)
    strategy._shutting_down = True

    calls = [ToolCall(tool="test", arguments={})]

    results = []
    async for result in strategy.stream_run(calls):
        results.append(result)

    assert len(results) == 1
    assert results[0].error == "System is shutting down"


# ============================================================================
# Tests for execute_to_queue (lines 330, 334-344)
# ============================================================================


@pytest.mark.asyncio
async def test_execute_to_queue():
    """Test execute_to_queue method."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=ToolWithoutName)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = SubprocessStrategy(registry)

    # Mock the pool
    strategy._process_pool = MagicMock()

    queue = asyncio.Queue()
    call = ToolCall(tool="test", arguments={})

    # Mock execute_single_call
    async def mock_execute(c, t):
        return ToolResult(tool=c.tool, result="queued_result")

    strategy._execute_single_call = mock_execute

    await strategy._execute_to_queue(call, queue, timeout=1.0)

    result = await queue.get()
    assert result.result == "queued_result"


# ============================================================================
# Tests for serialization failures (lines 379-380, 445-447)
# ============================================================================


@pytest.mark.asyncio
async def test_execute_single_call_unpickleable_tool():
    """Test handling of unpickleable tools."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=UnpickleableTool)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = SubprocessStrategy(registry)

    # Ensure pool is initialized
    strategy._process_pool = MagicMock()

    call = ToolCall(tool="unpickleable", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert result.error is not None
    assert "serialization failed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_single_call_cancelled():
    """Test handling of cancellation."""
    registry = Mock()
    registry.get_tool = AsyncMock(side_effect=asyncio.CancelledError())
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = SubprocessStrategy(registry)

    call = ToolCall(tool="test", arguments={})
    result = await strategy._execute_single_call(call, timeout=1.0)

    assert "cancelled" in result.error.lower()


# ============================================================================
# Tests for broken process pool (lines 506-515)
# ============================================================================


@pytest.mark.asyncio
async def test_broken_process_pool_recovery():
    """Test recovery from broken process pool."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=ToolWithoutName)
    registry.list_namespaces = AsyncMock(return_value=["default"])

    strategy = SubprocessStrategy(registry)

    # Set up mock pool that raises BrokenProcessPool
    mock_pool = MagicMock()
    strategy._process_pool = mock_pool

    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=concurrent.futures.process.BrokenProcessPool())

        call = ToolCall(tool="test", arguments={})
        result = await strategy._execute_single_call(call, timeout=1.0)

        assert "Worker process crashed" in result.error
        assert strategy._process_pool is None  # Should be reset
        mock_pool.shutdown.assert_called_once_with(wait=False)


# ============================================================================
# Tests for tool resolution (lines 591-603, 615-619, 627-653)
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_tool_info_namespaced_not_found():
    """Test namespaced tool resolution when tool not found."""
    registry = NamespacedRegistry()
    strategy = SubprocessStrategy(registry)

    tool, ns = await strategy._resolve_tool_info("custom.nonexistent")
    assert tool is None
    assert ns is None


@pytest.mark.asyncio
async def test_resolve_tool_info_fuzzy_matching():
    """Test fuzzy matching in tool resolution."""
    registry = Mock()

    async def mock_get_tool(name, namespace):
        if name == "test_tool" and namespace == "found":
            return ToolWithoutName
        return None

    registry.get_tool = mock_get_tool
    registry.list_namespaces = AsyncMock(return_value=["default", "found"])
    registry.list_tools = AsyncMock(return_value=[("found", "test_tool"), ("default", "other_tool")])

    strategy = SubprocessStrategy(registry)

    # Should find via fuzzy matching
    tool, ns = await strategy._resolve_tool_info("test_tool")
    assert tool == ToolWithoutName
    assert ns == "found"


@pytest.mark.asyncio
async def test_resolve_tool_info_exception_handling():
    """Test exception handling in tool resolution."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=None)
    registry.list_namespaces = AsyncMock(side_effect=RuntimeError("Registry error"))

    strategy = SubprocessStrategy(registry)

    tool, ns = await strategy._resolve_tool_info("test")
    assert tool is None
    assert ns is None


# ============================================================================
# Tests for signal handling and shutdown (lines 664, 668-670, 675, 690-691, 699, 701, 720-728)
# ============================================================================


@pytest.mark.asyncio
async def test_signal_handler():
    """Test signal handler."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Mock shutdown
    strategy.shutdown = AsyncMock()

    await strategy._signal_handler(signal.SIGTERM)

    strategy.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_with_null_pool():
    """Test shutdown when pool is None."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)
    strategy._process_pool = None

    # Should handle gracefully
    await strategy.shutdown()

    assert strategy._shutting_down
    assert strategy._shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_with_timeout():
    """Test shutdown with timeout handling."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Create a mock pool
    mock_pool = MagicMock()
    strategy._process_pool = mock_pool

    # Create slow task
    async def slow_task():
        await asyncio.sleep(10)

    task = asyncio.create_task(slow_task())
    strategy._active_tasks.add(task)

    # Shutdown should handle timeout
    await strategy.shutdown()

    assert strategy._shutting_down
    mock_pool.shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_shutdown_pool_error():
    """Test shutdown handles pool errors gracefully."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Create a pool that raises on shutdown
    mock_pool = MagicMock()
    mock_pool.shutdown.side_effect = RuntimeError("Pool error")
    strategy._process_pool = mock_pool

    # Should handle error gracefully
    await strategy.shutdown()

    assert strategy._shutting_down
    assert strategy._process_pool is None


@pytest.mark.asyncio
async def test_shutdown_race_condition():
    """Test shutdown handles race conditions."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Set up a pool
    mock_pool = MagicMock()
    strategy._process_pool = mock_pool

    # Simulate race condition by setting pool to None during shutdown
    original_shutdown = mock_pool.shutdown

    def shutdown_with_race(*args, **kwargs):
        strategy._process_pool = None
        return original_shutdown(*args, **kwargs)

    mock_pool.shutdown = shutdown_with_race

    # Should handle gracefully
    await strategy.shutdown()

    assert strategy._shutting_down


# ============================================================================
# Tests for warm pool feature (lines 176, 186-188, 236-246, 705-729)
# ============================================================================


@pytest.mark.asyncio
async def test_warm_pool_parameter():
    """Test warm_pool parameter pre-warms all workers."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=4, warm_pool=True)

    assert strategy._warm_pool is True

    # Clean up without initializing pool
    strategy._shutting_down = True


@pytest.mark.asyncio
async def test_warm_pool_disabled_default():
    """Test warm_pool is disabled by default."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=4)

    assert strategy._warm_pool is False

    # Clean up without initializing pool
    strategy._shutting_down = True


@pytest.mark.asyncio
async def test_is_pool_ready_property():
    """Test is_pool_ready property."""
    registry = Mock()
    strategy = SubprocessStrategy(registry)

    # Pool not ready initially
    assert strategy.is_pool_ready is False

    # Mock pool
    strategy._process_pool = Mock()
    assert strategy.is_pool_ready is True

    # Clean up
    strategy._process_pool = None
    strategy._shutting_down = True


@pytest.mark.asyncio
async def test_explicit_warm_method():
    """Test explicit warm() method pre-warms all workers."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=2)

    # Initially warm_pool is False
    assert strategy._warm_pool is False

    call_count = 0

    async def mock_ensure_pool():
        nonlocal call_count
        call_count += 1
        strategy._process_pool = Mock()

    strategy._ensure_pool = mock_ensure_pool

    # Call warm() method
    await strategy.warm()

    # Should have called _ensure_pool with _warm_pool temporarily True
    assert call_count == 1

    # warm_pool should be restored to original value
    assert strategy._warm_pool is False

    # Clean up
    strategy._process_pool = None
    strategy._shutting_down = True


@pytest.mark.asyncio
async def test_ensure_pool_warm_all_workers():
    """Test _ensure_pool pre-warms all workers when warm_pool=True."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=3, warm_pool=True)

    call_count = 0

    # Track how many times the executor is called
    async def count_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return "ok"

    with (
        patch("concurrent.futures.ProcessPoolExecutor") as mock_pool_class,
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        mock_loop.return_value.run_in_executor = count_calls

        await strategy._ensure_pool()

        # Should have made max_workers calls (3)
        assert call_count == 3

    strategy._shutting_down = True


@pytest.mark.asyncio
async def test_ensure_pool_single_test_without_warm():
    """Test _ensure_pool only tests single worker when warm_pool=False."""
    registry = Mock()
    strategy = SubprocessStrategy(registry, max_workers=3, warm_pool=False)

    call_count = 0

    async def count_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return "ok"

    with (
        patch("concurrent.futures.ProcessPoolExecutor") as mock_pool_class,
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool
        mock_loop.return_value.run_in_executor = count_calls

        await strategy._ensure_pool()

        # Should have made only 1 call (single test)
        assert call_count == 1

    strategy._shutting_down = True
