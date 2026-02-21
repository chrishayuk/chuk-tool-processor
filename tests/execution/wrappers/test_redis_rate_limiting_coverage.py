# tests/execution/wrappers/test_redis_rate_limiting_coverage.py
"""
Comprehensive tests for redis_rate_limiting.py using only unittest.mock.

No fakeredis required -- all Redis interactions are mocked via AsyncMock.
Target: push module coverage above 90%.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
    RedisRateLimiter,
    create_redis_rate_limiter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_mock_redis() -> MagicMock:
    """Create a mock Redis client with all needed async methods."""
    r = MagicMock()
    r.eval = AsyncMock(return_value=-1)
    r.zremrangebyscore = AsyncMock()
    r.zcard = AsyncMock(return_value=0)
    r.delete = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# Constructor / attributes
# ---------------------------------------------------------------------------
class TestRedisRateLimiterInit:
    def test_defaults(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r)
        assert limiter.global_limit is None
        assert limiter.global_period == 60.0
        assert limiter.tool_limits == {}
        assert limiter._key_prefix == "ratelimit"
        assert limiter._request_counter == 0

    def test_custom_values(self):
        r = _make_mock_redis()
        tl = {"api": (10, 30.0)}
        limiter = RedisRateLimiter(
            r,
            global_limit=50,
            global_period=120.0,
            tool_limits=tl,
            key_prefix="myapp",
        )
        assert limiter.global_limit == 50
        assert limiter.global_period == 120.0
        assert limiter.tool_limits == tl
        assert limiter._key_prefix == "myapp"

    def test_none_tool_limits_becomes_empty_dict(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, tool_limits=None)
        assert limiter.tool_limits == {}


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------
class TestKeyHelpers:
    def test_global_key(self):
        limiter = RedisRateLimiter(_make_mock_redis(), key_prefix="pfx")
        assert limiter._global_key() == "pfx:global"

    def test_tool_key(self):
        limiter = RedisRateLimiter(_make_mock_redis(), key_prefix="pfx")
        assert limiter._tool_key("search") == "pfx:tool:search"

    def test_generate_request_id_unique(self):
        limiter = RedisRateLimiter(_make_mock_redis())
        ids = {limiter._generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # all unique

    def test_generate_request_id_increments_counter(self):
        limiter = RedisRateLimiter(_make_mock_redis())
        limiter._generate_request_id()
        assert limiter._request_counter == 1
        limiter._generate_request_id()
        assert limiter._request_counter == 2


# ---------------------------------------------------------------------------
# _acquire_slot
# ---------------------------------------------------------------------------
class TestAcquireSlot:
    @pytest.mark.asyncio
    async def test_returns_none_on_success(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=10)
        result = await limiter._acquire_slot("key", 10, 60.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_float_wait_time_when_limited(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=42.5)
        limiter = RedisRateLimiter(r, global_limit=10)
        result = await limiter._acquire_slot("key", 10, 60.0)
        assert result == 42.5
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_returns_zero_wait_time(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=0)
        limiter = RedisRateLimiter(r, global_limit=10)
        result = await limiter._acquire_slot("key", 10, 60.0)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_passes_correct_args_to_eval(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=10, key_prefix="pfx")
        await limiter._acquire_slot("pfx:global", 10, 60.0)

        call_args = r.eval.call_args
        # First positional arg is the Lua script (string)
        assert isinstance(call_args[0][0], str)
        # Second arg is number of keys (1)
        assert call_args[0][1] == 1
        # Third arg is the key
        assert call_args[0][2] == "pfx:global"


# ---------------------------------------------------------------------------
# _acquire_global
# ---------------------------------------------------------------------------
class TestAcquireGlobal:
    @pytest.mark.asyncio
    async def test_returns_immediately_when_no_limit(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, global_limit=None)
        await limiter._acquire_global()
        r.eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_acquires_on_first_try(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=10, global_period=60.0)
        await limiter._acquire_global()
        assert r.eval.call_count == 1

    @pytest.mark.asyncio
    async def test_loops_until_slot_available(self):
        r = _make_mock_redis()
        # First call: wait 0.01s, second call: success
        r.eval = AsyncMock(side_effect=[0.01, -1])
        limiter = RedisRateLimiter(r, global_limit=10, global_period=60.0)
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter._acquire_global()
        assert r.eval.call_count == 2
        mock_sleep.assert_called_once()
        # sleep called with max(0.01, 0.01)
        assert mock_sleep.call_args[0][0] >= 0.01

    @pytest.mark.asyncio
    async def test_loops_multiple_times(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[0.02, 0.03, -1])
        limiter = RedisRateLimiter(r, global_limit=1, global_period=60.0)
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock):
            await limiter._acquire_global()
        assert r.eval.call_count == 3


# ---------------------------------------------------------------------------
# _acquire_tool
# ---------------------------------------------------------------------------
class TestAcquireTool:
    @pytest.mark.asyncio
    async def test_returns_immediately_when_tool_not_in_limits(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, tool_limits={})
        await limiter._acquire_tool("unknown")
        r.eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_acquires_on_first_try(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, tool_limits={"api": (5, 30.0)})
        await limiter._acquire_tool("api")
        assert r.eval.call_count == 1

    @pytest.mark.asyncio
    async def test_loops_until_slot_available(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[0.05, -1])
        limiter = RedisRateLimiter(r, tool_limits={"api": (1, 60.0)})
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter._acquire_tool("api")
        assert r.eval.call_count == 2
        mock_sleep.assert_called_once()


# ---------------------------------------------------------------------------
# wait (combines global + tool)
# ---------------------------------------------------------------------------
class TestWait:
    @pytest.mark.asyncio
    async def test_calls_both_acquire_methods(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            tool_limits={"tool_a": (10, 60.0)},
        )
        with (
            patch.object(limiter, "_acquire_global", new_callable=AsyncMock) as mg,
            patch.object(limiter, "_acquire_tool", new_callable=AsyncMock) as mt,
        ):
            await limiter.wait("tool_a")
        mg.assert_awaited_once()
        mt.assert_awaited_once_with("tool_a")

    @pytest.mark.asyncio
    async def test_no_global_limit_still_checks_tool(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={"x": (2, 10.0)})
        await limiter.wait("x")
        # eval called once for tool acquire
        assert r.eval.call_count == 1

    @pytest.mark.asyncio
    async def test_no_limits_at_all(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={})
        await limiter.wait("anything")
        r.eval.assert_not_called()


# ---------------------------------------------------------------------------
# _async_sleep
# ---------------------------------------------------------------------------
class TestAsyncSleep:
    @pytest.mark.asyncio
    async def test_delegates_to_asyncio_sleep(self):
        limiter = RedisRateLimiter(_make_mock_redis())
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter._async_sleep(1.5)
        mock_sleep.assert_awaited_once_with(1.5)


# ---------------------------------------------------------------------------
# check_limits
# ---------------------------------------------------------------------------
class TestCheckLimits:
    @pytest.mark.asyncio
    async def test_no_limits_set(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={})
        gl, tl = await limiter.check_limits("tool")
        assert gl is False
        assert tl is False

    @pytest.mark.asyncio
    async def test_global_not_limited(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=5)
        limiter = RedisRateLimiter(r, global_limit=100)
        gl, tl = await limiter.check_limits("tool")
        assert gl is False
        assert tl is False

    @pytest.mark.asyncio
    async def test_global_limited(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=100)
        limiter = RedisRateLimiter(r, global_limit=100)
        gl, tl = await limiter.check_limits("tool")
        assert gl is True
        assert tl is False

    @pytest.mark.asyncio
    async def test_tool_limited(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=10)
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={"api": (10, 60.0)})
        gl, tl = await limiter.check_limits("api")
        assert gl is False
        assert tl is True

    @pytest.mark.asyncio
    async def test_tool_not_limited_when_below_threshold(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=3)
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={"api": (10, 60.0)})
        gl, tl = await limiter.check_limits("api")
        assert gl is False
        assert tl is False

    @pytest.mark.asyncio
    async def test_both_limited(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=50)
        limiter = RedisRateLimiter(
            r,
            global_limit=50,
            tool_limits={"api": (50, 60.0)},
        )
        gl, tl = await limiter.check_limits("api")
        assert gl is True
        assert tl is True

    @pytest.mark.asyncio
    async def test_calls_zremrangebyscore_for_cleanup(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=0)
        limiter = RedisRateLimiter(
            r,
            global_limit=10,
            global_period=60.0,
            tool_limits={"api": (5, 30.0)},
        )
        await limiter.check_limits("api")
        # Called once for global, once for tool
        assert r.zremrangebyscore.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_not_in_limits_skips_tool_check(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=0)
        limiter = RedisRateLimiter(r, global_limit=10, tool_limits={"other": (5, 30.0)})
        gl, tl = await limiter.check_limits("unknown_tool")
        assert tl is False
        # zremrangebyscore called only once (for global)
        assert r.zremrangebyscore.call_count == 1


# ---------------------------------------------------------------------------
# get_usage
# ---------------------------------------------------------------------------
class TestGetUsage:
    @pytest.mark.asyncio
    async def test_no_global_limit(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, global_limit=None)
        usage = await limiter.get_usage()
        assert "global" not in usage

    @pytest.mark.asyncio
    async def test_global_usage_info(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=30)
        limiter = RedisRateLimiter(r, global_limit=100, global_period=60.0)
        usage = await limiter.get_usage()
        assert usage["global"]["used"] == 30
        assert usage["global"]["limit"] == 100
        assert usage["global"]["period"] == 60.0
        assert usage["global"]["remaining"] == 70

    @pytest.mark.asyncio
    async def test_global_remaining_never_negative(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=200)
        limiter = RedisRateLimiter(r, global_limit=100)
        usage = await limiter.get_usage()
        assert usage["global"]["remaining"] == 0

    @pytest.mark.asyncio
    async def test_tool_usage_info(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=3)
        limiter = RedisRateLimiter(
            r,
            global_limit=None,
            tool_limits={"api": (10, 30.0)},
        )
        usage = await limiter.get_usage("api")
        assert "api" in usage
        assert usage["api"]["used"] == 3
        assert usage["api"]["limit"] == 10
        assert usage["api"]["period"] == 30.0
        assert usage["api"]["remaining"] == 7

    @pytest.mark.asyncio
    async def test_tool_remaining_never_negative(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=50)
        limiter = RedisRateLimiter(r, global_limit=None, tool_limits={"x": (10, 60.0)})
        usage = await limiter.get_usage("x")
        assert usage["x"]["remaining"] == 0

    @pytest.mark.asyncio
    async def test_tool_not_in_limits_excluded(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=0)
        limiter = RedisRateLimiter(r, global_limit=10, tool_limits={"known": (5, 60.0)})
        usage = await limiter.get_usage("unknown")
        assert "unknown" not in usage
        assert "global" in usage

    @pytest.mark.asyncio
    async def test_no_tool_argument(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=5)
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            tool_limits={"api": (10, 60.0)},
        )
        usage = await limiter.get_usage(None)
        assert "global" in usage
        # tool not included when tool=None
        assert "api" not in usage

    @pytest.mark.asyncio
    async def test_both_global_and_tool(self):
        r = _make_mock_redis()
        r.zcard = AsyncMock(return_value=7)
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            global_period=60.0,
            tool_limits={"api": (20, 30.0)},
        )
        usage = await limiter.get_usage("api")
        assert "global" in usage
        assert "api" in usage


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------
class TestReset:
    @pytest.mark.asyncio
    async def test_reset_all(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            tool_limits={"t1": (5, 60.0), "t2": (10, 60.0)},
            key_prefix="rl",
        )
        await limiter.reset(None)
        # Should delete global + 2 tool keys = 3 calls
        assert r.delete.call_count == 3
        # Verify keys
        calls = [c[0][0] for c in r.delete.call_args_list]
        assert "rl:global" in calls
        assert "rl:tool:t1" in calls
        assert "rl:tool:t2" in calls

    @pytest.mark.asyncio
    async def test_reset_specific_tool(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            tool_limits={"api": (10, 60.0)},
            key_prefix="rl",
        )
        await limiter.reset("api")
        r.delete.assert_called_once_with("rl:tool:api")

    @pytest.mark.asyncio
    async def test_reset_unknown_tool_no_op(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(
            r,
            global_limit=100,
            tool_limits={"api": (10, 60.0)},
        )
        await limiter.reset("nonexistent")
        r.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_all_empty_tool_limits(self):
        r = _make_mock_redis()
        limiter = RedisRateLimiter(r, global_limit=100, tool_limits={}, key_prefix="rl")
        await limiter.reset(None)
        # Only global key deleted
        r.delete.assert_called_once_with("rl:global")


# ---------------------------------------------------------------------------
# create_redis_rate_limiter factory function
# ---------------------------------------------------------------------------
class TestCreateRedisRateLimiter:
    @pytest.mark.asyncio
    async def test_creates_limiter_with_defaults(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.Redis",
                mock_redis_cls,
                create=True,
            ),
            patch.dict(
                "sys.modules",
                {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
            ),
        ):
            limiter = await create_redis_rate_limiter()

        assert isinstance(limiter, RedisRateLimiter)
        assert limiter.global_limit is None
        assert limiter.global_period == 60.0

    @pytest.mark.asyncio
    async def test_creates_limiter_with_custom_args(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
        ):
            limiter = await create_redis_rate_limiter(
                redis_url="redis://myhost:6379/1",
                global_limit=200,
                global_period=120.0,
                tool_limits={"api": (10, 30.0)},
                key_prefix="custom",
            )

        assert limiter.global_limit == 200
        assert limiter.global_period == 120.0
        assert limiter.tool_limits == {"api": (10, 30.0)}
        assert limiter._key_prefix == "custom"
        mock_redis_cls.from_url.assert_called_once_with("redis://myhost:6379/1", decode_responses=False)

    @pytest.mark.asyncio
    async def test_from_url_called_with_decode_responses_false(self):
        mock_redis_client = _make_mock_redis()
        mock_redis_cls = MagicMock()
        mock_redis_cls.from_url = MagicMock(return_value=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {"redis": MagicMock(), "redis.asyncio": MagicMock(Redis=mock_redis_cls)},
        ):
            await create_redis_rate_limiter(redis_url="redis://localhost:6379/0")

        mock_redis_cls.from_url.assert_called_once_with("redis://localhost:6379/0", decode_responses=False)


# ---------------------------------------------------------------------------
# Edge cases / integration-level
# ---------------------------------------------------------------------------
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_sliding_window_acquire_returns_negative_one_as_success(self):
        """Lua script returns -1 for success, verify we treat it correctly."""
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=10)
        result = await limiter._acquire_slot("k", 10, 60.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_wait_calls(self):
        """Multiple concurrent waits should all complete."""
        r = _make_mock_redis()
        r.eval = AsyncMock(return_value=-1)
        limiter = RedisRateLimiter(r, global_limit=100, tool_limits={"t": (50, 60.0)})
        tasks = [limiter.wait("t") for _ in range(10)]
        await asyncio.gather(*tasks)
        # 10 waits: each calls _acquire_global and _acquire_tool => 20 eval calls
        assert r.eval.call_count == 20

    @pytest.mark.asyncio
    async def test_wait_global_blocked_then_succeeds(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[0.001, -1])
        limiter = RedisRateLimiter(r, global_limit=1, global_period=60.0)
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock):
            await limiter._acquire_global()
        assert r.eval.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_tool_blocked_then_succeeds(self):
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[0.001, -1])
        limiter = RedisRateLimiter(r, tool_limits={"t": (1, 60.0)})
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock):
            await limiter._acquire_tool("t")
        assert r.eval.call_count == 2

    @pytest.mark.asyncio
    async def test_sleep_uses_max_of_001_and_wait_time(self):
        """When wait_time < 0.01, we should sleep for 0.01."""
        r = _make_mock_redis()
        r.eval = AsyncMock(side_effect=[0.001, -1])  # very small wait
        limiter = RedisRateLimiter(r, global_limit=1)
        with patch.object(limiter, "_async_sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter._acquire_global()
        # max(0.01, 0.001) == 0.01
        mock_sleep.assert_awaited_once_with(0.01)
