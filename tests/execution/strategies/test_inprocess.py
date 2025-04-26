import pytest
import asyncio
import time
from datetime import datetime, timezone

from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class DummyRegistry:
    def __init__(self, tools=None, metadata=None):
        # tools: dict name->impl
        self._tools = tools or {}
        self._metadata = metadata or {}

    def get_tool(self, name):
        return self._tools.get(name)

    def get_metadata(self, name):
        # Return metadata with is_async
        return self._metadata.get(name)


class SyncTool:
    def __init__(self, multiplier=1):
        self.multiplier = multiplier
    def execute(self, x: int, y: int):
        return (x + y) * self.multiplier


class AsyncTool:
    async def execute(self, a: int, b: int):
        await asyncio.sleep(0)  # yield control
        return a * b


class SleepTool:
    def __init__(self, delay):
        self.delay = delay
    async def execute(self):
        await asyncio.sleep(self.delay)
        return "done"


class ErrorTool:
    def execute(self):
        raise ValueError("oops")


class DummyMetadata:
    def __init__(self, is_async: bool):
        self.is_async = is_async


@pytest.mark.asyncio
async def test_sync_tool_execution():
    tool = SyncTool(multiplier=2)
    registry = DummyRegistry(tools={'sync': tool}, metadata={'sync': DummyMetadata(is_async=False)})
    strat = InProcessStrategy(registry=registry, default_timeout=1.0)

    call = ToolCall(tool='sync', arguments={'x': 3, 'y': 4})
    results = await strat.run([call])
    res = results[0]
    assert res.error is None
    assert res.result == 14
    assert res.tool == 'sync'
    assert isinstance(res.start_time, datetime)
    assert isinstance(res.end_time, datetime)


@pytest.mark.asyncio
async def test_async_tool_execution():
    tool = AsyncTool()
    registry = DummyRegistry(tools={'async': tool}, metadata={'async': DummyMetadata(is_async=True)})
    strat = InProcessStrategy(registry=registry)

    call = ToolCall(tool='async', arguments={'a': 5, 'b': 6})
    results = await strat.run([call])
    res = results[0]
    assert res.error is None
    assert res.result == 30


@pytest.mark.asyncio
async def test_tool_not_found():
    registry = DummyRegistry()
    strat = InProcessStrategy(registry=registry)

    call = ToolCall(tool='missing', arguments={})
    results = await strat.run([call])
    res = results[0]
    assert res.error == "Tool not found"
    assert res.result is None


@pytest.mark.asyncio
async def test_timeout_error():
    # tool that sleeps longer than timeout
    tool = SleepTool(delay=0.2)
    registry = DummyRegistry(tools={'sleep': tool}, metadata={'sleep': DummyMetadata(is_async=True)})
    strat = InProcessStrategy(registry=registry, default_timeout=0.05)

    call = ToolCall(tool='sleep', arguments={})
    results = await strat.run([call])
    res = results[0]
    assert res.error.startswith("Timeout after")
    assert res.result is None


@pytest.mark.asyncio
async def test_unexpected_error():
    tool = ErrorTool()
    registry = DummyRegistry(tools={'error': tool})
    strat = InProcessStrategy(registry=registry)

    call = ToolCall(tool='error', arguments={})
    results = await strat.run([call])
    res = results[0]
    assert res.error == "oops"
    assert res.result is None


@pytest.mark.asyncio
async def test_max_concurrency_limits():
    # track max concurrency
    current = 0
    max_seen = 0
    lock = asyncio.Lock()

    class ConcurrencyTool:
        async def execute(self, idx):
            nonlocal current, max_seen
            async with lock:
                current += 1
                max_seen = max(max_seen, current)
            # sleep to hold semaphore
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1
            return idx

    tools = {str(i): ConcurrencyTool() for i in range(5)}
    metadata = {str(i): DummyMetadata(is_async=True) for i in range(5)}
    registry = DummyRegistry(tools=tools, metadata=metadata)
    strat = InProcessStrategy(registry=registry, max_concurrency=2)

    calls = [ToolCall(tool=str(i), arguments={'idx': i}) for i in range(5)]
    results = await strat.run(calls)
    # ensure concurrency limit respected
    assert max_seen <= 2
    # results order and values correct
    assert [r.result for r in results] == list(range(5))
