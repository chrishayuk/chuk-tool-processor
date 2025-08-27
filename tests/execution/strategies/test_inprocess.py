# tests/execution/strategies/test_inprocess.py
"""
Unit tests for the InProcessStrategy that executes tools concurrently in the same process.

These tests verify that the InProcessStrategy correctly:
- Executes tools concurrently with proper semaphore control
- Handles timeouts and errors correctly
- Supports both _aexecute and execute async entry points
- Maintains call order in the results
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall


# Common Mock Registry for tests
class MockRegistry:
    """Mock registry that implements the async ToolRegistryInterface."""

    def __init__(self, tools: dict[str, Any] = None):
        self._tools = tools or {}

    async def get_tool(self, name: str, namespace: str = "default") -> Any | None:
        """Async version of get_tool to match the ToolRegistryInterface."""
        return self._tools.get(name)

    async def get_metadata(self, name: str, namespace: str = "default") -> Any | None:
        """Mock metadata retrieval."""
        if name in self._tools:
            return {"description": f"Mock metadata for {name}", "supports_streaming": False}
        return None

    async def list_tools(self, namespace: str | None = None) -> list:
        """Mock list_tools method."""
        return [(namespace or "default", name) for name in self._tools]


# --------------------------------------------------------------------------- #
# Sample tools for testing
# --------------------------------------------------------------------------- #


class AddTool:
    """Simple tool that adds two numbers using the public execute method."""

    async def execute(self, x: int, y: int):
        return x + y


class MulTool:
    """Tool that multiplies two numbers using the private _aexecute method."""

    async def _aexecute(self, a: int, b: int):
        await asyncio.sleep(0.01)  # Small delay to simulate work
        return a * b


class SleepTool:
    """Tool that sleeps for a configurable time."""

    def __init__(self, delay: float = 0.2):
        self.delay = delay

    async def execute(self):
        await asyncio.sleep(self.delay)
        return {"done": True, "pid": os.getpid(), "timestamp": datetime.now().isoformat()}


class ErrorTool:
    """Tool that raises an exception."""

    async def execute(self):
        raise RuntimeError("fail_op")


class SlowTool:
    """Tool that takes a configurable amount of time to execute."""

    def __init__(self, name: str, delay: float = 0.5):
        self.name = name
        self.delay = delay

    async def execute(self):
        start_time = time.time()
        await asyncio.sleep(self.delay)
        return {"name": self.name, "delay": self.delay, "actual_delay": time.time() - start_time}


class SyncTool:
    """Tool with only a synchronous entry point (should be rejected)."""

    def execute(self, x: int, y: int):
        return x + y


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def registry():
    """Create a registry with test tools."""
    return MockRegistry(
        {
            "add": AddTool,
            "mul": MulTool,
            "sleep": SleepTool,
            "error": ErrorTool,
            "slow1": SlowTool("slow1", 0.3),
            "slow2": SlowTool("slow2", 0.3),
            "sync": SyncTool,
        }
    )


@pytest_asyncio.fixture
async def strategy(registry):
    """Create an InProcessStrategy with the test registry."""
    return InProcessStrategy(registry, default_timeout=1.0)


@pytest_asyncio.fixture
async def limited_strategy(registry):
    """Create an InProcessStrategy with a concurrency limit of 1."""
    return InProcessStrategy(registry, default_timeout=1.0, max_concurrency=1)


# --------------------------------------------------------------------------- #
# Basic tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tool_not_found(strategy):
    """Test that a non-existent tool returns an appropriate error."""
    res = (await strategy.run([ToolCall(tool="missing", arguments={})], timeout=0.5))[0]
    assert res.error and "not found" in res.error.lower()
    assert res.result is None


@pytest.mark.asyncio
async def test_add_tool_execution(strategy):
    """Test that a simple add tool works correctly."""
    res = (await strategy.run([ToolCall(tool="add", arguments={"x": 2, "y": 3})], timeout=1))[0]
    assert res.result == 5
    assert res.error is None
    assert isinstance(res.start_time, datetime)
    assert res.end_time >= res.start_time


@pytest.mark.asyncio
async def test_mul_tool_execution(strategy):
    """Test that a tool using _aexecute works correctly."""
    res = (await strategy.run([ToolCall(tool="mul", arguments={"a": 4, "b": 5})], timeout=1))[0]
    assert res.result == 20
    assert res.error is None


@pytest.mark.asyncio
async def test_timeout_error(strategy):
    """Test that timeouts are handled correctly."""
    res = (await strategy.run([ToolCall(tool="sleep", arguments={})], timeout=0.05))[0]
    assert res.result is None
    assert res.error and "timeout" in res.error.lower()


@pytest.mark.asyncio
async def test_unexpected_exception(strategy):
    """Test that exceptions in tools are handled correctly."""
    res = (await strategy.run([ToolCall(tool="error", arguments={})], timeout=1))[0]
    assert res.result is None
    assert "fail_op" in res.error


@pytest.mark.asyncio
async def test_sync_tool_rejected(strategy):
    """Test that tools with only synchronous entry points are rejected."""
    res = (await strategy.run([ToolCall(tool="sync", arguments={"x": 1, "y": 2})], timeout=1))[0]
    assert res.result is None
    assert "async" in res.error.lower()


# --------------------------------------------------------------------------- #
# Concurrency tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_concurrent_execution(strategy):
    """Test that tools execute concurrently in the same process."""
    # Run two slow tools concurrently - should take about 0.3s, not 0.6s
    start_time = time.time()
    results = await strategy.run([ToolCall(tool="slow1", arguments={}), ToolCall(tool="slow2", arguments={})])
    duration = time.time() - start_time

    # Verify both completed successfully
    assert all(r.error is None for r in results)

    # Verify they ran concurrently (allowing some buffer)
    assert duration < 0.5, f"Expected duration < 0.5s, got {duration}s"

    # Verify they ran in the same process
    pids = [r.pid for r in results]
    assert len(set(pids)) == 1, f"Expected same PID, got {pids}"
    assert pids[0] == os.getpid(), "Tools didn't run in the main process"


@pytest.mark.asyncio
async def test_concurrency_limit(limited_strategy):
    """Test that the concurrency limit is respected."""
    # Run two slow tools with a concurrency limit of 1
    # Should take about 0.6s (0.3s + 0.3s), not 0.3s
    start_time = time.time()
    results = await limited_strategy.run([ToolCall(tool="slow1", arguments={}), ToolCall(tool="slow2", arguments={})])
    duration = time.time() - start_time

    # Verify both completed successfully
    assert all(r.error is None for r in results)

    # Verify they ran sequentially due to semaphore
    assert duration >= 0.5, f"Expected duration >= 0.5s, got {duration}s"
    assert duration < 0.8, f"Expected duration < 0.8s, got {duration}s"


@pytest.mark.asyncio
async def test_results_preserve_order(strategy):
    """Test that results preserve the order of calls."""
    # Run tools in a specific order
    calls = [
        ToolCall(tool="add", arguments={"x": 1, "y": 2}),
        ToolCall(tool="sleep", arguments={}),
        ToolCall(tool="mul", arguments={"a": 3, "b": 4}),
        ToolCall(tool="add", arguments={"x": 5, "y": 6}),
    ]

    results = await strategy.run(calls)

    # Verify the order is preserved
    assert len(results) == 4
    assert results[0].tool == "add" and results[0].result == 3
    assert results[1].tool == "sleep" and results[1].error is None
    assert results[2].tool == "mul" and results[2].result == 12
    assert results[3].tool == "add" and results[3].result == 11


# --------------------------------------------------------------------------- #
# Streaming support tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_run(strategy):
    """Test stream_run implementation."""
    # Tools that complete at different speeds
    calls = [
        ToolCall(tool="add", arguments={"x": 1, "y": 2}),  # Fast
        ToolCall(tool="slow1", arguments={}),  # 0.3s
        ToolCall(tool="sleep", arguments={}),  # 0.2s
    ]

    # Use stream_run to get results as they become available
    results = []
    start_time = time.time()

    async for result in strategy.stream_run(calls):
        results.append({"tool": result.tool, "elapsed": time.time() - start_time})

    # Should have 3 results
    assert len(results) == 3

    # Sort by arrival time
    results.sort(key=lambda r: r["elapsed"])

    # The add tool should complete first
    assert results[0]["tool"] == "add"
    assert results[0]["elapsed"] < 0.1  # Should be very quick

    # The sleep tool (0.2s) should complete second
    assert results[1]["tool"] == "sleep"
    assert 0.1 < results[1]["elapsed"] < 0.25

    # The slow1 tool (0.3s) should complete last
    assert results[2]["tool"] == "slow1"
    assert 0.2 < results[2]["elapsed"] < 0.4


# --------------------------------------------------------------------------- #
# Edge cases and error handling
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_empty_calls_list(strategy):
    """Test that an empty calls list returns an empty results list."""
    results = await strategy.run([])
    assert isinstance(results, list)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_mixed_success_and_failure(strategy):
    """Test a mix of successful and failed tool calls."""
    calls = [
        ToolCall(tool="add", arguments={"x": 1, "y": 2}),  # Should succeed
        ToolCall(tool="missing", arguments={}),  # Should fail (not found)
        ToolCall(tool="error", arguments={}),  # Should fail (raises exception)
        ToolCall(tool="mul", arguments={"a": 3, "b": 4}),  # Should succeed
    ]

    results = await strategy.run(calls)

    # Check individual results
    assert len(results) == 4
    assert results[0].error is None and results[0].result == 3
    assert results[1].error is not None and "not found" in results[1].error.lower()
    assert results[2].error is not None and "fail_op" in results[2].error
    assert results[3].error is None and results[3].result == 12


# tests/execution/strategies/test_inprocess.py
# Only update the test_timeout_cancels_execution function


@pytest.mark.asyncio
async def test_timeout_cancels_execution(registry):
    """Test that a timeout properly cancels the tool execution."""

    # Create a tool that hangs indefinitely unless cancelled
    class HangingTool:
        async def execute(self):
            # This will hang unless the TimeoutError propagates
            # and cancels this coroutine
            try:
                await asyncio.sleep(3600)  # 1 hour
                return "This should never return"
            except asyncio.CancelledError:
                # We expect this to be cancelled
                return "Cancelled as expected"

    registry._tools["hanging"] = HangingTool
    strategy = InProcessStrategy(registry, default_timeout=1.0)

    # Execute with a short timeout
    start_time = time.time()
    res = (await strategy.run([ToolCall(tool="hanging", arguments={})], timeout=0.1))[0]
    duration = time.time() - start_time

    # Should timeout quickly
    assert duration < 0.3, f"Expected quick timeout, took {duration}s"

    # Check for either a timeout error OR a cancelled result
    # Both are acceptable outcomes since they show the long operation was interrupted
    assert (res.error and "timeout" in res.error.lower()) or (
        res.result == "Cancelled as expected" and res.error is None
    ), "Expected either a timeout error or a cancelled result"
