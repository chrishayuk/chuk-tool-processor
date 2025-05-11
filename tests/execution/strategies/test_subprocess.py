# tests/execution/strategies/test_subprocess.py
"""
Unit-tests for the delegating SubprocessStrategy (wraps InProcessStrategy).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict

import pytest

from chuk_tool_processor.execution.strategies.subprocess_strategy import (
    SubprocessStrategy,
)
from chuk_tool_processor.models.tool_call import ToolCall


class DummyRegistry:
    def __init__(self, tools: Dict[str, object] | None = None):
        self._tools = tools or {}

    def get_tool(self, name):
        return self._tools.get(name)


class AddTool:
    async def execute(self, x: int, y: int):
        return x + y


class MulTool:
    async def _aexecute(self, a: int, b: int):
        await asyncio.sleep(0)
        return a * b


class SleepTool:
    def __init__(self, delay: float):
        self.delay = delay

    async def _aexecute(self):
        await asyncio.sleep(self.delay)
        return "done"


class ErrorTool:
    async def execute(self):
        raise RuntimeError("fail_op")


@pytest.mark.asyncio
async def test_tool_not_found():
    strat = SubprocessStrategy(DummyRegistry(), max_workers=1)
    res = (
        await strat.run([ToolCall(tool="missing", arguments={})], timeout=0.1)
    )[0]
    assert res.error == "Tool not found" and res.result is None


@pytest.mark.asyncio
async def test_add_tool_execution():
    reg = DummyRegistry({"add": AddTool()})
    strat = SubprocessStrategy(reg, max_workers=1)

    res = (
        await strat.run(
            [ToolCall(tool="add", arguments={"x": 2, "y": 3})], timeout=1
        )
    )[0]
    assert res.result == 5 and res.error is None
    assert isinstance(res.start_time, datetime) and res.end_time >= res.start_time


@pytest.mark.asyncio
async def test_mul_tool_execution():
    reg = DummyRegistry({"mul": MulTool()})
    strat = SubprocessStrategy(reg, max_workers=1)

    res = (
        await strat.run(
            [ToolCall(tool="mul", arguments={"a": 4, "b": 5})], timeout=1
        )
    )[0]
    assert res.result == 20 and res.error is None


@pytest.mark.asyncio
async def test_timeout_error():
    reg = DummyRegistry({"sleep": SleepTool(delay=0.2)})
    strat = SubprocessStrategy(reg, max_workers=1)

    res = (
        await strat.run(
            [ToolCall(tool="sleep", arguments={})], timeout=0.05
        )
    )[0]
    assert res.result is None and res.error.startswith("Timeout after")


@pytest.mark.asyncio
async def test_unexpected_exception():
    reg = DummyRegistry({"err": ErrorTool()})
    strat = SubprocessStrategy(reg, max_workers=1)

    res = (
        await strat.run(
            [ToolCall(tool="err", arguments={})], timeout=1
        )
    )[0]
    assert res.result is None and res.error == "fail_op"

