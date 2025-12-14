# chuk_tool_processor/execution/wrappers/factory.py
"""
Factory module for creating circuit breakers and rate limiters with configurable backends.

This module provides a unified interface for creating production wrappers that work
with either in-memory (single-instance) or Redis (distributed) backends.

Example:
    from chuk_tool_processor.execution.wrappers.factory import (
        create_circuit_breaker,
        create_rate_limiter,
        WrapperBackend,
    )

    # Create in-memory circuit breaker (default)
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=5,
        reset_timeout=60.0,
    )

    # Create Redis-backed circuit breaker for distributed deployments
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        failure_threshold=5,
        reset_timeout=60.0,
    )

    # Create rate limiter with automatic backend detection
    limiter = await create_rate_limiter(
        backend=WrapperBackend.AUTO,  # Uses Redis if available, falls back to memory
        global_limit=100,
        global_period=60.0,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from chuk_tool_processor.execution.wrappers.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerExecutor,
)
from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimitedToolExecutor,
    RateLimiter,
)
from chuk_tool_processor.logging import get_logger

if TYPE_CHECKING:
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreaker,
    )
    from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
        RedisRateLimiter,
    )

logger = get_logger("chuk_tool_processor.execution.wrappers.factory")


class WrapperBackend(str, Enum):
    """Backend type for production wrappers."""

    MEMORY = "memory"  # In-memory, single-instance
    REDIS = "redis"  # Redis-backed, distributed
    AUTO = "auto"  # Auto-detect (Redis if available, else memory)


@runtime_checkable
class CircuitBreakerInterface(Protocol):
    """Protocol for circuit breaker implementations."""

    async def can_execute(self, tool: str) -> bool:
        """Check if execution is allowed."""
        ...

    async def record_success(self, tool: str) -> None:
        """Record a successful execution."""
        ...

    async def record_failure(self, tool: str) -> None:
        """Record a failed execution."""
        ...


@runtime_checkable
class RateLimiterInterface(Protocol):
    """Protocol for rate limiter implementations."""

    async def wait(self, tool: str) -> None:
        """Wait until rate limit allows execution."""
        ...


@dataclass
class CircuitBreakerSettings:
    """Configuration settings for circuit breaker creation."""

    failure_threshold: int = 5
    """Number of failures before opening circuit."""

    success_threshold: int = 2
    """Number of successes in HALF_OPEN to close circuit."""

    reset_timeout: float = 60.0
    """Seconds to wait before trying HALF_OPEN."""

    half_open_max_calls: int = 1
    """Max concurrent calls allowed in HALF_OPEN state."""

    failure_window: float = 60.0
    """Time window in seconds for counting failures (Redis only)."""

    # Per-tool overrides
    tool_configs: dict[str, dict[str, Any]] | None = None


@dataclass
class RateLimiterSettings:
    """Configuration settings for rate limiter creation."""

    global_limit: int | None = None
    """Maximum global requests per period (None = no limit)."""

    global_period: float = 60.0
    """Time period in seconds for the global limit."""

    tool_limits: dict[str, tuple[int, float]] | None = None
    """Dict mapping tool names to (limit, period) tuples."""


def _check_redis_available() -> bool:
    """Check if Redis package is available."""
    try:
        import redis.asyncio  # noqa: F401

        return True
    except ImportError:
        return False


async def create_circuit_breaker(
    backend: WrapperBackend = WrapperBackend.MEMORY,
    *,
    redis_url: str = "redis://localhost:6379/0",
    key_prefix: str = "circuitbreaker",
    **settings: Any,
) -> CircuitBreakerInterface:
    """
    Create a circuit breaker with the specified backend.

    Args:
        backend: Backend type (MEMORY, REDIS, or AUTO)
        redis_url: Redis connection URL (only used for REDIS backend)
        key_prefix: Key prefix for Redis storage (only used for REDIS backend)
        **settings: Circuit breaker settings (failure_threshold, reset_timeout, etc.)

    Returns:
        Circuit breaker instance implementing CircuitBreakerInterface

    Example:
        # Memory-backed (single instance)
        breaker = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=5,
            reset_timeout=60.0,
        )

        # Redis-backed (distributed)
        breaker = await create_circuit_breaker(
            backend=WrapperBackend.REDIS,
            redis_url="redis://localhost:6379/0",
            failure_threshold=5,
            reset_timeout=60.0,
        )
    """
    # Determine actual backend
    actual_backend = backend
    if backend == WrapperBackend.AUTO:
        actual_backend = WrapperBackend.REDIS if _check_redis_available() else WrapperBackend.MEMORY
        logger.debug(f"Auto-detected backend: {actual_backend.value}")

    if actual_backend == WrapperBackend.REDIS:
        if not _check_redis_available():
            raise ImportError("Redis package not installed. Install with: pip install chuk-tool-processor[redis]")

        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreakerConfig,
            create_redis_circuit_breaker,
        )

        # Build config from settings
        config = RedisCircuitBreakerConfig(
            failure_threshold=settings.get("failure_threshold", 5),
            success_threshold=settings.get("success_threshold", 2),
            reset_timeout=settings.get("reset_timeout", 60.0),
            half_open_max_calls=settings.get("half_open_max_calls", 1),
            failure_window=settings.get("failure_window", 60.0),
        )

        # Handle per-tool configs
        tool_configs = None
        if "tool_configs" in settings and settings["tool_configs"]:
            tool_configs = {tool: RedisCircuitBreakerConfig(**cfg) for tool, cfg in settings["tool_configs"].items()}

        breaker: RedisCircuitBreaker = await create_redis_circuit_breaker(
            redis_url=redis_url,
            default_config=config,
            tool_configs=tool_configs,
            key_prefix=key_prefix,
        )
        logger.info(f"Created Redis circuit breaker: {redis_url}")
        return breaker

    else:
        # Memory-backed circuit breaker
        config = CircuitBreakerConfig(
            failure_threshold=settings.get("failure_threshold", 5),
            success_threshold=settings.get("success_threshold", 2),
            reset_timeout=settings.get("reset_timeout", 60.0),
            half_open_max_calls=settings.get("half_open_max_calls", 1),
        )

        # Handle per-tool configs
        tool_configs = None
        if "tool_configs" in settings and settings["tool_configs"]:
            tool_configs = {tool: CircuitBreakerConfig(**cfg) for tool, cfg in settings["tool_configs"].items()}

        # Create a memory circuit breaker implementation
        from chuk_tool_processor.execution.wrappers.circuit_breaker import (
            CircuitBreakerState,
        )

        class MemoryCircuitBreaker:
            """Memory-backed circuit breaker that implements the protocol interface."""

            def __init__(
                self,
                default_config: CircuitBreakerConfig,
                tool_configs: dict[str, CircuitBreakerConfig] | None = None,
            ):
                self._default_config = default_config
                self._tool_configs = tool_configs or {}
                self._states: dict[str, CircuitBreakerState] = {}

            def _get_config(self, tool: str) -> CircuitBreakerConfig:
                return self._tool_configs.get(tool, self._default_config)

            def _get_state(self, tool: str) -> CircuitBreakerState:
                if tool not in self._states:
                    self._states[tool] = CircuitBreakerState(self._get_config(tool))
                return self._states[tool]

            async def can_execute(self, tool: str) -> bool:
                state = self._get_state(tool)
                return await state.can_execute()

            async def record_success(self, tool: str) -> None:
                state = self._get_state(tool)
                await state.record_success()

            async def record_failure(self, tool: str) -> None:
                state = self._get_state(tool)
                await state.record_failure()

        breaker = MemoryCircuitBreaker(config, tool_configs)
        logger.info("Created in-memory circuit breaker")
        return breaker


async def create_rate_limiter(
    backend: WrapperBackend = WrapperBackend.MEMORY,
    *,
    redis_url: str = "redis://localhost:6379/0",
    key_prefix: str = "ratelimit",
    **settings: Any,
) -> RateLimiterInterface:
    """
    Create a rate limiter with the specified backend.

    Args:
        backend: Backend type (MEMORY, REDIS, or AUTO)
        redis_url: Redis connection URL (only used for REDIS backend)
        key_prefix: Key prefix for Redis storage (only used for REDIS backend)
        **settings: Rate limiter settings (global_limit, global_period, tool_limits)

    Returns:
        Rate limiter instance implementing RateLimiterInterface

    Example:
        # Memory-backed (single instance)
        limiter = await create_rate_limiter(
            backend=WrapperBackend.MEMORY,
            global_limit=100,
            global_period=60.0,
            tool_limits={"expensive_api": (10, 60.0)},
        )

        # Redis-backed (distributed)
        limiter = await create_rate_limiter(
            backend=WrapperBackend.REDIS,
            redis_url="redis://localhost:6379/0",
            global_limit=100,
            global_period=60.0,
        )
    """
    # Determine actual backend
    actual_backend = backend
    if backend == WrapperBackend.AUTO:
        actual_backend = WrapperBackend.REDIS if _check_redis_available() else WrapperBackend.MEMORY
        logger.debug(f"Auto-detected backend: {actual_backend.value}")

    if actual_backend == WrapperBackend.REDIS:
        if not _check_redis_available():
            raise ImportError("Redis package not installed. Install with: pip install chuk-tool-processor[redis]")

        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            create_redis_rate_limiter,
        )

        limiter: RedisRateLimiter = await create_redis_rate_limiter(
            redis_url=redis_url,
            global_limit=settings.get("global_limit"),
            global_period=settings.get("global_period", 60.0),
            tool_limits=settings.get("tool_limits"),
            key_prefix=key_prefix,
        )
        logger.info(f"Created Redis rate limiter: {redis_url}")
        return limiter

    else:
        # Memory-backed rate limiter
        limiter_impl = RateLimiter(
            global_limit=settings.get("global_limit"),
            global_period=settings.get("global_period", 60.0),
            tool_limits=settings.get("tool_limits"),
        )
        logger.info("Created in-memory rate limiter")
        return limiter_impl


async def create_production_executor(
    strategy: Any,
    *,
    circuit_breaker_backend: WrapperBackend = WrapperBackend.MEMORY,
    rate_limiter_backend: WrapperBackend = WrapperBackend.MEMORY,
    redis_url: str = "redis://localhost:6379/0",
    circuit_breaker_settings: CircuitBreakerSettings | None = None,
    rate_limiter_settings: RateLimiterSettings | None = None,
    enable_circuit_breaker: bool = True,
    enable_rate_limiter: bool = True,
) -> Any:
    """
    Create a production-ready executor with circuit breaker and rate limiting.

    This is a convenience function that wraps a strategy with production features.

    Args:
        strategy: The underlying execution strategy
        circuit_breaker_backend: Backend for circuit breaker
        rate_limiter_backend: Backend for rate limiter
        redis_url: Redis URL for distributed backends
        circuit_breaker_settings: Circuit breaker configuration
        rate_limiter_settings: Rate limiter configuration
        enable_circuit_breaker: Whether to enable circuit breaker
        enable_rate_limiter: Whether to enable rate limiting

    Returns:
        Wrapped executor with production features

    Example:
        from chuk_tool_processor.execution.strategies import InProcessStrategy
        from chuk_tool_processor.execution.wrappers.factory import (
            create_production_executor,
            WrapperBackend,
            CircuitBreakerSettings,
            RateLimiterSettings,
        )

        strategy = InProcessStrategy(registry)

        # Single-instance deployment
        executor = await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.MEMORY,
            rate_limiter_backend=WrapperBackend.MEMORY,
        )

        # Distributed deployment
        executor = await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.REDIS,
            rate_limiter_backend=WrapperBackend.REDIS,
            redis_url="redis://localhost:6379/0",
        )
    """
    wrapped = strategy

    # Determine actual backends
    actual_cb_backend = circuit_breaker_backend
    if circuit_breaker_backend == WrapperBackend.AUTO:
        actual_cb_backend = WrapperBackend.REDIS if _check_redis_available() else WrapperBackend.MEMORY

    actual_rl_backend = rate_limiter_backend
    if rate_limiter_backend == WrapperBackend.AUTO:
        actual_rl_backend = WrapperBackend.REDIS if _check_redis_available() else WrapperBackend.MEMORY

    # Apply circuit breaker first (inner wrapper, closest to execution)
    if enable_circuit_breaker:
        cb_settings = circuit_breaker_settings or CircuitBreakerSettings()

        if actual_cb_backend == WrapperBackend.REDIS:
            if not _check_redis_available():
                raise ImportError("Redis package not installed. Install with: pip install chuk-tool-processor[redis]")

            from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
                RedisCircuitBreakerConfig,
                create_redis_circuit_breaker_executor,
            )

            # Build Redis config
            redis_config = RedisCircuitBreakerConfig(
                failure_threshold=cb_settings.failure_threshold,
                success_threshold=cb_settings.success_threshold,
                reset_timeout=cb_settings.reset_timeout,
                half_open_max_calls=cb_settings.half_open_max_calls,
                failure_window=cb_settings.failure_window,
            )

            # Convert tool_configs for Redis
            redis_tool_configs = None
            if cb_settings.tool_configs:
                redis_tool_configs = {
                    tool: RedisCircuitBreakerConfig(**cfg) for tool, cfg in cb_settings.tool_configs.items()
                }

            wrapped = await create_redis_circuit_breaker_executor(
                wrapped,
                redis_url=redis_url,
                default_config=redis_config,
                tool_configs=redis_tool_configs,
            )
            logger.info(f"Created Redis circuit breaker executor: {redis_url}")
        else:
            # Memory-backed circuit breaker
            cb_config = CircuitBreakerConfig(
                failure_threshold=cb_settings.failure_threshold,
                success_threshold=cb_settings.success_threshold,
                reset_timeout=cb_settings.reset_timeout,
                half_open_max_calls=cb_settings.half_open_max_calls,
            )

            # Convert tool_configs
            tool_configs = None
            if cb_settings.tool_configs:
                tool_configs = {tool: CircuitBreakerConfig(**cfg) for tool, cfg in cb_settings.tool_configs.items()}

            wrapped = CircuitBreakerExecutor(
                wrapped,
                default_config=cb_config,
                tool_configs=tool_configs,
            )
            logger.info("Created in-memory circuit breaker executor")

    # Apply rate limiting (outer wrapper)
    if enable_rate_limiter:
        rl_settings = rate_limiter_settings or RateLimiterSettings()

        if actual_rl_backend == WrapperBackend.REDIS:
            if not _check_redis_available():
                raise ImportError("Redis package not installed. Install with: pip install chuk-tool-processor[redis]")

            # For Redis, create the rate limiter and wrap
            limiter = await create_rate_limiter(
                backend=WrapperBackend.REDIS,
                redis_url=redis_url,
                global_limit=rl_settings.global_limit,
                global_period=rl_settings.global_period,
                tool_limits=rl_settings.tool_limits,
            )
            wrapped = RateLimitedToolExecutor(wrapped, limiter)
            logger.info(f"Created Redis rate limiter: {redis_url}")
        else:
            # Memory-backed rate limiter
            limiter = RateLimiter(
                global_limit=rl_settings.global_limit,
                global_period=rl_settings.global_period,
                tool_limits=rl_settings.tool_limits,
            )
            wrapped = RateLimitedToolExecutor(wrapped, limiter)
            logger.info("Created in-memory rate limiter")

    logger.info(
        f"Created production executor: "
        f"circuit_breaker={enable_circuit_breaker} ({actual_cb_backend.value}), "
        f"rate_limiter={enable_rate_limiter} ({actual_rl_backend.value})"
    )

    return wrapped
