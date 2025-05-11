# tests/execution/wrappers/test_rate_limiting.py
import asyncio
import time
from typing import List, Tuple

import pytest

from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimiter,
    RateLimitedToolExecutor,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class DummyExecutor:
    """Echoes back a ToolResult for every call and records invocations."""

    def __init__(self):
        self.called: List[Tuple[Tuple[str, ...], float | None]] = []

    async def execute(self, calls, timeout=None):
        self.called.append((tuple(c.tool for c in calls), timeout))
        return [ToolResult(tool=c.tool, result="ok") for c in calls]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_global_rate_limit_none(monkeypatch):
    limiter = RateLimiter(global_limit=None)

    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(t):
        slept.append(t)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await limiter.wait("tool")
    await limiter.wait("tool")
    assert slept == []  # never slept when limit is None


@pytest.mark.asyncio
async def test_global_rate_limit(monkeypatch):
    # Simulate monotonic clock
    now = [0.0]

    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    slept: list[float] = []

    async def fake_sleep(dur):
        slept.append(dur)
        now[0] += dur  # advance virtual clock

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    limiter = RateLimiter(global_limit=2, global_period=10)

    # first two pass immediately
    await limiter.wait("t")
    await limiter.wait("t")

    # third must wait 10 seconds
    await limiter.wait("t")
    assert slept == [10]


@pytest.mark.asyncio
async def test_tool_specific_rate_limit(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    slept: list[float] = []

    async def fake_sleep(dur):
        slept.append(dur)
        now[0] += dur

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    limiter = RateLimiter(tool_limits={"tool1": (1, 5)})

    await limiter.wait("tool1")  # at t = 0
    await limiter.wait("tool1")  # should sleep 5 s
    assert slept == [5]


@pytest.mark.asyncio
async def test_rate_limited_executor(monkeypatch):
    waited: list[str] = []

    class FakeLimiter:
        async def wait(self, tool):
            waited.append(tool)

    dummy_exec = DummyExecutor()
    rl_exec = RateLimitedToolExecutor(dummy_exec, FakeLimiter())

    calls = [ToolCall(tool="a", arguments={}), ToolCall(tool="b", arguments={})]
    results = await rl_exec.execute(calls, timeout=2.5)

    assert waited == ["a", "b"]
    assert dummy_exec.called == [(("a", "b"), 2.5)]
    assert [r.result for r in results] == ["ok", "ok"]
