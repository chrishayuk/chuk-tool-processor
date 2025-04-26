"""
Unit-tests for the InProcessStrategy (with the _execute / _aexecute API).

They rely only on the public surface of chuk_tool_processor – no private
attributes are touched.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict

import pytest

from chuk_tool_processor.execution.strategies.inprocess_strategy import (
    InProcessStrategy,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# minimal fake registry used by all tests
# --------------------------------------------------------------------------- #
class DummyRegistry:
    def __init__(self, tools: Dict[str, object] | None = None):
        self._tools = tools or {}

    # strategy only calls get_tool()
    def get_tool(self, name: str):
        return self._tools.get(name)


# --------------------------------------------------------------------------- #
# helper classes used in multiple tests
# --------------------------------------------------------------------------- #
class SyncTool:
    """Synchronous tool using the *new* _execute naming convention."""

    def __init__(self, multiplier: int = 1):
        self.multiplier = multiplier

    def _execute(self, x: int, y: int):
        return (x + y) * self.multiplier


class AsyncTool:
    """Asynchronous tool using preferred _aexecute."""

    async def _aexecute(self, a: int, b: int):
        await asyncio.sleep(0)  # yield control to event-loop
        return a * b


class SleepTool:
    """Async tool that just waits – useful for timeout tests."""

    def __init__(self, delay: float):
        self.delay = delay

    async def _aexecute(self):
        await asyncio.sleep(self.delay)
        return "done"


class ErrorTool:
    """Tool that always raises a ValueError."""

    def _execute(self):
        raise ValueError("oops")


# --------------------------------------------------------------------------- #
# individual test-cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sync_tool_execution():
    reg = DummyRegistry({"sync": SyncTool(multiplier=2)})
    strat = InProcessStrategy(registry=reg, default_timeout=1.0)

    call = ToolCall(tool="sync", arguments={"x": 3, "y": 4})
    res: ToolResult = (await strat.run([call]))[0]

    assert res.error is None
    assert res.result == 14
    assert res.tool == "sync"
    assert isinstance(res.start_time, datetime) and isinstance(
        res.end_time, datetime
    )
    assert res.end_time >= res.start_time


@pytest.mark.asyncio
async def test_async_tool_execution():
    reg = DummyRegistry({"async": AsyncTool()})
    strat = InProcessStrategy(registry=reg)

    call = ToolCall(tool="async", arguments={"a": 5, "b": 6})
    res = (await strat.run([call]))[0]

    assert res.error is None
    assert res.result == 30


@pytest.mark.asyncio
async def test_tool_not_found():
    strat = InProcessStrategy(registry=DummyRegistry())

    res = (await strat.run([ToolCall(tool="missing", arguments={})]))[0]
    assert res.error == "Tool not found"
    assert res.result is None


@pytest.mark.asyncio
async def test_timeout_error():
    reg = DummyRegistry({"sleep": SleepTool(delay=0.2)})
    strat = InProcessStrategy(registry=reg, default_timeout=0.05)

    res = (await strat.run([ToolCall(tool="sleep", arguments={})]))[0]
    assert res.error.startswith("Timeout after")
    assert res.result is None


@pytest.mark.asyncio
async def test_unexpected_error():
    reg = DummyRegistry({"err": ErrorTool()})
    strat = InProcessStrategy(registry=reg)

    res = (await strat.run([ToolCall(tool="err", arguments={})]))[0]
    assert res.error == "oops"
    assert res.result is None


@pytest.mark.asyncio
async def test_max_concurrency_limits():
    current = 0
    max_seen = 0
    lock = asyncio.Lock()

    class ConcurrencyTool:
        async def _aexecute(self, idx: int):
            nonlocal current, max_seen
            async with lock:
                current += 1
                max_seen = max(max_seen, current)
            await asyncio.sleep(0.01)  # hold the semaphore for a tick
            async with lock:
                current -= 1
            return idx

    tools = {str(i): ConcurrencyTool() for i in range(5)}
    reg = DummyRegistry(tools)
    strat = InProcessStrategy(registry=reg, max_concurrency=2)

    calls = [ToolCall(tool=str(i), arguments={"idx": i}) for i in range(5)]
    results = await strat.run(calls)

    # concurrency limit respected
    assert max_seen <= 2
    # result order preserved
    assert [r.result for r in results] == list(range(5))
