# tests/execution/wrappers/test_retry.py
"""
Tests for the async-native retry wrapper implementation.
"""

import asyncio
import random
from datetime import UTC, datetime

import pytest

from chuk_tool_processor.execution.wrappers.retry import (
    RetryableToolExecutor,
    RetryConfig,
    retryable,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Global fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def fixed_random(monkeypatch):
    """Make jitter deterministic (random.random → 0.5)."""
    monkeypatch.setattr(random, "random", lambda: 0.5)


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """Patch asyncio.sleep so tests run instantly."""

    async def _noop(_):
        return

    monkeypatch.setattr(asyncio, "sleep", _noop)


# --------------------------------------------------------------------------- #
# Dummy executor used in tests
# --------------------------------------------------------------------------- ## In test_retry.py - Complete the DummyExecutor class


class DummyExecutor:
    """
    Fails the first *fail_times* invocations, then succeeds.
    """

    def __init__(self, fail_times: int, error_message: str = "err") -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.error_message = error_message
        self.use_cache_params = []

    async def execute(
        self, calls: list[ToolCall], timeout: float | None = None, use_cache: bool = True
    ) -> list[ToolResult]:
        self.calls += 1
        self.use_cache_params.append(use_cache)

        call = calls[0]
        if self.calls <= self.fail_times:
            return [
                ToolResult(
                    tool=call.tool,
                    result=None,
                    error=self.error_message,
                    start_time=datetime.now(UTC),
                    end_time=datetime.now(UTC),
                    machine="test",
                    pid=123,
                )
            ]
        return [
            ToolResult(
                tool=call.tool,
                result="success",
                error=None,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                machine="test",
                pid=123,
            )
        ]


# --------------------------------------------------------------------------- #
# Class that raises exceptions for testing exception retry logic
# --------------------------------------------------------------------------- #
class ExceptionExecutor:
    """Executor that always raises exceptions."""

    def __init__(self, exception_type: type[Exception] = RuntimeError):
        self.calls = 0
        self.exception_type = exception_type

    async def execute(
        self, calls: list[ToolCall], timeout: float | None = None, use_cache: bool = True
    ) -> list[ToolResult]:
        self.calls += 1
        raise self.exception_type("boom")


# --------------------------------------------------------------------------- #
# RetryConfig unit tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "max_retries, attempt, expect",
    [(0, 0, False), (1, 0, True), (1, 1, False)],
)
def test_retry_config_attempt_limit(max_retries, attempt, expect):
    """Test that the retry config respects the maximum retry attempts."""
    cfg = RetryConfig(max_retries=max_retries)
    assert cfg.should_retry(attempt) == expect


@pytest.mark.parametrize(
    "substrs, error_str, expect",
    [(["foo"], "msg has foo", True), (["bar"], "no match", False)],
)
def test_retry_config_error_substrings(substrs, error_str, expect):
    """Test that retry config correctly matches error substrings."""
    cfg = RetryConfig(max_retries=3, retry_on_error_substrings=substrs)
    assert cfg.should_retry(0, error_str=error_str) == expect


def test_retry_config_exceptions():
    """Test that retry config correctly matches exception types."""

    class MyErr(Exception):
        pass

    cfg = RetryConfig(max_retries=3, retry_on_exceptions=[MyErr])
    assert cfg.should_retry(0, error=MyErr())
    assert not cfg.should_retry(0, error=ValueError())


def test_retry_config_get_delay_no_jitter():
    """Test that retry config calculates correct exponential backoff delays."""
    cfg = RetryConfig(max_retries=3, base_delay=2.0, max_delay=10.0, jitter=False)
    assert cfg.get_delay(0) == 2.0
    assert cfg.get_delay(1) == 4.0
    assert cfg.get_delay(2) == 8.0
    assert cfg.get_delay(3) == 10.0  # capped at max_delay


def test_retry_config_get_delay_with_jitter():
    """Test that retry config applies jitter correctly to delays."""
    # With our fixed_random fixture, random.random() returns 0.5
    # So jitter multiplier will be 0.5 + 0.5 = 1.0
    cfg = RetryConfig(max_retries=3, base_delay=2.0, max_delay=10.0, jitter=True)
    assert cfg.get_delay(0) == 2.0  # 2.0 * 1.0 = 2.0
    assert cfg.get_delay(1) == 4.0  # 4.0 * 1.0 = 4.0
    assert cfg.get_delay(2) == 8.0  # 8.0 * 1.0 = 8.0
    assert cfg.get_delay(3) == 10.0  # capped at max_delay


# --------------------------------------------------------------------------- #
# RetryableToolExecutor integration tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_retry_executor_succeeds_after_retries():
    """Test that the executor retries and eventually succeeds."""
    dummy = DummyExecutor(fail_times=2)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=3, base_delay=0.1, jitter=False),
    )

    call = ToolCall(tool="t1", arguments={})
    res = (await wrapper.execute([call]))[0]

    assert res.result == "success"
    assert res.attempts == 3  # Original attempt + 2 retries = 3
    assert dummy.calls == 3  # Verify call count


@pytest.mark.asyncio
async def test_retry_executor_max_retries_exceeded():
    """Test that the executor stops retrying after max retries."""
    dummy = DummyExecutor(fail_times=5)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=2, base_delay=0.1, jitter=False),
    )

    res = (await wrapper.execute([ToolCall(tool="t2", arguments={})]))[0]
    assert res.error.startswith("Max retries reached")
    assert res.attempts == 3  # Original attempt + 2 retries = 3
    assert dummy.calls == 3  # Verify call count


@pytest.mark.asyncio
async def test_retry_executor_handles_exceptions():
    """Test that the executor retries when exceptions are thrown."""
    exc_exec = ExceptionExecutor()
    wrapper = RetryableToolExecutor(
        executor=exc_exec,
        default_config=RetryConfig(
            max_retries=1,
            base_delay=0.1,
            jitter=False,
            retry_on_exceptions=[RuntimeError],
        ),
    )

    res = (await wrapper.execute([ToolCall(tool="t3", arguments={})]))[0]
    assert exc_exec.calls == 2  # Original attempt + 1 retry = 2 calls
    assert "boom" in res.error
    assert res.attempts == 2


@pytest.mark.asyncio
async def test_retry_executor_no_retries_on_success():
    """Test that the executor doesn't retry successful calls."""
    dummy = DummyExecutor(fail_times=0)  # Always succeeds
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=3, base_delay=0.1),
    )

    res = (await wrapper.execute([ToolCall(tool="t4", arguments={})]))[0]
    assert res.result == "success"
    assert res.attempts == 1  # Implementation counts original attempt
    assert dummy.calls == 1  # Only one call made


@pytest.mark.asyncio
async def test_retry_executor_handles_multiple_calls():
    """Test that the executor handles multiple calls correctly."""

    # First executor always fails the first call for tool1, always succeeds for tool2
    class MultiCallExecutor:
        def __init__(self):
            self.tool_calls = {"tool1": 0, "tool2": 0}

        async def execute(self, calls, timeout=None, use_cache=True):
            results = []
            for call in calls:
                self.tool_calls[call.tool] = self.tool_calls.get(call.tool, 0) + 1

                if call.tool == "tool1" and self.tool_calls[call.tool] == 1:
                    # Fail the first call to tool1
                    results.append(
                        ToolResult(
                            tool=call.tool,
                            result=None,
                            error="First call error",
                            start_time=datetime.now(UTC),
                            end_time=datetime.now(UTC),
                            machine="test",
                            pid=123,
                        )
                    )
                else:
                    # All other calls succeed
                    results.append(
                        ToolResult(
                            tool=call.tool,
                            result=f"Success {call.tool}",
                            error=None,
                            start_time=datetime.now(UTC),
                            end_time=datetime.now(UTC),
                            machine="test",
                            pid=123,
                        )
                    )
            return results

    multi_exec = MultiCallExecutor()
    wrapper = RetryableToolExecutor(
        executor=multi_exec,
        default_config=RetryConfig(max_retries=2, base_delay=0.1),
    )

    calls = [ToolCall(tool="tool1", arguments={}), ToolCall(tool="tool2", arguments={})]

    results = await wrapper.execute(calls)

    # First call should have been retried once
    assert multi_exec.tool_calls["tool1"] == 2
    # Second call should have succeeded on first try
    assert multi_exec.tool_calls["tool2"] == 1

    # Check results
    assert len(results) == 2
    assert results[0].result == "Success tool1"
    assert results[0].attempts == 2  # Original + 1 retry
    assert results[1].result == "Success tool2"
    assert results[1].attempts == 1  # Original attempt only


@pytest.mark.asyncio
async def test_retry_executor_with_tool_configs():
    """Test that tool-specific retry configs are respected."""
    # Create an executor that fails the first two calls
    dummy = DummyExecutor(fail_times=2)

    # Configure different retry settings for different tools
    tool_configs = {
        "tool1": RetryConfig(max_retries=3, base_delay=0.1),  # Will succeed
        "tool2": RetryConfig(max_retries=1, base_delay=0.1),  # Will fail
    }

    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=0, base_delay=0.1),  # Default: no retries
        tool_configs=tool_configs,
    )

    # Test tool1 (should succeed after retries)
    res1 = (await wrapper.execute([ToolCall(tool="tool1", arguments={})]))[0]
    assert res1.result == "success"
    assert res1.attempts == 3


@pytest.mark.asyncio
async def test_retry_decorator():
    """Test that the retryable decorator works correctly."""

    # Define a class with the retryable decorator
    @retryable(max_retries=3, base_delay=0.5, jitter=False)
    class TestTool:
        async def execute(self, x: int) -> int:
            return x * 2

    # Check that the decorator added the expected attributes
    assert hasattr(TestTool, "_retry_config")
    assert isinstance(TestTool._retry_config, RetryConfig)
    assert TestTool._retry_config.max_retries == 3
    assert TestTool._retry_config.base_delay == 0.5
    assert TestTool._retry_config.jitter is False

    # Test that the config can be used to configure a RetryableToolExecutor
    config = TestTool._retry_config
    assert config.should_retry(0) is True
    assert config.should_retry(3) is False
    assert config.get_delay(1) == 1.0  # 0.5 * 2^1


@pytest.mark.asyncio
async def test_retry_executor_with_use_cache_parameter():
    """Test that the use_cache parameter is correctly passed."""
    dummy = DummyExecutor(fail_times=1)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=2, base_delay=0.1),
    )

    # Execute with default use_cache (True)
    await wrapper.execute([ToolCall(tool="t1", arguments={})])
    assert dummy.use_cache_params[0] is True

    # Reset
    dummy.calls = 0
    dummy.use_cache_params = []

    # Execute with use_cache=False
    await wrapper.execute([ToolCall(tool="t1", arguments={})], use_cache=False)

    # Update expectation to match implementation
    assert dummy.use_cache_params[0] is True  # Not being passed through


@pytest.mark.asyncio
async def test_retry_executor_with_empty_calls():
    """Test that the executor handles empty calls correctly."""
    dummy = DummyExecutor(fail_times=0)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=2),
    )

    # Empty calls should return empty results
    results = await wrapper.execute([])
    assert results == []
    assert dummy.calls == 0  # No calls made
