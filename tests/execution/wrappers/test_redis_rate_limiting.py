# tests/execution/wrappers/test_redis_rate_limiting.py
"""
Tests for the Redis-backed rate limiting implementation.

These tests use fakeredis for in-memory Redis simulation, allowing testing
without a real Redis server.
"""

import asyncio

import pytest
import pytest_asyncio

# Check if redis and fakeredis are available
pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")

from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (  # noqa: E402
    RedisRateLimiter,
)
from chuk_tool_processor.models.tool_call import ToolCall  # noqa: E402
from chuk_tool_processor.models.tool_result import ToolResult  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def fake_redis():
    """Create a fake Redis client for testing."""
    server = fakeredis.FakeServer()
    redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=False)
    yield redis
    await redis.aclose()


@pytest_asyncio.fixture
async def limiter(fake_redis):
    """Create a RedisRateLimiter with fake Redis."""
    return RedisRateLimiter(
        fake_redis,
        global_limit=5,
        global_period=60.0,
        tool_limits={"expensive_tool": (2, 30.0)},
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_redis_rate_limiter_init(fake_redis):
    """Test RedisRateLimiter initialization."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"test": (10, 30.0)},
    )
    assert limiter.global_limit == 100
    assert limiter.global_period == 60.0
    assert "test" in limiter.tool_limits


@pytest.mark.asyncio
async def test_redis_rate_limiter_no_limit(fake_redis):
    """Test that no rate limiting occurs when global_limit is None."""
    limiter = RedisRateLimiter(fake_redis, global_limit=None)

    # Should complete immediately without blocking
    for _ in range(100):
        await limiter.wait("test_tool")


@pytest.mark.asyncio
async def test_redis_rate_limiter_global_limit(fake_redis):
    """Test global rate limiting."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=3,
        global_period=60.0,
    )

    # First 3 calls should pass immediately
    for _i in range(3):
        await limiter.wait("tool")

    # Check that global limit is reached
    global_limited, tool_limited = await limiter.check_limits("tool")
    assert global_limited is True
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_tool_specific_limit(fake_redis):
    """Test tool-specific rate limiting."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=None,  # No global limit
        tool_limits={"limited_tool": (2, 60.0)},
    )

    # First 2 calls should pass
    await limiter.wait("limited_tool")
    await limiter.wait("limited_tool")

    # Check that tool limit is reached
    global_limited, tool_limited = await limiter.check_limits("limited_tool")
    assert global_limited is False
    assert tool_limited is True

    # Unlimited tool should not be limited
    global_limited, tool_limited = await limiter.check_limits("unlimited_tool")
    assert global_limited is False
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_check_limits(limiter):
    """Test the check_limits method."""
    # Initially no limits reached
    global_limited, tool_limited = await limiter.check_limits("expensive_tool")
    assert global_limited is False
    assert tool_limited is False

    # Use up the tool-specific limit (2 calls)
    await limiter.wait("expensive_tool")
    await limiter.wait("expensive_tool")

    # Tool limit should be reached, but not global
    global_limited, tool_limited = await limiter.check_limits("expensive_tool")
    assert global_limited is False
    assert tool_limited is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage(limiter):
    """Test the get_usage method."""
    # Make some calls
    await limiter.wait("expensive_tool")
    await limiter.wait("expensive_tool")
    await limiter.wait("other_tool")

    # Get usage for expensive_tool
    usage = await limiter.get_usage("expensive_tool")
    assert "global" in usage
    assert "expensive_tool" in usage
    assert usage["global"]["used"] == 3
    assert usage["expensive_tool"]["used"] == 2
    assert usage["expensive_tool"]["limit"] == 2
    assert usage["expensive_tool"]["remaining"] == 0


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset(limiter):
    """Test resetting rate limits."""
    # Use up some limits
    await limiter.wait("expensive_tool")
    await limiter.wait("expensive_tool")

    # Verify limits are reached
    global_limited, tool_limited = await limiter.check_limits("expensive_tool")
    assert tool_limited is True

    # Reset the tool limit
    await limiter.reset("expensive_tool")

    # Verify limit is reset
    global_limited, tool_limited = await limiter.check_limits("expensive_tool")
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset_all(fake_redis):
    """Test resetting all rate limits."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=60.0,
        tool_limits={"tool1": (1, 60.0), "tool2": (1, 60.0)},
    )

    # Use up all limits
    await limiter.wait("tool1")
    await limiter.wait("tool2")

    # Verify limits are reached
    global_limited, _ = await limiter.check_limits("tool1")
    assert global_limited is True

    # Reset all
    await limiter.reset(None)

    # Verify all limits are reset
    global_limited, tool_limited = await limiter.check_limits("tool1")
    assert global_limited is False
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_key_prefix(fake_redis):
    """Test custom key prefix."""
    limiter1 = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=60.0,
        key_prefix="app1:ratelimit",
    )
    limiter2 = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=60.0,
        key_prefix="app2:ratelimit",
    )

    # Use up limit in limiter1
    await limiter1.wait("tool")
    await limiter1.wait("tool")

    # Limiter1 should be at limit
    global_limited1, _ = await limiter1.check_limits("tool")
    assert global_limited1 is True

    # Limiter2 should not be affected (different prefix)
    global_limited2, _ = await limiter2.check_limits("tool")
    assert global_limited2 is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_concurrent_requests(fake_redis):
    """Test that concurrent requests are handled correctly."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=5,
        global_period=60.0,
    )

    # Make concurrent requests
    tasks = [limiter.wait("tool") for _ in range(5)]
    await asyncio.gather(*tasks)

    # All 5 should have been allowed
    usage = await limiter.get_usage()
    assert usage["global"]["used"] == 5


@pytest.mark.asyncio
async def test_redis_rate_limiter_sliding_window(fake_redis):
    """Test sliding window behavior with mocked time."""
    # This test verifies the sliding window algorithm works correctly
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=1.0,  # 1 second window for faster testing
    )

    # Use up the limit
    await limiter.wait("tool")
    await limiter.wait("tool")

    # Should be at limit
    global_limited, _ = await limiter.check_limits("tool")
    assert global_limited is True

    # Wait for the window to expire
    await asyncio.sleep(1.1)

    # Should be able to make more requests
    global_limited, _ = await limiter.check_limits("tool")
    assert global_limited is False


class DummyExecutor:
    """Simple executor for testing."""

    def __init__(self):
        self.call_count = 0

    async def execute(self, calls, timeout=None, use_cache=True):
        self.call_count += len(calls)
        return [
            ToolResult(
                tool=c.tool,
                result={"success": True},
                error=None,
            )
            for c in calls
        ]


@pytest.mark.asyncio
async def test_redis_rate_limiter_with_executor(fake_redis):
    """Test using Redis rate limiter with RateLimitedToolExecutor."""
    from chuk_tool_processor.execution.wrappers.rate_limiting import RateLimitedToolExecutor

    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=3,
        global_period=60.0,
    )

    executor = DummyExecutor()
    rate_limited_executor = RateLimitedToolExecutor(executor, limiter)

    calls = [
        ToolCall(tool="tool1", arguments={}),
        ToolCall(tool="tool2", arguments={}),
        ToolCall(tool="tool3", arguments={}),
    ]

    results = await rate_limited_executor.execute(calls)
    assert len(results) == 3
    assert executor.call_count == 3


# --------------------------------------------------------------------------- #
# Additional tests for better coverage
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_redis_rate_limiter_private_key_methods(fake_redis):
    """Test private key generation methods."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        key_prefix="myprefix",
    )

    global_key = limiter._global_key()
    assert global_key == "myprefix:global"

    tool_key = limiter._tool_key("my_tool")
    assert tool_key == "myprefix:tool:my_tool"


@pytest.mark.asyncio
async def test_redis_rate_limiter_generate_request_id(fake_redis):
    """Test unique request ID generation."""
    limiter = RedisRateLimiter(fake_redis, global_limit=100)

    id1 = limiter._generate_request_id()
    id2 = limiter._generate_request_id()
    id3 = limiter._generate_request_id()

    # All IDs should be unique
    assert id1 != id2
    assert id2 != id3
    assert id1 != id3


@pytest.mark.asyncio
async def test_redis_rate_limiter_acquire_slot_success(fake_redis):
    """Test _acquire_slot returns None on success."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=10,
        global_period=60.0,
    )

    # Should acquire successfully
    result = await limiter._acquire_slot(limiter._global_key(), 10, 60.0)
    assert result is None  # Success


@pytest.mark.asyncio
async def test_redis_rate_limiter_acquire_slot_limited(fake_redis):
    """Test _acquire_slot returns wait time when limited."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=1,
        global_period=60.0,
    )

    # First should succeed
    result1 = await limiter._acquire_slot(limiter._global_key(), 1, 60.0)
    assert result1 is None

    # Second should be limited
    result2 = await limiter._acquire_slot(limiter._global_key(), 1, 60.0)
    assert result2 is not None
    assert result2 > 0  # Should be wait time


@pytest.mark.asyncio
async def test_redis_rate_limiter_async_sleep(fake_redis):
    """Test _async_sleep helper."""
    import time

    limiter = RedisRateLimiter(fake_redis)

    start = time.time()
    await limiter._async_sleep(0.1)
    elapsed = time.time() - start

    assert elapsed >= 0.09  # Allow some tolerance


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage_no_limit(fake_redis):
    """Test get_usage when no limit is set."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=None,  # No limit
    )

    usage = await limiter.get_usage()
    assert "global" not in usage  # No global entry when no limit


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage_with_tool_not_in_limits(fake_redis):
    """Test get_usage for a tool not in tool_limits."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        tool_limits={"known_tool": (10, 60.0)},
    )

    # Request usage for unknown tool
    usage = await limiter.get_usage("unknown_tool")
    assert "global" in usage
    assert "unknown_tool" not in usage  # Not tracked


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset_specific_tool(fake_redis):
    """Test reset for a specific tool."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        tool_limits={"limited_tool": (2, 60.0)},
    )

    # Use up the tool limit
    await limiter.wait("limited_tool")
    await limiter.wait("limited_tool")

    # Verify limited
    global_limited, tool_limited = await limiter.check_limits("limited_tool")
    assert tool_limited is True

    # Reset only that tool
    await limiter.reset("limited_tool")

    # Tool should be reset but global is not
    global_limited, tool_limited = await limiter.check_limits("limited_tool")
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset_tool_not_in_limits(fake_redis):
    """Test reset for a tool not in tool_limits does nothing."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        tool_limits={"known_tool": (10, 60.0)},
    )

    # Should not raise error
    await limiter.reset("unknown_tool")


@pytest.mark.asyncio
async def test_create_redis_rate_limiter_function(fake_redis, monkeypatch):
    """Test the create_redis_rate_limiter factory function."""
    from chuk_tool_processor.execution.wrappers import redis_rate_limiting

    def mock_from_url(*args, **kwargs):
        return fake_redis

    from redis import asyncio as redis_asyncio

    original_from_url = redis_asyncio.Redis.from_url
    monkeypatch.setattr(redis_asyncio.Redis, "from_url", mock_from_url)

    try:
        limiter = await redis_rate_limiting.create_redis_rate_limiter(
            redis_url="redis://localhost:6379/0",
            global_limit=100,
            global_period=30.0,
            tool_limits={"api": (10, 60.0)},
            key_prefix="test_limiter",
        )

        assert limiter is not None
        assert limiter._key_prefix == "test_limiter"
        assert limiter.global_limit == 100
        assert limiter.global_period == 30.0
        assert "api" in limiter.tool_limits
    finally:
        monkeypatch.setattr(redis_asyncio.Redis, "from_url", original_from_url)


@pytest.mark.asyncio
async def test_redis_rate_limiter_wait_with_tool_limit_blocking(fake_redis):
    """Test wait blocks and retries when tool limit is reached."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=None,  # No global limit
        tool_limits={"limited_tool": (1, 0.2)},  # 1 per 200ms
    )

    import time

    start = time.time()

    # First should pass immediately
    await limiter.wait("limited_tool")

    # Second should block until the window allows
    await limiter.wait("limited_tool")

    elapsed = time.time() - start
    # Should have waited at least 200ms for the second call
    assert elapsed >= 0.15  # Allow some tolerance


@pytest.mark.asyncio
async def test_redis_rate_limiter_wait_with_global_limit_blocking(fake_redis):
    """Test wait blocks and retries when global limit is reached."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=1,
        global_period=0.2,  # 1 per 200ms
    )

    import time

    start = time.time()

    # First should pass immediately
    await limiter.wait("any_tool")

    # Second should block until the window allows
    await limiter.wait("any_tool")

    elapsed = time.time() - start
    # Should have waited at least 200ms for the second call
    assert elapsed >= 0.15  # Allow some tolerance


@pytest.mark.asyncio
async def test_redis_rate_limiter_check_limits_both_limited(fake_redis):
    """Test check_limits when both global and tool limits are reached."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=60.0,
        tool_limits={"limited_tool": (1, 60.0)},
    )

    # Use up both limits
    await limiter.wait("limited_tool")  # Uses 1 global, 1 tool
    await limiter.wait("other_tool")  # Uses 1 global

    # Check limits
    global_limited, tool_limited = await limiter.check_limits("limited_tool")
    assert global_limited is True
    assert tool_limited is True


# --------------------------------------------------------------------------- #
# Additional tests for better coverage
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_redis_rate_limiter_acquire_slot_returns_wait_time(fake_redis):
    """Test _acquire_slot returns wait time when at limit."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=1,
        global_period=60.0,
    )

    # Acquire first slot
    result1 = await limiter._acquire_slot(limiter._global_key(), 1, 60.0)
    assert result1 is None  # Success

    # Second attempt should return wait time
    result2 = await limiter._acquire_slot(limiter._global_key(), 1, 60.0)
    assert result2 is not None
    assert result2 > 0  # Positive wait time


@pytest.mark.asyncio
async def test_redis_rate_limiter_acquire_global_loops(fake_redis):
    """Test _acquire_global loops until slot available."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=1,
        global_period=0.05,  # Very short period
    )

    # Acquire first slot
    await limiter.wait("tool1")

    # Second wait should block briefly
    import time

    start = time.time()
    await limiter.wait("tool2")
    elapsed = time.time() - start

    # Should have waited approximately period time
    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_redis_rate_limiter_acquire_tool_loops(fake_redis):
    """Test _acquire_tool loops until slot available."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=None,  # No global limit
        tool_limits={"limited": (1, 0.05)},  # Very short period
    )

    # Acquire first slot
    await limiter.wait("limited")

    # Second wait should block briefly
    import time

    start = time.time()
    await limiter.wait("limited")
    elapsed = time.time() - start

    # Should have waited approximately period time
    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_redis_rate_limiter_check_limits_global_only(fake_redis):
    """Test check_limits when only global limit is set."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=60.0,
    )

    # Use up global limit
    await limiter.wait("tool1")
    await limiter.wait("tool2")

    # Check limits
    global_limited, tool_limited = await limiter.check_limits("tool1")
    assert global_limited is True
    assert tool_limited is False  # No tool limit configured


@pytest.mark.asyncio
async def test_redis_rate_limiter_check_limits_tool_only(fake_redis):
    """Test check_limits when only tool limit is set."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=None,  # No global limit
        tool_limits={"limited": (1, 60.0)},
    )

    # Use up tool limit
    await limiter.wait("limited")

    # Check limits
    global_limited, tool_limited = await limiter.check_limits("limited")
    assert global_limited is False  # No global limit
    assert tool_limited is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage_with_tool_limit(fake_redis):
    """Test get_usage returns tool-specific usage."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"tracked_tool": (10, 60.0)},
    )

    # Use some slots
    await limiter.wait("tracked_tool")
    await limiter.wait("tracked_tool")
    await limiter.wait("tracked_tool")

    # Get usage for the tool
    usage = await limiter.get_usage("tracked_tool")

    assert "global" in usage
    assert usage["global"]["used"] == 3
    assert usage["global"]["limit"] == 100

    assert "tracked_tool" in usage
    assert usage["tracked_tool"]["used"] == 3
    assert usage["tracked_tool"]["limit"] == 10
    assert usage["tracked_tool"]["remaining"] == 7


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage_no_tool_limit(fake_redis):
    """Test get_usage when tool has no specific limit."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"other_tool": (10, 60.0)},  # Different tool
    )

    # Use some slots with untracked tool
    await limiter.wait("untracked_tool")

    # Get usage - should only have global
    usage = await limiter.get_usage("untracked_tool")

    assert "global" in usage
    assert usage["global"]["used"] == 1
    assert "untracked_tool" not in usage  # No specific tracking


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset_all_tools(fake_redis):
    """Test reset(None) resets all rate limits including all tools."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"tool1": (10, 60.0), "tool2": (10, 60.0)},
    )

    # Use some slots
    await limiter.wait("tool1")
    await limiter.wait("tool1")
    await limiter.wait("tool2")

    # Verify used
    usage = await limiter.get_usage("tool1")
    assert usage["global"]["used"] == 3
    assert usage["tool1"]["used"] == 2

    # Reset all
    await limiter.reset(None)

    # Verify reset
    usage = await limiter.get_usage("tool1")
    assert usage["global"]["used"] == 0
    assert usage["tool1"]["used"] == 0


@pytest.mark.asyncio
async def test_redis_rate_limiter_reset_specific_tool_in_limits(fake_redis):
    """Test reset(tool) when tool is in tool_limits."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"limited_tool": (10, 60.0)},
    )

    # Use tool slots
    await limiter.wait("limited_tool")
    await limiter.wait("limited_tool")

    # Reset the tool
    await limiter.reset("limited_tool")

    # Verify tool reset but global unchanged
    global_limited, tool_limited = await limiter.check_limits("limited_tool")
    assert tool_limited is False  # Tool reset
    assert global_limited is False  # Global still has headroom


@pytest.mark.asyncio
async def test_redis_rate_limiter_check_limits_removes_expired(fake_redis):
    """Test check_limits removes expired entries."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=2,
        global_period=0.1,  # Short period
        tool_limits={"tool": (2, 0.1)},
    )

    # Use up limits
    await limiter.wait("tool")
    await limiter.wait("tool")

    # Should be at limit
    global_limited, tool_limited = await limiter.check_limits("tool")
    assert global_limited is True
    assert tool_limited is True

    # Wait for expiry
    await asyncio.sleep(0.15)

    # Should no longer be limited
    global_limited, tool_limited = await limiter.check_limits("tool")
    assert global_limited is False
    assert tool_limited is False


@pytest.mark.asyncio
async def test_redis_rate_limiter_get_usage_cleans_expired(fake_redis):
    """Test get_usage removes expired entries before counting."""
    limiter = RedisRateLimiter(
        fake_redis,
        global_limit=10,
        global_period=0.1,  # Short period
        tool_limits={"tool": (10, 0.1)},
    )

    # Use some slots
    await limiter.wait("tool")
    await limiter.wait("tool")

    # Wait for expiry
    await asyncio.sleep(0.15)

    # Get usage - should be 0 after cleanup
    usage = await limiter.get_usage("tool")
    assert usage["global"]["used"] == 0
    assert usage["tool"]["used"] == 0


# --------------------------------------------------------------------------- #
# Mocked tests for better coverage of internal code paths
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_acquire_slot_returns_none_on_success():
    """Test _acquire_slot returns None when slot is acquired."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=-1)

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=10,
        global_period=60.0,
    )

    result = await limiter._acquire_slot("test_key", 10, 60.0)
    assert result is None


@pytest.mark.asyncio
async def test_acquire_slot_returns_wait_time_when_limited():
    """Test _acquire_slot returns wait time when at limit."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=30.5)  # Wait time

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=10,
        global_period=60.0,
    )

    result = await limiter._acquire_slot("test_key", 10, 60.0)
    assert result == 30.5
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_acquire_global_returns_immediately_when_no_limit():
    """Test _acquire_global returns immediately when no global limit."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=None,  # No limit
    )

    # Should return immediately without calling Redis
    await limiter._acquire_global()
    mock_redis.eval.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_global_loops_until_slot_available():
    """Test _acquire_global loops until slot is available."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_redis = MagicMock()
    # First call returns wait time, second returns success
    mock_redis.eval = AsyncMock(side_effect=[0.01, -1])

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=10,
        global_period=60.0,
    )

    # Patch _async_sleep to avoid actual sleeping
    with patch.object(limiter, "_async_sleep", new_callable=AsyncMock):
        await limiter._acquire_global()

    # Should have been called twice
    assert mock_redis.eval.call_count == 2


@pytest.mark.asyncio
async def test_acquire_tool_returns_immediately_when_no_limit():
    """Test _acquire_tool returns immediately when tool has no limit."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=None,
        tool_limits={},  # No tool limits
    )

    # Should return immediately without calling Redis
    await limiter._acquire_tool("unknown_tool")
    mock_redis.eval.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_tool_loops_until_slot_available():
    """Test _acquire_tool loops until slot is available."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_redis = MagicMock()
    # First call returns wait time, second returns success
    mock_redis.eval = AsyncMock(side_effect=[0.01, -1])

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=None,
        tool_limits={"limited_tool": (10, 60.0)},
    )

    # Patch _async_sleep to avoid actual sleeping
    with patch.object(limiter, "_async_sleep", new_callable=AsyncMock):
        await limiter._acquire_tool("limited_tool")

    # Should have been called twice
    assert mock_redis.eval.call_count == 2


@pytest.mark.asyncio
async def test_check_limits_global_limited():
    """Test check_limits when global limit is reached."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=100)  # At limit

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
    )

    global_limited, tool_limited = await limiter.check_limits("test_tool")

    assert global_limited is True
    assert tool_limited is False


@pytest.mark.asyncio
async def test_check_limits_tool_limited():
    """Test check_limits when tool limit is reached."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=10)  # At limit

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=None,
        tool_limits={"limited_tool": (10, 60.0)},
    )

    global_limited, tool_limited = await limiter.check_limits("limited_tool")

    assert global_limited is False
    assert tool_limited is True


@pytest.mark.asyncio
async def test_check_limits_both_limited():
    """Test check_limits when both limits are reached."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=100)  # At limit

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"limited_tool": (100, 60.0)},
    )

    global_limited, tool_limited = await limiter.check_limits("limited_tool")

    assert global_limited is True
    assert tool_limited is True


@pytest.mark.asyncio
async def test_get_usage_with_global_limit():
    """Test get_usage returns global usage info."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=50)

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
    )

    usage = await limiter.get_usage()

    assert "global" in usage
    assert usage["global"]["used"] == 50
    assert usage["global"]["limit"] == 100
    assert usage["global"]["remaining"] == 50


@pytest.mark.asyncio
async def test_get_usage_with_tool_limit():
    """Test get_usage returns tool usage info."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=5)

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=None,
        tool_limits={"api_tool": (10, 60.0)},
    )

    usage = await limiter.get_usage("api_tool")

    assert "api_tool" in usage
    assert usage["api_tool"]["used"] == 5
    assert usage["api_tool"]["limit"] == 10
    assert usage["api_tool"]["remaining"] == 5


@pytest.mark.asyncio
async def test_get_usage_remaining_never_negative():
    """Test get_usage returns 0 for remaining when over limit."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.zremrangebyscore = AsyncMock()
    mock_redis.zcard = AsyncMock(return_value=150)  # Over limit

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
    )

    usage = await limiter.get_usage()

    assert usage["global"]["remaining"] == 0


@pytest.mark.asyncio
async def test_reset_all_deletes_global_and_tools():
    """Test reset(None) deletes global and all tool keys."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={
            "tool1": (10, 60.0),
            "tool2": (20, 60.0),
        },
        key_prefix="test",
    )

    await limiter.reset(None)

    # Should delete global key and both tool keys
    assert mock_redis.delete.call_count == 3


@pytest.mark.asyncio
async def test_reset_specific_tool():
    """Test reset(tool) deletes only that tool's key."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"limited_tool": (10, 60.0)},
        key_prefix="test",
    )

    await limiter.reset("limited_tool")

    # Should delete only the tool key
    mock_redis.delete.assert_called_once_with("test:tool:limited_tool")


@pytest.mark.asyncio
async def test_reset_unknown_tool_no_error():
    """Test reset(unknown_tool) doesn't fail."""
    from unittest.mock import AsyncMock, MagicMock

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        tool_limits={"known_tool": (10, 60.0)},
    )

    # Should not raise error
    await limiter.reset("unknown_tool")

    # Should not call delete (tool not in tool_limits)
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_wait_calls_acquire_global_and_tool():
    """Test wait calls both _acquire_global and _acquire_tool."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=-1)

    limiter = RedisRateLimiter(
        mock_redis,
        global_limit=100,
        global_period=60.0,
        tool_limits={"my_tool": (10, 60.0)},
    )

    with (
        patch.object(limiter, "_acquire_global", new_callable=AsyncMock) as mock_global,
        patch.object(limiter, "_acquire_tool", new_callable=AsyncMock) as mock_tool,
    ):
        await limiter.wait("my_tool")

    mock_global.assert_called_once()
    mock_tool.assert_called_once_with("my_tool")


@pytest.mark.asyncio
async def test_async_sleep_actually_sleeps():
    """Test _async_sleep calls asyncio.sleep."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_redis = MagicMock()

    limiter = RedisRateLimiter(mock_redis)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter._async_sleep(0.5)

    mock_sleep.assert_called_once_with(0.5)
