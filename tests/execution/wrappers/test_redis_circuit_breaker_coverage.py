# tests/execution/wrappers/test_redis_circuit_breaker_coverage.py
"""
Comprehensive tests for redis_circuit_breaker.py using only unittest.mock.

No fakeredis required -- all Redis interactions are mocked via AsyncMock.
Target: push module coverage above 90%.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
    RedisCircuitBreaker,
    RedisCircuitBreakerConfig,
    RedisCircuitBreakerExecutor,
    create_redis_circuit_breaker,
    create_redis_circuit_breaker_executor,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_mock_redis() -> MagicMock:
    """Create a mock Redis client with all needed async methods."""
    r = MagicMock()
    r.eval = AsyncMock(return_value=1)
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# RedisCircuitBreakerConfig
# ---------------------------------------------------------------------------
class TestConfig:
    def test_defaults(self):
        c = RedisCircuitBreakerConfig()
        assert c.failure_threshold == 5
        assert c.success_threshold == 2
        assert c.reset_timeout == 60.0
        assert c.half_open_max_calls == 1
        assert c.failure_window == 60.0

    def test_custom(self):
        c = RedisCircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            reset_timeout=30.0,
            half_open_max_calls=5,
            failure_window=120.0,
        )
        assert c.failure_threshold == 3
        assert c.success_threshold == 1
        assert c.reset_timeout == 30.0
        assert c.half_open_max_calls == 5
        assert c.failure_window == 120.0


# ---------------------------------------------------------------------------
# Constructor / private helpers
# ---------------------------------------------------------------------------
class TestRedisCircuitBreakerInit:
    def test_defaults(self):
        r = _make_mock_redis()
        cb = RedisCircuitBreaker(r)
        assert cb.default_config.failure_threshold == 5
        assert cb.tool_configs == {}
        assert cb._key_prefix == "circuitbreaker"

    def test_custom(self):
        r = _make_mock_redis()
        cfg = RedisCircuitBreakerConfig(failure_threshold=3)
        tc = {"api": RedisCircuitBreakerConfig(failure_threshold=1)}
        cb = RedisCircuitBreaker(r, default_config=cfg, tool_configs=tc, key_prefix="cb")
        assert cb.default_config.failure_threshold == 3
        assert cb.tool_configs == tc
        assert cb._key_prefix == "cb"

    def test_state_key(self):
        cb = RedisCircuitBreaker(_make_mock_redis(), key_prefix="pfx")
        assert cb._state_key("tool") == "pfx:tool:state"

    def test_failures_key(self):
        cb = RedisCircuitBreaker(_make_mock_redis(), key_prefix="pfx")
        assert cb._failures_key("tool") == "pfx:tool:failures"

    def test_get_config_returns_default(self):
        cb = RedisCircuitBreaker(_make_mock_redis())
        cfg = cb._get_config("any_tool")
        assert cfg is cb.default_config

    def test_get_config_returns_tool_specific(self):
        special = RedisCircuitBreakerConfig(failure_threshold=2)
        cb = RedisCircuitBreaker(_make_mock_redis(), tool_configs={"api": special})
        assert cb._get_config("api") is special
        assert cb._get_config("other") is cb.default_config


# ---------------------------------------------------------------------------
# can_execute
# ---------------------------------------------------------------------------
class TestCanExecute:
    @pytest.mark.asyncio
    async def test_returns_true_when_allowed(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=1)
        cb = RedisCircuitBreaker(r)
        result = await cb.can_execute("tool")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_blocked(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=0)
        cb = RedisCircuitBreaker(r)
        result = await cb.can_execute("tool")
        assert result is False

    @pytest.mark.asyncio
    async def test_passes_config_values_to_lua(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=1)
        cfg = RedisCircuitBreakerConfig(reset_timeout=30.0, half_open_max_calls=3)
        cb = RedisCircuitBreaker(r, default_config=cfg, key_prefix="cb")
        await cb.can_execute("mytool")

        call_args = r.eval.call_args[0]
        # Lua script is first arg
        assert isinstance(call_args[0], str)
        # key count
        assert call_args[1] == 1
        # state key
        assert call_args[2] == "cb:mytool:state"
        # ARGV[2] = reset_timeout
        assert call_args[4] == "30.0"
        # ARGV[3] = half_open_max_calls
        assert call_args[5] == "3"

    @pytest.mark.asyncio
    async def test_uses_tool_specific_config(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=1)
        special = RedisCircuitBreakerConfig(reset_timeout=99.0, half_open_max_calls=7)
        cb = RedisCircuitBreaker(r, tool_configs={"special": special})
        await cb.can_execute("special")
        call_args = r.eval.call_args[0]
        assert call_args[4] == "99.0"
        assert call_args[5] == "7"


# ---------------------------------------------------------------------------
# record_success
# ---------------------------------------------------------------------------
class TestRecordSuccess:
    @pytest.mark.asyncio
    async def test_transitions_to_closed(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"closed")
        cb = RedisCircuitBreaker(r)
        await cb.record_success("tool")
        r.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stays_half_open(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"half_open")
        cb = RedisCircuitBreaker(r)
        await cb.record_success("tool")
        r.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_correct_keys_and_args(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"closed")
        cfg = RedisCircuitBreakerConfig(success_threshold=3)
        cb = RedisCircuitBreaker(r, default_config=cfg, key_prefix="cb")
        await cb.record_success("api")
        call_args = r.eval.call_args[0]
        # 2 keys
        assert call_args[1] == 2
        assert call_args[2] == "cb:api:state"
        assert call_args[3] == "cb:api:failures"
        assert call_args[4] == "3"  # success_threshold

    @pytest.mark.asyncio
    async def test_non_closed_result_no_log(self):
        """When result is not b'closed', the info log should not fire."""
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"half_open")
        cb = RedisCircuitBreaker(r)
        # Should not raise
        await cb.record_success("tool")


# ---------------------------------------------------------------------------
# record_failure
# ---------------------------------------------------------------------------
class TestRecordFailure:
    @pytest.mark.asyncio
    async def test_transitions_to_open(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"open")
        cb = RedisCircuitBreaker(r)
        await cb.record_failure("tool")
        r.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stays_closed(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"closed")
        cb = RedisCircuitBreaker(r)
        await cb.record_failure("tool")
        r.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_correct_keys_and_args(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"closed")
        cfg = RedisCircuitBreakerConfig(failure_window=90.0, failure_threshold=7)
        cb = RedisCircuitBreaker(r, default_config=cfg, key_prefix="cb")
        await cb.record_failure("api")
        call_args = r.eval.call_args[0]
        assert call_args[1] == 2  # 2 keys
        assert call_args[2] == "cb:api:state"
        assert call_args[3] == "cb:api:failures"
        # ARGV[2] = failure_window
        assert call_args[5] == "90.0"
        # ARGV[3] = failure_threshold
        assert call_args[6] == "7"

    @pytest.mark.asyncio
    async def test_non_open_result_no_warning_log(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=b"closed")
        cb = RedisCircuitBreaker(r)
        await cb.record_failure("tool")
        # No exception expected


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------
class TestGetState:
    @pytest.mark.asyncio
    async def test_empty_redis_data(self):
        r = _make_mock_redis()
        r.hgetall = AsyncMock(return_value={})
        cb = RedisCircuitBreaker(r)
        state = await cb.get_state("tool")
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0
        assert state["opened_at"] is None
        assert state["half_open_calls"] == 0
        assert state["time_until_half_open"] is None

    @pytest.mark.asyncio
    async def test_all_fields_populated(self):
        r = _make_mock_redis()
        now = time.time()
        r.hgetall = AsyncMock(
            return_value={
                b"state": b"open",
                b"failure_count": b"5",
                b"success_count": b"2",
                b"opened_at": str(now).encode(),
                b"half_open_calls": b"3",
            }
        )
        cfg = RedisCircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            reset_timeout=60.0,
            half_open_max_calls=1,
        )
        cb = RedisCircuitBreaker(r, default_config=cfg)
        state = await cb.get_state("tool")
        assert state["state"] == "open"
        assert state["failure_count"] == 5
        assert state["success_count"] == 2
        assert state["opened_at"] == pytest.approx(now, abs=1)
        assert state["half_open_calls"] == 3
        assert state["time_until_half_open"] is not None
        assert state["time_until_half_open"] > 0
        assert state["config"]["failure_threshold"] == 5

    @pytest.mark.asyncio
    async def test_time_until_half_open_expired(self):
        r = _make_mock_redis()
        r.hgetall = AsyncMock(
            return_value={
                b"state": b"open",
                b"failure_count": b"5",
                b"success_count": b"0",
                b"opened_at": b"1000000000.0",
                b"half_open_calls": b"0",
            }
        )
        cfg = RedisCircuitBreakerConfig(reset_timeout=60.0)
        cb = RedisCircuitBreaker(r, default_config=cfg)
        state = await cb.get_state("tool")
        assert state["time_until_half_open"] is None

    @pytest.mark.asyncio
    async def test_closed_state_no_time_until_half_open(self):
        r = _make_mock_redis()
        r.hgetall = AsyncMock(
            return_value={
                b"state": b"closed",
                b"opened_at": b"0",
            }
        )
        cb = RedisCircuitBreaker(r)
        state = await cb.get_state("tool")
        assert state["time_until_half_open"] is None

    @pytest.mark.asyncio
    async def test_config_in_state_output(self):
        cfg = RedisCircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=4,
            reset_timeout=120.0,
            half_open_max_calls=3,
        )
        r = _make_mock_redis()
        r.hgetall = AsyncMock(return_value={})
        cb = RedisCircuitBreaker(r, default_config=cfg)
        state = await cb.get_state("tool")
        assert state["config"]["failure_threshold"] == 10
        assert state["config"]["success_threshold"] == 4
        assert state["config"]["reset_timeout"] == 120.0
        assert state["config"]["half_open_max_calls"] == 3


# ---------------------------------------------------------------------------
# get_all_states
# ---------------------------------------------------------------------------
class TestGetAllStates:
    @pytest.mark.asyncio
    async def test_empty(self):
        r = _make_mock_redis()

        async def scan_iter_empty(pattern):
            return
            yield  # noqa  -- make it an async generator

        r.scan_iter = scan_iter_empty
        cb = RedisCircuitBreaker(r)
        states = await cb.get_all_states()
        assert states == {}

    @pytest.mark.asyncio
    async def test_multiple_tools(self):
        r = _make_mock_redis()

        async def scan_iter_mock(pattern):
            yield b"circuitbreaker:tool1:state"
            yield b"circuitbreaker:tool2:state"

        r.scan_iter = scan_iter_mock
        r.hgetall = AsyncMock(return_value={b"state": b"closed"})
        cb = RedisCircuitBreaker(r)
        states = await cb.get_all_states()
        assert "tool1" in states
        assert "tool2" in states

    @pytest.mark.asyncio
    async def test_string_keys(self):
        r = _make_mock_redis()

        async def scan_iter_mock(pattern):
            yield "circuitbreaker:tool1:state"

        r.scan_iter = scan_iter_mock
        r.hgetall = AsyncMock(return_value={b"state": b"closed"})
        cb = RedisCircuitBreaker(r)
        states = await cb.get_all_states()
        assert "tool1" in states

    @pytest.mark.asyncio
    async def test_skips_short_keys(self):
        r = _make_mock_redis()

        async def scan_iter_mock(pattern):
            yield b"cb"  # too short, < 3 parts
            yield b"x:y"  # only 2 parts
            yield b"circuitbreaker:valid:state"

        r.scan_iter = scan_iter_mock
        r.hgetall = AsyncMock(return_value={b"state": b"closed"})
        cb = RedisCircuitBreaker(r)
        states = await cb.get_all_states()
        assert "valid" in states
        assert len(states) == 1


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------
class TestReset:
    @pytest.mark.asyncio
    async def test_deletes_state_and_failures_keys(self):
        r = _make_mock_redis()
        cb = RedisCircuitBreaker(r, key_prefix="cb")
        await cb.reset("tool")
        r.delete.assert_awaited_once_with("cb:tool:state", "cb:tool:failures")


# ---------------------------------------------------------------------------
# reset_all
# ---------------------------------------------------------------------------
class TestResetAll:
    @pytest.mark.asyncio
    async def test_deletes_all_matching_keys(self):
        r = _make_mock_redis()

        async def scan_iter_mock(pattern):
            yield b"circuitbreaker:t1:state"
            yield b"circuitbreaker:t1:failures"
            yield b"circuitbreaker:t2:state"

        r.scan_iter = scan_iter_mock
        cb = RedisCircuitBreaker(r)
        count = await cb.reset_all()
        assert count == 3
        assert r.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_keys(self):
        r = _make_mock_redis()

        async def scan_iter_empty(pattern):
            return
            yield  # noqa

        r.scan_iter = scan_iter_empty
        cb = RedisCircuitBreaker(r)
        count = await cb.reset_all()
        assert count == 0


# ---------------------------------------------------------------------------
# RedisCircuitBreakerExecutor
# ---------------------------------------------------------------------------
def _make_tool_result(tool: str, error: str | None = None) -> ToolResult:
    now = datetime.now(UTC)
    return ToolResult(
        tool=tool,
        result=None if error else {"ok": True},
        error=error,
        start_time=now,
        end_time=now,
        machine="test",
        pid=0,
    )


class TestExecutorInit:
    def test_stores_executor_and_breaker(self):
        mock_exec = MagicMock()
        mock_cb = MagicMock()
        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        assert ex.executor is mock_exec
        assert ex.circuit_breaker is mock_cb


class TestExecutorExecute:
    @pytest.mark.asyncio
    async def test_empty_calls(self):
        ex = RedisCircuitBreakerExecutor(MagicMock(), MagicMock())
        result = await ex.execute([])
        assert result == []

    @pytest.mark.asyncio
    async def test_circuit_open_rejects(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=False)
        mock_cb.get_state = AsyncMock(
            return_value={
                "state": "open",
                "failure_count": 5,
                "time_until_half_open": 30.0,
            }
        )
        mock_exec = MagicMock()
        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)

        call = ToolCall(tool="blocked_tool", arguments={})
        results = await ex.execute([call])

        assert len(results) == 1
        assert results[0].error is not None
        assert "circuit breaker" in results[0].error.lower()
        assert results[0].machine == "redis_circuit_breaker"
        assert results[0].error_info is not None
        mock_exec.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_open_no_time_until_half_open(self):
        """time_until_half_open can be None."""
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=False)
        mock_cb.get_state = AsyncMock(
            return_value={
                "state": "open",
                "failure_count": 3,
                "time_until_half_open": None,
            }
        )
        ex = RedisCircuitBreakerExecutor(MagicMock(), mock_cb)
        call = ToolCall(tool="tool", arguments={})
        results = await ex.execute([call])
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_success_records_success(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()
        mock_cb.record_failure = AsyncMock()

        result = _make_tool_result("tool")
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        results = await ex.execute([call])

        assert len(results) == 1
        assert results[0].error is None
        mock_cb.record_success.assert_awaited_once_with("tool")
        mock_cb.record_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_result_records_failure(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()
        mock_cb.record_failure = AsyncMock()

        result = _make_tool_result("tool", error="boom")
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        results = await ex.execute([call])

        assert len(results) == 1
        mock_cb.record_failure.assert_awaited_once_with("tool")
        mock_cb.record_success.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_records_failure_and_returns_error(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_failure = AsyncMock()

        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(side_effect=RuntimeError("kaboom"))

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        results = await ex.execute([call])

        assert len(results) == 1
        assert results[0].error is not None
        assert "kaboom" in results[0].error
        mock_cb.record_failure.assert_awaited_once_with("tool")

    @pytest.mark.asyncio
    async def test_passes_timeout(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()

        result = _make_tool_result("tool")
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        await ex.execute([call], timeout=42.0)

        kwargs = mock_exec.execute.call_args[1]
        assert kwargs["timeout"] == 42.0

    @pytest.mark.asyncio
    async def test_passes_use_cache_when_executor_has_attribute(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()

        result = _make_tool_result("tool")
        mock_exec = MagicMock()
        mock_exec.use_cache = True
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        await ex.execute([call], use_cache=False)

        kwargs = mock_exec.execute.call_args[1]
        assert kwargs["use_cache"] is False

    @pytest.mark.asyncio
    async def test_does_not_pass_use_cache_when_executor_lacks_attribute(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()

        result = _make_tool_result("tool")
        mock_exec = MagicMock(spec=[])  # no use_cache attribute
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        call = ToolCall(tool="tool", arguments={})
        await ex.execute([call], use_cache=False)

        kwargs = mock_exec.execute.call_args[1]
        assert "use_cache" not in kwargs

    @pytest.mark.asyncio
    async def test_mixed_calls_some_open_some_closed(self):
        mock_cb = MagicMock()

        async def can_execute_side(tool):
            return tool != "blocked"

        mock_cb.can_execute = AsyncMock(side_effect=can_execute_side)
        mock_cb.get_state = AsyncMock(
            return_value={
                "state": "open",
                "failure_count": 5,
                "time_until_half_open": 10.0,
            }
        )
        mock_cb.record_success = AsyncMock()

        result = _make_tool_result("allowed")
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=[result])

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        calls = [
            ToolCall(tool="blocked", arguments={}),
            ToolCall(tool="allowed", arguments={}),
        ]
        results = await ex.execute(calls)
        assert len(results) == 2
        assert results[0].error is not None
        assert "circuit breaker" in results[0].error.lower()
        assert results[1].error is None

    @pytest.mark.asyncio
    async def test_multiple_successful_calls(self):
        mock_cb = MagicMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()

        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(
            side_effect=[
                [_make_tool_result("t1")],
                [_make_tool_result("t2")],
            ]
        )

        ex = RedisCircuitBreakerExecutor(mock_exec, mock_cb)
        calls = [
            ToolCall(tool="t1", arguments={}),
            ToolCall(tool="t2", arguments={}),
        ]
        results = await ex.execute(calls)
        assert len(results) == 2
        assert mock_cb.record_success.call_count == 2


# ---------------------------------------------------------------------------
# Executor helper methods
# ---------------------------------------------------------------------------
class TestExecutorHelpers:
    @pytest.mark.asyncio
    async def test_get_circuit_states(self):
        mock_cb = MagicMock()
        mock_cb.get_all_states = AsyncMock(return_value={"t1": {"state": "open"}})
        ex = RedisCircuitBreakerExecutor(MagicMock(), mock_cb)
        states = await ex.get_circuit_states()
        assert states == {"t1": {"state": "open"}}

    @pytest.mark.asyncio
    async def test_reset_circuit(self):
        mock_cb = MagicMock()
        mock_cb.reset = AsyncMock()
        ex = RedisCircuitBreakerExecutor(MagicMock(), mock_cb)
        await ex.reset_circuit("tool")
        mock_cb.reset.assert_awaited_once_with("tool")


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------
class TestCreateRedisCircuitBreaker:
    @pytest.mark.asyncio
    async def test_creates_with_defaults(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
        ):
            cb = await create_redis_circuit_breaker()

        assert isinstance(cb, RedisCircuitBreaker)
        assert cb.default_config.failure_threshold == 5

    @pytest.mark.asyncio
    async def test_creates_with_custom_config(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
        ):
            cfg = RedisCircuitBreakerConfig(failure_threshold=3)
            tc = {"api": RedisCircuitBreakerConfig(failure_threshold=1)}
            cb = await create_redis_circuit_breaker(
                redis_url="redis://myhost:6380/2",
                default_config=cfg,
                tool_configs=tc,
                key_prefix="custom",
            )

        assert cb.default_config.failure_threshold == 3
        assert "api" in cb.tool_configs
        assert cb._key_prefix == "custom"
        mock_redis_cls.from_url.assert_called_once_with("redis://myhost:6380/2", decode_responses=False)


class TestCreateRedisCircuitBreakerExecutor:
    @pytest.mark.asyncio
    async def test_creates_executor_wrapper(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
        ):
            mock_exec = MagicMock()
            result = await create_redis_circuit_breaker_executor(
                mock_exec,
                redis_url="redis://localhost:6379/0",
                default_config=RedisCircuitBreakerConfig(failure_threshold=3),
                tool_configs={"api": RedisCircuitBreakerConfig(failure_threshold=1)},
                key_prefix="test",
            )

        assert isinstance(result, RedisCircuitBreakerExecutor)
        assert result.executor is mock_exec
        assert isinstance(result.circuit_breaker, RedisCircuitBreaker)


# ---------------------------------------------------------------------------
# State transitions (full flow with mocks)
# ---------------------------------------------------------------------------
class TestStateTransitions:
    @pytest.mark.asyncio
    async def test_closed_to_open_via_failures(self):
        r = _make_mock_redis()
        # record_failure returns "closed" twice, then "open"
        r.eval = AsyncMock(side_effect=[b"closed", b"closed", b"open"])
        cb = RedisCircuitBreaker(
            r,
            default_config=RedisCircuitBreakerConfig(failure_threshold=3),
        )
        await cb.record_failure("tool")
        await cb.record_failure("tool")
        await cb.record_failure("tool")
        assert r.eval.call_count == 3

    @pytest.mark.asyncio
    async def test_half_open_success_to_closed(self):
        r = _make_mock_redis()
        # can_execute returns 1 (allowed in half_open)
        # record_success returns b"closed"
        r.eval = AsyncMock(side_effect=[1, b"closed"])
        cb = RedisCircuitBreaker(r)
        can = await cb.can_execute("tool")
        assert can is True
        await cb.record_success("tool")

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[1, b"open"])
        cb = RedisCircuitBreaker(r)
        can = await cb.can_execute("tool")
        assert can is True
        await cb.record_failure("tool")
        # last eval returned b"open"
        assert r.eval.call_count == 2
