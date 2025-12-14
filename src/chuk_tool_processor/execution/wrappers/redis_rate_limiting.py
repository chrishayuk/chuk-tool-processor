# chuk_tool_processor/execution/wrappers/redis_rate_limiting.py
"""
Redis-backed distributed rate limiting for multi-instance deployments.

This module provides a rate limiter that uses Redis for distributed state,
allowing rate limits to be enforced across multiple application instances.

Uses Redis sorted sets with timestamps for a sliding window algorithm that
is both accurate and efficient.

Example:
    from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
        RedisRateLimiter,
        create_redis_rate_limiter,
    )

    # Create a distributed rate limiter
    limiter = await create_redis_rate_limiter(
        redis_url="redis://localhost:6379/0",
        global_limit=100,
        global_period=60.0,
        tool_limits={"expensive_api": (10, 60.0)},
    )

    # Use it
    await limiter.wait("my_tool")
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from chuk_tool_processor.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger("chuk_tool_processor.execution.wrappers.redis_rate_limiting")


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis sorted sets.

    Implements a sliding window algorithm with Redis sorted sets where:
    - Scores are timestamps
    - Members are unique request IDs
    - The set is trimmed to only contain requests within the window

    This provides accurate rate limiting across multiple application instances.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        global_limit: int | None = None,
        global_period: float = 60.0,
        tool_limits: dict[str, tuple[int, float]] | None = None,
        key_prefix: str = "ratelimit",
    ) -> None:
        """
        Initialize the Redis rate limiter.

        Args:
            redis: Redis async client
            global_limit: Maximum global requests per period (None = no limit)
            global_period: Time period in seconds for the global limit
            tool_limits: Dict mapping tool names to (limit, period) tuples
            key_prefix: Prefix for Redis keys
        """
        self._redis = redis
        self.global_limit = global_limit
        self.global_period = global_period
        self.tool_limits = tool_limits or {}
        self._key_prefix = key_prefix
        self._request_counter = 0

        logger.debug(
            f"Initialized Redis rate limiter: global={global_limit}/{global_period}s, "
            f"tool-specific={len(self.tool_limits)} tools"
        )

    def _global_key(self) -> str:
        """Get the Redis key for global rate limiting."""
        return f"{self._key_prefix}:global"

    def _tool_key(self, tool: str) -> str:
        """Get the Redis key for tool-specific rate limiting."""
        return f"{self._key_prefix}:tool:{tool}"

    def _generate_request_id(self) -> str:
        """Generate a unique request ID for this request."""
        self._request_counter += 1
        return f"{time.time_ns()}:{self._request_counter}"

    async def _acquire_slot(self, key: str, limit: int, period: float) -> float | None:
        """
        Try to acquire a rate limit slot.

        Uses a Lua script for atomic check-and-increment to avoid race conditions.

        Args:
            key: Redis key for this rate limit
            limit: Maximum requests allowed
            period: Time period in seconds

        Returns:
            None if slot acquired, otherwise seconds to wait
        """
        now = time.time()
        cutoff = now - period
        request_id = self._generate_request_id()

        # Use a Lua script for atomic operation
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local cutoff = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local request_id = ARGV[4]
        local period = tonumber(ARGV[5])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

        -- Count current entries
        local count = redis.call('ZCARD', key)

        if count < limit then
            -- Add new request
            redis.call('ZADD', key, now, request_id)
            -- Set expiry on the key
            redis.call('EXPIRE', key, math.ceil(period) + 1)
            return -1  -- Success
        else
            -- Get oldest entry to calculate wait time
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            if #oldest >= 2 then
                return oldest[2] + period - now  -- Wait time
            end
            return period  -- Default wait time
        end
        """

        result = await self._redis.eval(  # type: ignore[union-attr]
            lua_script, 1, key, str(now), str(cutoff), str(limit), request_id, str(period)
        )

        if result == -1:
            return None  # Slot acquired
        return float(result)  # Wait time

    async def _acquire_global(self) -> None:
        """Block until a global slot is available."""
        if self.global_limit is None:
            return

        while True:
            wait_time = await self._acquire_slot(self._global_key(), self.global_limit, self.global_period)

            if wait_time is None:
                return  # Slot acquired

            logger.debug(f"Global rate limit reached, waiting {wait_time:.2f}s")
            await self._async_sleep(max(0.01, wait_time))

    async def _acquire_tool(self, tool: str) -> None:
        """Block until a per-tool slot is available."""
        if tool not in self.tool_limits:
            return

        limit, period = self.tool_limits[tool]

        while True:
            wait_time = await self._acquire_slot(self._tool_key(tool), limit, period)

            if wait_time is None:
                return  # Slot acquired

            logger.debug(f"Tool '{tool}' rate limit reached, waiting {wait_time:.2f}s")
            await self._async_sleep(max(0.01, wait_time))

    async def _async_sleep(self, seconds: float) -> None:
        """Async sleep helper."""
        import asyncio

        await asyncio.sleep(seconds)

    async def wait(self, tool: str) -> None:
        """
        Block until rate limits allow execution.

        This method blocks until both global and tool-specific rate limits
        allow one more execution of the specified tool.

        Args:
            tool: Name of the tool being executed
        """
        await self._acquire_global()
        await self._acquire_tool(tool)

    async def check_limits(self, tool: str) -> tuple[bool, bool]:
        """
        Check if the tool would be rate limited without consuming a slot.

        Args:
            tool: Name of the tool to check

        Returns:
            Tuple of (global_limit_reached, tool_limit_reached)
        """
        global_limited = False
        tool_limited = False

        now = time.time()

        # Check global limit
        if self.global_limit is not None:
            cutoff = now - self.global_period
            await self._redis.zremrangebyscore(self._global_key(), "-inf", cutoff)  # type: ignore[union-attr]
            count = await self._redis.zcard(self._global_key())  # type: ignore[union-attr]
            global_limited = count >= self.global_limit

        # Check tool limit
        if tool in self.tool_limits:
            limit, period = self.tool_limits[tool]
            cutoff = now - period
            key = self._tool_key(tool)
            await self._redis.zremrangebyscore(key, "-inf", cutoff)  # type: ignore[union-attr]
            count = await self._redis.zcard(key)  # type: ignore[union-attr]
            tool_limited = count >= limit

        return global_limited, tool_limited

    async def get_usage(self, tool: str | None = None) -> dict[str, Any]:
        """
        Get current rate limit usage information.

        Args:
            tool: Optional specific tool to check

        Returns:
            Dict with usage statistics
        """
        now = time.time()
        result: dict[str, Any] = {}

        # Global usage
        if self.global_limit is not None:
            cutoff = now - self.global_period
            await self._redis.zremrangebyscore(self._global_key(), "-inf", cutoff)  # type: ignore[union-attr]
            count = await self._redis.zcard(self._global_key())  # type: ignore[union-attr]
            result["global"] = {
                "used": count,
                "limit": self.global_limit,
                "period": self.global_period,
                "remaining": max(0, self.global_limit - count),
            }

        # Tool usage
        if tool and tool in self.tool_limits:
            limit, period = self.tool_limits[tool]
            cutoff = now - period
            key = self._tool_key(tool)
            await self._redis.zremrangebyscore(key, "-inf", cutoff)  # type: ignore[union-attr]
            count = await self._redis.zcard(key)  # type: ignore[union-attr]
            result[tool] = {
                "used": count,
                "limit": limit,
                "period": period,
                "remaining": max(0, limit - count),
            }

        return result

    async def reset(self, tool: str | None = None) -> None:
        """
        Reset rate limit counters.

        Args:
            tool: Specific tool to reset, or None to reset all
        """
        if tool is None:
            # Reset global
            await self._redis.delete(self._global_key())  # type: ignore[union-attr]
            # Reset all tools
            for t in self.tool_limits:
                await self._redis.delete(self._tool_key(t))  # type: ignore[union-attr]
        elif tool in self.tool_limits:
            await self._redis.delete(self._tool_key(tool))  # type: ignore[union-attr]

        logger.debug(f"Reset rate limits for: {tool or 'all'}")


async def create_redis_rate_limiter(
    redis_url: str = "redis://localhost:6379/0",
    *,
    global_limit: int | None = None,
    global_period: float = 60.0,
    tool_limits: dict[str, tuple[int, float]] | None = None,
    key_prefix: str = "ratelimit",
) -> RedisRateLimiter:
    """
    Create a Redis-backed rate limiter.

    Args:
        redis_url: Redis connection URL
        global_limit: Maximum global requests per period
        global_period: Time period in seconds for global limit
        tool_limits: Dict mapping tool names to (limit, period) tuples
        key_prefix: Prefix for Redis keys

    Returns:
        Configured RedisRateLimiter instance
    """
    from redis.asyncio import Redis

    redis = Redis.from_url(redis_url, decode_responses=False)

    return RedisRateLimiter(
        redis,
        global_limit=global_limit,
        global_period=global_period,
        tool_limits=tool_limits,
        key_prefix=key_prefix,
    )
