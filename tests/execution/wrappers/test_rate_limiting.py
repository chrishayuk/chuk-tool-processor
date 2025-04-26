import asyncio
import time
import pytest

from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimiter, RateLimitedToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.core.exceptions import ToolExecutionError

class DummyExecutor:
    def __init__(self):
        self.called = []

    async def execute(self, calls, timeout=None):
        self.called.append((tuple(c.tool for c in calls), timeout))
        # echo back a ToolResult per call
        return [ToolResult(tool=c.tool, result="ok") for c in calls]

@pytest.mark.asyncio
async def test_global_rate_limit_without_limit(monkeypatch):
    limiter = RateLimiter(global_limit=None)
    slept = []
    monkeypatch.setattr(asyncio, 'sleep', lambda t: slept.append(t) or asyncio.sleep(0))

    # No limit, should never sleep
    await limiter.wait('anytool')
    await limiter.wait('anytool')
    assert slept == []

@pytest.mark.asyncio
async def test_global_rate_limit_with_limit(monkeypatch):
    # simulate time progression
    times = [0]
    def fake_time(): return times[0]
    monkeypatch.setattr(time, 'time', fake_time)

    slept = []
    async def fake_sleep(duration):
        slept.append(duration)
        # advance time artificially
        times[0] += duration
    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)

    limiter = RateLimiter(global_limit=2, global_period=10)
    # first two requests at time=0
    await limiter.wait('t')
    await limiter.wait('t')
    # third should sleep until earliest timestamp + period = 0+10
    await limiter.wait('t')
    assert slept == [10]

@pytest.mark.asyncio
async def test_tool_specific_rate_limit(monkeypatch):
    times = [0]
    monkeypatch.setattr(time, 'time', lambda: times[0])
    slept = []
    async def fake_sleep(duration):
        slept.append(duration)
        times[0] += duration
    monkeypatch.setattr(asyncio, 'sleep', fake_sleep)

    limiter = RateLimiter(tool_limits={'tool1': (1, 5)})
    # first call for tool1
    await limiter.wait('tool1')  # time 0
    # second call should sleep until 0+5
    await limiter.wait('tool1')
    assert slept == [5]

@pytest.mark.asyncio
async def test_rate_limited_executor_invokes_wait_and_execute(monkeypatch):
    dummy = DummyExecutor()
    calls = [ToolCall(tool='a', arguments={}), ToolCall(tool='b', arguments={})]
    # Track waits
    waited = []
    class FakeLimiter:
        async def wait(self, tool):
            waited.append(tool)
    executor = RateLimitedToolExecutor(executor=dummy, rate_limiter=FakeLimiter())

    # Execute
    results = await executor.execute(calls, timeout=2.5)

    # wait called for each tool in order
    assert waited == ['a', 'b']
    # underlying executor called once with same calls and timeout
    assert dummy.called == [(('a', 'b'), 2.5)]
    # results are ToolResult objects
    assert all(isinstance(r, ToolResult) for r in results)
    assert [r.result for r in results] == ['ok', 'ok']
