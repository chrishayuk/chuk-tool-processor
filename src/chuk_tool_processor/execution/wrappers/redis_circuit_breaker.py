# chuk_tool_processor/execution/wrappers/redis_circuit_breaker.py
"""
Redis-backed distributed circuit breaker for multi-instance deployments.

This module provides a circuit breaker that uses Redis for distributed state,
allowing circuit breaker state to be shared across multiple application instances.

The circuit breaker implements the standard state machine:
    CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN)

Example:
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreaker,
        RedisCircuitBreakerConfig,
        create_redis_circuit_breaker,
    )

    # Create a distributed circuit breaker
    breaker = await create_redis_circuit_breaker(
        redis_url="redis://localhost:6379/0",
        default_config=RedisCircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
    )

    # Check if execution is allowed
    if await breaker.can_execute("my_tool"):
        try:
            result = await execute_tool()
            await breaker.record_success("my_tool")
        except Exception:
            await breaker.record_failure("my_tool")
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from chuk_tool_processor.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger("chuk_tool_processor.execution.wrappers.redis_circuit_breaker")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests due to failures
    HALF_OPEN = "half_open"  # Testing recovery with limited requests


@dataclass
class RedisCircuitBreakerConfig:
    """Configuration for Redis circuit breaker behavior."""

    failure_threshold: int = 5
    """Number of failures before opening circuit."""

    success_threshold: int = 2
    """Number of successes in HALF_OPEN to close circuit."""

    reset_timeout: float = 60.0
    """Seconds to wait before trying HALF_OPEN."""

    half_open_max_calls: int = 1
    """Max concurrent calls allowed in HALF_OPEN state."""

    failure_window: float = 60.0
    """Time window in seconds for counting failures."""


class RedisCircuitBreaker:
    """
    Distributed circuit breaker using Redis for state management.

    Uses Redis hashes and sorted sets for efficient state tracking:
    - Hash for circuit state (state, failure_count, success_count, etc.)
    - Sorted set for failure timestamps (for sliding window)

    All operations use Lua scripts for atomicity across multiple Redis commands.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        default_config: RedisCircuitBreakerConfig | None = None,
        tool_configs: dict[str, RedisCircuitBreakerConfig] | None = None,
        key_prefix: str = "circuitbreaker",
    ) -> None:
        """
        Initialize the Redis circuit breaker.

        Args:
            redis: Redis async client
            default_config: Default circuit breaker configuration
            tool_configs: Per-tool circuit breaker configurations
            key_prefix: Prefix for Redis keys
        """
        self._redis = redis
        self.default_config = default_config or RedisCircuitBreakerConfig()
        self.tool_configs = tool_configs or {}
        self._key_prefix = key_prefix

        logger.debug(
            f"Initialized Redis circuit breaker: "
            f"default_threshold={self.default_config.failure_threshold}, "
            f"tool-specific={len(self.tool_configs)} tools"
        )

    def _state_key(self, tool: str) -> str:
        """Get the Redis key for circuit state hash."""
        return f"{self._key_prefix}:{tool}:state"

    def _failures_key(self, tool: str) -> str:
        """Get the Redis key for failure timestamps."""
        return f"{self._key_prefix}:{tool}:failures"

    def _get_config(self, tool: str) -> RedisCircuitBreakerConfig:
        """Get configuration for a specific tool."""
        return self.tool_configs.get(tool, self.default_config)

    async def can_execute(self, tool: str) -> bool:
        """
        Check if a call should be allowed through.

        This method checks the circuit state and either:
        - Returns True (CLOSED or HALF_OPEN with available slot)
        - Returns False (OPEN or HALF_OPEN at capacity)
        - Transitions from OPEN to HALF_OPEN if timeout elapsed

        Args:
            tool: Name of the tool to check

        Returns:
            True if execution is allowed, False otherwise
        """
        config = self._get_config(tool)
        state_key = self._state_key(tool)

        lua_script = """
        local state_key = KEYS[1]
        local now = tonumber(ARGV[1])
        local reset_timeout = tonumber(ARGV[2])
        local half_open_max = tonumber(ARGV[3])

        -- Get current state
        local state = redis.call('HGET', state_key, 'state') or 'closed'
        local opened_at = tonumber(redis.call('HGET', state_key, 'opened_at') or '0')
        local half_open_calls = tonumber(redis.call('HGET', state_key, 'half_open_calls') or '0')

        if state == 'closed' then
            return 1  -- Allow
        end

        if state == 'half_open' then
            if half_open_calls < half_open_max then
                redis.call('HINCRBY', state_key, 'half_open_calls', 1)
                return 1  -- Allow
            end
            return 0  -- Reject
        end

        -- OPEN state: check if we should transition to HALF_OPEN
        if state == 'open' and opened_at > 0 then
            local elapsed = now - opened_at
            if elapsed >= reset_timeout then
                -- Transition to HALF_OPEN
                redis.call('HSET', state_key, 'state', 'half_open')
                redis.call('HSET', state_key, 'half_open_calls', 1)
                redis.call('HSET', state_key, 'success_count', 0)
                return 1  -- Allow test request
            end
        end

        return 0  -- Reject
        """

        result = await self._redis.eval(  # type: ignore[union-attr]
            lua_script, 1, state_key, str(time.time()), str(config.reset_timeout), str(config.half_open_max_calls)
        )

        return result == 1

    async def record_success(self, tool: str) -> None:
        """
        Record a successful call.

        In HALF_OPEN state, counts towards closing the circuit.
        In CLOSED state, maintains healthy status.

        Args:
            tool: Name of the tool
        """
        config = self._get_config(tool)
        state_key = self._state_key(tool)
        failures_key = self._failures_key(tool)

        lua_script = """
        local state_key = KEYS[1]
        local failures_key = KEYS[2]
        local success_threshold = tonumber(ARGV[1])

        local state = redis.call('HGET', state_key, 'state') or 'closed'

        if state == 'half_open' then
            local success_count = redis.call('HINCRBY', state_key, 'success_count', 1)
            local half_open_calls = tonumber(redis.call('HGET', state_key, 'half_open_calls') or '1')
            redis.call('HSET', state_key, 'half_open_calls', math.max(0, half_open_calls - 1))

            if success_count >= success_threshold then
                -- Close the circuit
                redis.call('HSET', state_key, 'state', 'closed')
                redis.call('HSET', state_key, 'failure_count', 0)
                redis.call('HSET', state_key, 'success_count', 0)
                redis.call('HSET', state_key, 'opened_at', 0)
                redis.call('HSET', state_key, 'half_open_calls', 0)
                redis.call('DEL', failures_key)
                return 'closed'
            end
            return 'half_open'
        else
            -- In CLOSED state, just reset failure count
            redis.call('HSET', state_key, 'failure_count', 0)
            redis.call('DEL', failures_key)
            return 'closed'
        end
        """

        new_state = await self._redis.eval(lua_script, 2, state_key, failures_key, str(config.success_threshold))  # type: ignore[union-attr]

        if new_state == b"closed":
            logger.info(f"Circuit breaker for '{tool}' transitioned to CLOSED (recovered)")

    async def record_failure(self, tool: str) -> None:
        """
        Record a failed call.

        Tracks failures in a sliding window and opens the circuit
        if the failure threshold is exceeded.

        Args:
            tool: Name of the tool
        """
        config = self._get_config(tool)
        state_key = self._state_key(tool)
        failures_key = self._failures_key(tool)
        now = time.time()

        lua_script = """
        local state_key = KEYS[1]
        local failures_key = KEYS[2]
        local now = tonumber(ARGV[1])
        local failure_window = tonumber(ARGV[2])
        local failure_threshold = tonumber(ARGV[3])

        local state = redis.call('HGET', state_key, 'state') or 'closed'

        -- Add failure timestamp
        redis.call('ZADD', failures_key, now, now .. ':' .. math.random())

        -- Remove old failures outside the window
        local cutoff = now - failure_window
        redis.call('ZREMRANGEBYSCORE', failures_key, '-inf', cutoff)

        -- Count failures in window
        local failure_count = redis.call('ZCARD', failures_key)
        redis.call('HSET', state_key, 'failure_count', failure_count)

        -- Set key expiry
        redis.call('EXPIRE', failures_key, math.ceil(failure_window) + 60)
        redis.call('EXPIRE', state_key, math.ceil(failure_window) + 3600)

        if state == 'closed' then
            if failure_count >= failure_threshold then
                -- Open the circuit
                redis.call('HSET', state_key, 'state', 'open')
                redis.call('HSET', state_key, 'opened_at', now)
                return 'open'
            end
            return 'closed'
        elseif state == 'half_open' then
            -- Failed during test, back to OPEN
            redis.call('HSET', state_key, 'state', 'open')
            redis.call('HSET', state_key, 'opened_at', now)
            redis.call('HSET', state_key, 'success_count', 0)
            local half_open_calls = tonumber(redis.call('HGET', state_key, 'half_open_calls') or '1')
            redis.call('HSET', state_key, 'half_open_calls', math.max(0, half_open_calls - 1))
            return 'open'
        else
            return 'open'
        end
        """

        new_state = await self._redis.eval(  # type: ignore[union-attr]
            lua_script,
            2,
            state_key,
            failures_key,
            str(now),
            str(config.failure_window),
            str(config.failure_threshold),
        )

        if new_state == b"open":
            logger.warning(f"Circuit breaker for '{tool}' transitioned to OPEN")

    async def get_state(self, tool: str) -> dict[str, Any]:
        """
        Get current circuit breaker state.

        Args:
            tool: Name of the tool

        Returns:
            Dict with state information
        """
        config = self._get_config(tool)
        state_key = self._state_key(tool)

        # Get state hash
        state_data = await self._redis.hgetall(state_key)  # type: ignore[union-attr]

        state = (state_data.get(b"state") or b"closed").decode()
        failure_count = int(state_data.get(b"failure_count") or 0)
        success_count = int(state_data.get(b"success_count") or 0)
        opened_at = float(state_data.get(b"opened_at") or 0)
        half_open_calls = int(state_data.get(b"half_open_calls") or 0)

        # Calculate time until half_open
        time_until_half_open = None
        if state == "open" and opened_at > 0:
            elapsed = time.time() - opened_at
            remaining = config.reset_timeout - elapsed
            if remaining > 0:
                time_until_half_open = remaining

        return {
            "state": state,
            "failure_count": failure_count,
            "success_count": success_count,
            "opened_at": opened_at if opened_at > 0 else None,
            "half_open_calls": half_open_calls,
            "time_until_half_open": time_until_half_open,
            "config": {
                "failure_threshold": config.failure_threshold,
                "success_threshold": config.success_threshold,
                "reset_timeout": config.reset_timeout,
                "half_open_max_calls": config.half_open_max_calls,
            },
        }

    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """
        Get states for all known circuit breakers.

        Returns:
            Dict mapping tool names to state info
        """
        # Scan for all circuit breaker keys
        pattern = f"{self._key_prefix}:*:state"
        states = {}

        async for key in self._redis.scan_iter(pattern):  # type: ignore[union-attr]
            # Extract tool name from key
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) >= 3:
                tool = parts[1]
                states[tool] = await self.get_state(tool)

        return states

    async def reset(self, tool: str) -> None:
        """
        Manually reset a circuit breaker to CLOSED state.

        Args:
            tool: Name of the tool to reset
        """
        state_key = self._state_key(tool)
        failures_key = self._failures_key(tool)

        await self._redis.delete(state_key, failures_key)  # type: ignore[union-attr]

        logger.info(f"Manually reset circuit breaker for '{tool}'")

    async def reset_all(self) -> int:
        """
        Reset all circuit breakers.

        Returns:
            Number of circuit breakers reset
        """
        pattern = f"{self._key_prefix}:*"
        count = 0

        async for key in self._redis.scan_iter(pattern):  # type: ignore[union-attr]
            await self._redis.delete(key)  # type: ignore[union-attr]
            count += 1

        logger.info(f"Reset {count} circuit breaker keys")
        return count


async def create_redis_circuit_breaker(
    redis_url: str = "redis://localhost:6379/0",
    *,
    default_config: RedisCircuitBreakerConfig | None = None,
    tool_configs: dict[str, RedisCircuitBreakerConfig] | None = None,
    key_prefix: str = "circuitbreaker",
) -> RedisCircuitBreaker:
    """
    Create a Redis-backed circuit breaker.

    Args:
        redis_url: Redis connection URL
        default_config: Default circuit breaker configuration
        tool_configs: Per-tool circuit breaker configurations
        key_prefix: Prefix for Redis keys

    Returns:
        Configured RedisCircuitBreaker instance
    """
    from redis.asyncio import Redis

    redis = Redis.from_url(redis_url, decode_responses=False)

    return RedisCircuitBreaker(
        redis,
        default_config=default_config,
        tool_configs=tool_configs,
        key_prefix=key_prefix,
    )


class RedisCircuitBreakerExecutor:
    """
    Executor wrapper that uses Redis-backed circuit breaker for distributed deployments.

    This wraps an underlying executor and applies circuit breaker protection
    using Redis for state management, allowing circuit breaker state to be
    shared across multiple application instances.
    """

    def __init__(
        self,
        executor: Any,
        circuit_breaker: RedisCircuitBreaker,
    ) -> None:
        """
        Initialize the Redis circuit breaker executor.

        Args:
            executor: Underlying executor to wrap
            circuit_breaker: Redis-backed circuit breaker instance
        """
        self.executor = executor
        self.circuit_breaker = circuit_breaker

    async def execute(
        self,
        calls: list,
        *,
        timeout: float | None = None,
        use_cache: bool = True,
    ) -> list:
        """
        Execute tool calls with Redis-backed circuit breaker protection.

        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution
            use_cache: Whether to use cached results

        Returns:
            List of tool results
        """
        from datetime import UTC, datetime

        from chuk_tool_processor.core.exceptions import ToolCircuitOpenError
        from chuk_tool_processor.models.tool_result import ToolResult

        if not calls:
            return []

        results: list = []

        for call in calls:
            # Check if circuit allows execution
            can_execute = await self.circuit_breaker.can_execute(call.tool)

            if not can_execute:
                # Circuit is OPEN - reject immediately
                state_info = await self.circuit_breaker.get_state(call.tool)
                logger.warning(
                    f"Redis circuit breaker OPEN for {call.tool} (failures: {state_info.get('failure_count', 0)})"
                )

                reset_time = state_info.get("time_until_half_open")
                error = ToolCircuitOpenError(
                    tool_name=call.tool,
                    failure_count=state_info.get("failure_count", 0),
                    reset_timeout=reset_time,
                )

                now = datetime.now(UTC)
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result=None,
                        error=str(error),
                        error_info=error.to_error_info(),
                        start_time=now,
                        end_time=now,
                        machine="redis_circuit_breaker",
                        pid=0,
                    )
                )
                continue

            # Execute the call
            try:
                # Execute single call
                executor_kwargs = {"timeout": timeout}
                if hasattr(self.executor, "use_cache"):
                    executor_kwargs["use_cache"] = use_cache

                result_list = await self.executor.execute([call], **executor_kwargs)
                result = result_list[0]

                # Determine success/failure
                is_error = result.error is not None

                if is_error:
                    await self.circuit_breaker.record_failure(call.tool)
                else:
                    await self.circuit_breaker.record_success(call.tool)

                results.append(result)

            except Exception as e:
                # Exception during execution
                await self.circuit_breaker.record_failure(call.tool)

                now = datetime.now(UTC)
                results.append(
                    ToolResult.create_error(
                        tool=call.tool,
                        error=e,
                        start_time=now,
                        end_time=now,
                        machine="redis_circuit_breaker",
                        pid=0,
                    )
                )

        return results

    async def get_circuit_states(self) -> dict[str, dict[str, Any]]:
        """
        Get current state of all circuit breakers.

        Returns:
            Dict mapping tool name to state info
        """
        return await self.circuit_breaker.get_all_states()

    async def reset_circuit(self, tool: str) -> None:
        """
        Manually reset a circuit breaker.

        Args:
            tool: Tool name to reset
        """
        await self.circuit_breaker.reset(tool)


async def create_redis_circuit_breaker_executor(
    executor: Any,
    redis_url: str = "redis://localhost:6379/0",
    *,
    default_config: RedisCircuitBreakerConfig | None = None,
    tool_configs: dict[str, RedisCircuitBreakerConfig] | None = None,
    key_prefix: str = "circuitbreaker",
) -> RedisCircuitBreakerExecutor:
    """
    Create a Redis-backed circuit breaker executor.

    This is a convenience function that creates both the Redis circuit breaker
    and the executor wrapper.

    Args:
        executor: Underlying executor to wrap
        redis_url: Redis connection URL
        default_config: Default circuit breaker configuration
        tool_configs: Per-tool circuit breaker configurations
        key_prefix: Prefix for Redis keys

    Returns:
        Configured RedisCircuitBreakerExecutor instance

    Example:
        from chuk_tool_processor.execution.strategies import InProcessStrategy
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            create_redis_circuit_breaker_executor,
            RedisCircuitBreakerConfig,
        )

        strategy = InProcessStrategy(registry)
        executor = await create_redis_circuit_breaker_executor(
            strategy,
            redis_url="redis://localhost:6379/0",
            default_config=RedisCircuitBreakerConfig(
                failure_threshold=5,
                reset_timeout=60.0,
            ),
        )
    """
    circuit_breaker = await create_redis_circuit_breaker(
        redis_url=redis_url,
        default_config=default_config,
        tool_configs=tool_configs,
        key_prefix=key_prefix,
    )

    return RedisCircuitBreakerExecutor(executor, circuit_breaker)
