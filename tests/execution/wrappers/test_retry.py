# tests/execution/wrappers/test_retry.py
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from chuk_tool_processor.execution.wrappers.retry import (
    RetryConfig,
    RetryableToolExecutor,
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
# --------------------------------------------------------------------------- #
class DummyExecutor:
    """
    Fails the first *fail_times* invocations, then succeeds.
    """

    def __init__(self, fail_times: int, error_message: str = "err") -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.error_message = error_message

    async def execute(
        self, calls: List[ToolCall], timeout: Optional[float] = None
    ) -> List[ToolResult]:
        self.calls += 1
        call = calls[0]
        if self.calls <= self.fail_times:
            return [
                ToolResult(
                    tool=call.tool,
                    result=None,
                    error=self.error_message,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    machine="test",
                    pid=123,
                )
            ]
        return [
            ToolResult(
                tool=call.tool,
                result="success",
                error=None,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                machine="test",
                pid=123,
            )
        ]


# --------------------------------------------------------------------------- #
# RetryConfig unit tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "max_retries, attempt, expect",
    [(0, 0, False), (1, 0, True), (1, 1, False)],
)
def test_retry_config_attempt_limit(max_retries, attempt, expect):
    cfg = RetryConfig(max_retries=max_retries)
    assert cfg.should_retry(attempt) == expect


@pytest.mark.parametrize(
    "substrs, error_str, expect",
    [(["foo"], "msg has foo", True), (["bar"], "no match", False)],
)
def test_retry_config_error_substrings(substrs, error_str, expect):
    cfg = RetryConfig(max_retries=3, retry_on_error_substrings=substrs)
    assert cfg.should_retry(0, error_str=error_str) == expect


def test_retry_config_exceptions():
    class MyErr(Exception):
        ...

    cfg = RetryConfig(max_retries=3, retry_on_exceptions=[MyErr])
    assert cfg.should_retry(0, error=MyErr())
    assert not cfg.should_retry(0, error=ValueError())


def test_retry_config_get_delay_no_jitter():
    cfg = RetryConfig(max_retries=3, base_delay=2.0, max_delay=10.0, jitter=False)
    assert cfg.get_delay(0) == 2.0
    assert cfg.get_delay(1) == 4.0
    assert cfg.get_delay(2) == 8.0
    assert cfg.get_delay(3) == 10.0  # capped at max_delay


# --------------------------------------------------------------------------- #
# RetryableToolExecutor integration tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_retry_executor_succeeds_after_retries():
    dummy = DummyExecutor(fail_times=2)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=3, base_delay=0.1, jitter=False),
    )

    call = ToolCall(tool="t1", arguments={})
    res = (await wrapper.execute([call]))[0]

    assert res.result == "success"
    assert res.attempts >= 1  # at least one retry happened


@pytest.mark.asyncio
async def test_retry_executor_max_retries_exceeded():
    dummy = DummyExecutor(fail_times=5)
    wrapper = RetryableToolExecutor(
        executor=dummy,
        default_config=RetryConfig(max_retries=2, base_delay=0.1, jitter=False),
    )

    res = (await wrapper.execute([ToolCall(tool="t2", arguments={})]))[0]
    assert res.error.startswith("Max retries reached")
    assert res.attempts == 2  # exhausted retries


@pytest.mark.asyncio
async def test_retry_executor_handles_exceptions():
    class ExcExecutor:
        def __init__(self):
            self.calls = 0

        async def execute(self, calls, timeout=None):
            self.calls += 1
            raise RuntimeError("boom")

    exc_exec = ExcExecutor()
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
    assert exc_exec.calls == 2  # one retry
    assert "boom" in res.error
    assert res.attempts == 2
