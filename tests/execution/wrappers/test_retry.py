import pytest
import asyncio
import random
from datetime import datetime, timezone
from chuk_tool_processor.execution.wrappers.retry import RetryConfig, RetryableToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# Ensure deterministic jitter
@pytest.fixture(autouse=True)
def fixed_random(monkeypatch):
    monkeypatch.setattr(random, 'random', lambda: 0.5)

# Monkeypatch asyncio.sleep to avoid real delays
@pytest.fixture(autouse=True)
def dummy_sleep(monkeypatch):
    async def sleep(duration):
        # no-op
        return
    monkeypatch.setattr(asyncio, 'sleep', sleep)

class DummyExecutor:
    """
    Simulate an executor that fails first N times then succeeds.
    """
    def __init__(self, fail_times, error_message="err"):
        self.fail_times = fail_times
        self.called = 0
        self.error_message = error_message

    async def execute(self, calls, timeout=None):
        # Always single call for simplicity
        self.called += 1
        call = calls[0]
        if self.called <= self.fail_times:
            # return a ToolResult with error
            return [ToolResult(
                tool=call.tool,
                result=None,
                error=self.error_message,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                machine="test",
                pid=123
            )]
        else:
            # succeed
            return [ToolResult(
                tool=call.tool,
                result="success",
                error=None,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                machine="test",
                pid=123
            )]

@pytest.mark.parametrize("max_retries,attempt,expect", [
    (0, 0, False),
    (1, 0, True),
    (1, 1, False),
])
def test_retry_config_attempt_limit(max_retries, attempt, expect):
    cfg = RetryConfig(max_retries=max_retries)
    assert cfg.should_retry(attempt) == expect

@pytest.mark.parametrize("substrs,error_str,expect", [
    (["foo"], "this has foo", True),
    (["bar"], "no match", False),
])
def test_retry_config_error_substrings(substrs, error_str, expect):
    cfg = RetryConfig(max_retries=3, retry_on_error_substrings=substrs)
    assert cfg.should_retry(0, error_str=error_str) == expect

def test_retry_config_exceptions():
    class MyErr(Exception): pass
    cfg = RetryConfig(max_retries=3, retry_on_exceptions=[MyErr])
    assert cfg.should_retry(0, error=MyErr())
    assert not cfg.should_retry(0, error=ValueError())

def test_retry_config_get_delay_no_jitter():
    cfg = RetryConfig(max_retries=3, base_delay=2.0, max_delay=10.0, jitter=False)
    # delays: attempt=0->2,1->4,2->8,3->10 (capped)
    assert cfg.get_delay(0) == 2.0
    assert cfg.get_delay(1) == 4.0
    assert cfg.get_delay(2) == 8.0
    assert cfg.get_delay(3) == 10.0

@pytest.mark.asyncio
async def test_retryable_tool_executor_succeeds_after_retries():
    # fail twice, succeed on third
    dummy = DummyExecutor(fail_times=2)
    wrapper = RetryableToolExecutor(executor=dummy, default_config=RetryConfig(max_retries=3, base_delay=0.1, jitter=False))
    call = ToolCall(tool="t1", arguments={})
    results = await wrapper.execute([call])
    assert results[0].result == "success"
    # attempts count on final result should be >=1
    assert hasattr(results[0], 'attempts') and results[0].attempts >= 1

@pytest.mark.asyncio
async def test_retryable_tool_executor_max_retries_exceeded():
    # always fail
    dummy = DummyExecutor(fail_times=5)
    wrapper = RetryableToolExecutor(executor=dummy, default_config=RetryConfig(max_retries=2, base_delay=0.1, jitter=False))
    call = ToolCall(tool="t2", arguments={})
    results = await wrapper.execute([call])
    res = results[0]
    assert res.error.startswith("Max retries reached")
    assert res.attempts == 2

@pytest.mark.asyncio
async def test_retryable_with_exception_raised():
    class ExcExecutor:
        def __init__(self): self.called = 0
        async def execute(self, calls, timeout=None):
            self.called += 1
            raise RuntimeError("boom")
    exc_exec = ExcExecutor()
    wrapper = RetryableToolExecutor(executor=exc_exec, default_config=RetryConfig(max_retries=1, base_delay=0.1, jitter=False, retry_on_exceptions=[RuntimeError]))
    call = ToolCall(tool="t3", arguments={})
    results = await wrapper.execute([call])
    res = results[0]
    # should retry once then return error
    assert exc_exec.called == 2
    assert "boom" in res.error
    assert res.attempts == 2
