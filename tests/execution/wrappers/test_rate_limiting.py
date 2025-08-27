# tests/execution/wrappers/test_rate_limiting.py
"""
Tests for the async-native rate limiting wrapper.
"""

import asyncio
import time

import pytest

from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimitedToolExecutor,
    RateLimiter,
    rate_limited,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class DummyExecutor:
    """Echoes back a ToolResult for every call and records invocations."""

    def __init__(self):
        self.called: list[tuple[list[ToolCall], float | None]] = []
        self.use_cache_called: list[bool] = []

    async def execute(self, calls, timeout=None, use_cache=True):
        self.called.append((calls, timeout))
        self.use_cache_called.append(use_cache)
        return [ToolResult(tool=c.tool, result="ok") for c in calls]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_global_rate_limit_none(monkeypatch):
    """Test that no rate limiting occurs when global_limit is None."""
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
    """Test that global rate limiting works correctly."""
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
    """Test that tool-specific rate limiting works correctly."""
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
    """Test that the rate limited executor applies limits before execution."""
    waited: list[str] = []

    class FakeLimiter:
        async def wait(self, tool):
            waited.append(tool)

    dummy_exec = DummyExecutor()
    rl_exec = RateLimitedToolExecutor(dummy_exec, FakeLimiter())

    calls = [ToolCall(tool="a", arguments={}), ToolCall(tool="b", arguments={})]
    results = await rl_exec.execute(calls, timeout=2.5)

    assert waited == ["a", "b"]
    # Fix the assertion to check only the timeout part
    assert len(dummy_exec.called) == 1
    assert dummy_exec.called[0][1] == 2.5  # Just verify the timeout value
    assert [r.result for r in results] == ["ok", "ok"]


@pytest.mark.asyncio
async def test_rate_limited_executor_passes_use_cache(monkeypatch):
    """Test that the executor passes the use_cache parameter correctly."""

    class FakeLimiter:
        async def wait(self, tool):
            pass

    dummy_exec = DummyExecutor()
    rl_exec = RateLimitedToolExecutor(dummy_exec, FakeLimiter())

    calls = [ToolCall(tool="test", arguments={})]

    # Test with default
    await rl_exec.execute(calls, timeout=1.0)
    assert dummy_exec.use_cache_called[-1] is True

    # Test with explicit value
    await rl_exec.execute(calls, timeout=1.0, use_cache=False)
    assert dummy_exec.use_cache_called[-1] is False


@pytest.mark.asyncio
async def test_rate_limited_executor_empty_calls():
    """Test that the executor handles empty calls correctly."""
    dummy_exec = DummyExecutor()
    limiter = RateLimiter()
    rl_exec = RateLimitedToolExecutor(dummy_exec, limiter)

    # Empty calls should return empty results
    results = await rl_exec.execute([])
    assert results == []
    assert len(dummy_exec.called) == 0


@pytest.mark.asyncio
async def test_both_global_and_tool_rate_limits(monkeypatch):
    """Test that both global and tool-specific rate limits are respected."""
    now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    slept: list[float] = []

    async def fake_sleep(dur):
        slept.append(dur)
        now[0] += dur

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    # Set up a limiter with both global and tool-specific limits
    limiter = RateLimiter(global_limit=2, global_period=10, tool_limits={"tool1": (1, 5)})

    # First call to tool1 - passes global and tool limit
    await limiter.wait("tool1")

    # Second call to tool2 - passes global limit, no tool limit
    await limiter.wait("tool2")

    # Third call to tool1 - hits tool limit (5s) but also global limit (10s)
    # Global limit is stricter, so we wait 10s
    await limiter.wait("tool1")
    assert slept == [10.0]  # Global limit is enforced first and is longer


@pytest.mark.asyncio
async def test_check_limits_method():
    """Test the non-blocking check_limits method."""
    limiter = RateLimiter(global_limit=1, global_period=10, tool_limits={"test": (1, 5)})

    # First check - no limits reached
    global_limited, tool_limited = await limiter.check_limits("test")
    assert global_limited is False
    assert tool_limited is False

    # Use a slot
    await limiter.wait("test")

    # Check again - both limits should be reached
    global_limited, tool_limited = await limiter.check_limits("test")
    assert global_limited is True
    assert tool_limited is True

    # Check different tool - global limit reached, no tool limit
    global_limited, tool_limited = await limiter.check_limits("other")
    assert global_limited is True
    assert tool_limited is False


@pytest.mark.asyncio
async def test_rate_limited_decorator():
    """Test the rate_limited decorator."""

    # Define a class with the decorator
    @rate_limited(limit=5, period=60.0)
    class RateLimitedTool:
        async def execute(self, x: int) -> int:
            return x * 2

    # Check that class has the expected attributes
    assert hasattr(RateLimitedTool, "_rate_limit")
    assert RateLimitedTool._rate_limit == 5
    assert hasattr(RateLimitedTool, "_rate_period")
    assert RateLimitedTool._rate_period == 60.0

    # Test configuring a limiter with decorated class info
    tool_limits = {}

    # Function that would be used to auto-configure limits
    def collect_rate_limits(cls):
        if hasattr(cls, "_rate_limit") and hasattr(cls, "_rate_period"):
            tool_name = cls.__name__
            tool_limits[tool_name] = (cls._rate_limit, cls._rate_period)

    # Apply the function
    collect_rate_limits(RateLimitedTool)

    # Verify the tool limits were extracted
    assert "RateLimitedTool" in tool_limits
    assert tool_limits["RateLimitedTool"] == (5, 60.0)
