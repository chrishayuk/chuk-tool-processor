"""
Unit-tests for the delegating `SubprocessStrategy`.

NB:  The real strategy now just wraps an `InProcessStrategy`, so we only
     need to verify the high-level behaviour, not the fork/exec path.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from chuk_tool_processor.execution.strategies.subprocess_strategy import (
    SubprocessStrategy,
)
from chuk_tool_processor.models.tool_call import ToolCall


# --------------------------------------------------------------------------- #
# minimal fake registry
# --------------------------------------------------------------------------- #
class DummyRegistry:
    def __init__(self, tools=None):
        self._tools = tools or {}

    def get_tool(self, name):
        return self._tools.get(name)


# --------------------------------------------------------------------------- #
# helper tool classes
# --------------------------------------------------------------------------- #
class SyncTool:
    def _execute(self, x, y):
        return x + y


class AsyncTool:
    async def _aexecute(self, a, b):
        await asyncio.sleep(0)
        return a * b


class SleepTool:
    def _execute(self):  # still sync – used to force timeout quickly
        time.sleep(0.2)
        return "done"


class ErrorTool:
    def _execute(self):
        raise RuntimeError("fail_op")


# --------------------------------------------------------------------------- #
# individual tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_tool_not_found():
    strat = SubprocessStrategy(registry=DummyRegistry(), max_workers=1)

    res = (await strat.run([ToolCall(tool="missing", arguments={})], timeout=0.1))[0]
    assert res.error == "Tool not found"
    assert res.result is None


@pytest.mark.asyncio
async def test_sync_tool_execution():
    reg = DummyRegistry({"add": SyncTool})
    strat = SubprocessStrategy(registry=reg, max_workers=1)

    res = (
        await strat.run([ToolCall(tool="add", arguments={"x": 2, "y": 3})], timeout=1)
    )[0]
    assert res.error is None
    assert res.result == 5
    assert res.tool == "add"
    assert isinstance(res.start_time, datetime) and isinstance(
        res.end_time, datetime
    )
    assert res.end_time >= res.start_time


@pytest.mark.asyncio
async def test_async_tool_execution():
    reg = DummyRegistry({"mul": AsyncTool})
    strat = SubprocessStrategy(registry=reg, max_workers=1)

    res = (
        await strat.run([ToolCall(tool="mul", arguments={"a": 4, "b": 5})], timeout=1)
    )[0]
    assert res.error is None
    assert res.result == 20


@pytest.mark.asyncio
async def test_timeout_error():
    reg = DummyRegistry({"sleep": SleepTool})
    strat = SubprocessStrategy(registry=reg, max_workers=1)

    res = (
        await strat.run([ToolCall(tool="sleep", arguments={})], timeout=0.05)
    )[0]
    assert res.result is None
    assert res.error.startswith("Timeout after")


@pytest.mark.asyncio
async def test_unexpected_exception():
    reg = DummyRegistry({"err": ErrorTool})
    strat = SubprocessStrategy(registry=reg, max_workers=1)

    res = (await strat.run([ToolCall(tool="err", arguments={})], timeout=1))[0]
    assert res.result is None
    assert res.error == "fail_op"

