import pytest
import asyncio
import os
import time
from datetime import datetime, timezone
import importlib

from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy, _execute_tool_in_process
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class DummyRegistry:
    def __init__(self, tools=None):
        # tools: dict of name -> implementation (class or instance)
        self._tools = tools or {}

    def get_tool(self, name):
        return self._tools.get(name)


def test_tool_not_found(tmp_path):
    registry = DummyRegistry()
    strat = SubprocessStrategy(registry=registry, max_workers=1)

    call = ToolCall(tool='missing', arguments={})
    results = asyncio.get_event_loop().run_until_complete(strat.run([call], timeout=0.1))
    res = results[0]
    assert res.error == 'Tool not found'
    assert res.result is None


def test_sync_tool_execution(tmp_path):
    # Define a sync tool in this module
    class SyncTool:
        def execute(self, x, y):
            return x + y

    registry = DummyRegistry(tools={'add': SyncTool})
    strat = SubprocessStrategy(registry=registry, max_workers=1)
    call = ToolCall(tool='add', arguments={'x': 2, 'y': 3})
    results = asyncio.get_event_loop().run_until_complete(strat.run([call], timeout=1))
    res = results[0]
    assert res.error is None
    assert res.result == 5
    assert res.tool == 'add'
    assert isinstance(res.start_time, datetime)
    assert isinstance(res.end_time, datetime)


def test_async_tool_execution(tmp_path):
    # Define an async tool in this module
    class AsyncTool:
        async def execute(self, a, b):
            await asyncio.sleep(0)
            return a * b

    registry = DummyRegistry(tools={'mul': AsyncTool})
    strat = SubprocessStrategy(registry=registry, max_workers=1)
    call = ToolCall(tool='mul', arguments={'a': 4, 'b': 5})
    results = asyncio.get_event_loop().run_until_complete(strat.run([call], timeout=1))
    res = results[0]
    assert res.error is None
    assert res.result == 20


def test_timeout_error(tmp_path):
    # Sync tool that sleeps
    class SleepTool:
        def execute(self):
            time.sleep(0.2)
            return 'done'

    registry = DummyRegistry(tools={'sleep': SleepTool})
    strat = SubprocessStrategy(registry=registry, max_workers=1)
    call = ToolCall(tool='sleep', arguments={})
    results = asyncio.get_event_loop().run_until_complete(strat.run([call], timeout=0.05))
    res = results[0]
    assert 'Timeout after' in res.error
    assert res.result is None


def test_unexpected_exception(tmp_path):
    # Sync tool that raises
    class ErrorTool:
        def execute(self):
            raise RuntimeError('fail_op')

    registry = DummyRegistry(tools={'err': ErrorTool})
    strat = SubprocessStrategy(registry=registry, max_workers=1)
    call = ToolCall(tool='err', arguments={})
    results = asyncio.get_event_loop().run_until_complete(strat.run([call], timeout=1))
    res = results[0]
    assert res.error == 'fail_op'
    assert res.result is None
