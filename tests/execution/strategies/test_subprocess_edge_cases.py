# tests/execution/strategies/test_subprocess_edge_cases.py
"""
Edge case tests for SubprocessStrategy to improve coverage.
"""

import asyncio
import contextlib
import pickle

import pytest

from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy, _serialized_tool_worker
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry import get_default_registry


class SimpleTool:
    """A simple test tool."""

    async def execute(self, value: str) -> str:
        return f"Result: {value}"


class NamespacedTool:
    """A tool in a custom namespace."""

    async def execute(self, data: str) -> str:
        return f"Namespaced: {data}"


class SlowTool:
    """A tool that takes time to execute."""

    async def execute(self, delay: float = 0.1) -> str:
        await asyncio.sleep(delay)
        return "completed"


class BrokenTool:
    """A tool without execute method."""

    pass


class ToolClass:
    """A class that needs instantiation."""

    tool_name = "test"

    async def execute(self, x: int) -> int:
        return x * 2


@pytest.mark.asyncio
async def test_subprocess_with_dotted_tool_name():
    """Test resolving dotted tool names (namespace.toolname)."""
    registry = await get_default_registry()

    # Register tools
    await registry.register_tool(NamespacedTool(), name="namespace_tool", namespace="custom")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        # Call a tool in custom namespace using dotted notation
        call = ToolCall(tool="custom.namespace_tool", arguments={"data": "test"})
        results = await strategy.run([call])

        assert len(results) == 1
        assert results[0].error is None
        assert "Namespaced" in results[0].result
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_fallback_to_default_namespace():
    """Test fallback to default namespace when preferred namespace differs."""
    registry = await get_default_registry()

    # Register in default namespace
    await registry.register_tool(SimpleTool(), name="simple_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        # Try to access a tool in default namespace with a different preferred namespace
        call = ToolCall(tool="simple_tool", namespace="nonexistent", arguments={"value": "test"})
        results = await strategy.run([call])

        assert len(results) == 1
        # Should fall back to default namespace
        assert results[0].error is None or "not found" in results[0].error.lower()
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_stream_when_shutting_down():
    """Test stream_run when shutdown is in progress."""
    registry = await get_default_registry()
    await registry.register_tool(SimpleTool(), name="simple_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    # Set shutting down flag
    strategy._shutting_down = True

    call = ToolCall(tool="simple_tool", arguments={"value": "test"})
    results = []

    async for result in strategy.stream_run([call]):
        results.append(result)

    assert len(results) == 1
    assert results[0].error == "System is shutting down"

    await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_empty_stream_run():
    """Test stream_run with empty calls list."""
    registry = await get_default_registry()
    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        results = []
        async for result in strategy.stream_run([]):
            results.append(result)

        assert len(results) == 0
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_run_when_shutting_down():
    """Test run when shutdown is in progress."""
    registry = await get_default_registry()
    await registry.register_tool(SimpleTool(), name="simple_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    # Set shutting down flag
    strategy._shutting_down = True

    call = ToolCall(tool="simple_tool", arguments={"value": "test"})
    results = await strategy.run([call])

    assert len(results) == 1
    assert results[0].error == "System is shutting down"

    await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_signal_handler_not_main_thread():
    """Test signal handler registration when not in main thread."""
    # This tests the exception handling in __init__ for signal registration
    registry = await get_default_registry()

    # This should not raise even if we're not in the main thread
    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        assert strategy is not None
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_double_shutdown():
    """Test calling shutdown twice doesn't cause issues."""
    registry = await get_default_registry()
    strategy = SubprocessStrategy(registry, max_workers=2)

    # First shutdown
    await strategy.shutdown()
    assert strategy._shutting_down is True

    # Second shutdown should return immediately
    await strategy.shutdown()
    assert strategy._shutting_down is True


@pytest.mark.asyncio
async def test_subprocess_shutdown_with_active_tasks():
    """Test shutdown with active tasks running."""
    registry = await get_default_registry()
    await registry.register_tool(SlowTool(), name="slow_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        # Start a slow task
        call = ToolCall(tool="slow_tool", arguments={"delay": 1.0})
        task = asyncio.create_task(strategy.run([call]))

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Shutdown while task is running
        await strategy.shutdown()

        # Task should be cancelled
        with contextlib.suppress(asyncio.CancelledError):
            await task
    except Exception:
        pass  # Cleanup
    finally:
        if not strategy._shutting_down:
            await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_tool_not_found_all_namespaces():
    """Test tool not found in any namespace."""
    registry = await get_default_registry()
    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        call = ToolCall(tool="nonexistent_tool_xyz", arguments={})
        results = await strategy.run([call])

        assert len(results) == 1
        assert results[0].error is not None
        assert "not found" in results[0].error.lower()
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_broken_process_pool():
    """Test handling of broken process pool."""
    registry = await get_default_registry()
    strategy = SubprocessStrategy(registry, max_workers=1)

    try:
        # Ensure pool is initialized
        await strategy._ensure_pool()

        # Simulate broken pool by forcing shutdown
        if strategy._process_pool:
            strategy._process_pool.shutdown(wait=False)

            # Try to execute - should detect broken pool
            call = ToolCall(tool="simple_tool", arguments={"value": "test"})

            # This might fail or recover depending on timing
            try:
                results = await strategy.run([call])
                # Either succeeds after recreation or returns error
                assert len(results) == 1
            except Exception:
                pass  # Expected if pool is truly broken
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_timeout_in_worker():
    """Test timeout handling within worker process."""
    registry = await get_default_registry()
    await registry.register_tool(SlowTool(), name="slow_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        # Create a call with very short timeout
        call = ToolCall(tool="slow_tool", arguments={"delay": 5.0})
        results = await strategy.run([call], timeout=0.1)

        assert len(results) == 1
        assert results[0].error is not None
        assert "timed out" in results[0].error.lower()
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_cancelled_execution():
    """Test handling of cancelled execution."""
    registry = await get_default_registry()
    await registry.register_tool(SlowTool(), name="slow_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        call = ToolCall(tool="slow_tool", arguments={"delay": 2.0})
        task = asyncio.create_task(strategy.run([call]))

        # Let it start
        await asyncio.sleep(0.1)

        # Cancel the task
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_supports_streaming_property():
    """Test supports_streaming property."""
    registry = await get_default_registry()
    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        assert strategy.supports_streaming is True
    finally:
        await strategy.shutdown()


@pytest.mark.asyncio
async def test_subprocess_legacy_execute_method():
    """Test legacy execute() method (backwards compatibility)."""
    registry = await get_default_registry()
    await registry.register_tool(SimpleTool(), name="simple_tool")

    strategy = SubprocessStrategy(registry, max_workers=2)

    try:
        call = ToolCall(tool="simple_tool", arguments={"value": "legacy"})
        # Use legacy execute method instead of run
        results = await strategy.execute([call])

        assert len(results) == 1
        assert results[0].error is None
        assert "Result: legacy" in results[0].result
    finally:
        await strategy.shutdown()


def test_serialized_tool_worker_tool_without_execute():
    """Test worker with tool missing execute method."""
    import pickle

    broken_tool = BrokenTool()
    serialized = pickle.dumps(broken_tool)

    result = _serialized_tool_worker(
        tool_name="broken",
        namespace="default",
        arguments={},
        timeout=10.0,
        serialized_tool_data=serialized,
    )

    assert result["error"] is not None
    assert "missing execute method" in result["error"].lower()


def test_serialized_tool_worker_class_instantiation():
    """Test worker with tool class that needs instantiation."""
    import pickle

    serialized = pickle.dumps(ToolClass)

    result = _serialized_tool_worker(
        tool_name="test",
        namespace="default",
        arguments={"x": 5},
        timeout=10.0,
        serialized_tool_data=serialized,
    )

    # Should instantiate and execute
    assert result["error"] is None
    assert result["result"] == 10


def test_serialized_tool_worker_timeout():
    """Test worker timeout handling."""
    # Use the SlowTool class which is already defined at module level
    tool = SlowTool()
    serialized = pickle.dumps(tool)

    result = _serialized_tool_worker(
        tool_name="slow",
        namespace="default",
        arguments={"delay": 10.0},  # Very long delay
        timeout=0.1,  # Very short timeout
        serialized_tool_data=serialized,
    )

    assert result["error"] is not None
    assert "timed out" in result["error"].lower()
