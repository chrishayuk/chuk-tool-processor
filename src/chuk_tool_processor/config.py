# src/chuk_tool_processor/config.py
"""
Configuration module for chuk-tool-processor.

Provides environment-based configuration for all features including
registry, rate limiting, circuit breakers, and caching with support
for both in-memory and Redis backends.

Environment Variables:
    # Registry
    CHUK_REGISTRY_BACKEND: "memory" | "redis" (default: "memory")

    # Backend selection for resilience (rate limiting, circuit breaker)
    CHUK_RESILIENCE_BACKEND: "memory" | "redis" | "auto" (default: "memory")

    # Redis connection (shared by registry and resilience)
    CHUK_REDIS_URL: Redis connection URL (default: "redis://localhost:6379/0")
    CHUK_REDIS_KEY_PREFIX: Key prefix for Redis (default: "chuk")

    # Circuit breaker
    CHUK_CIRCUIT_BREAKER_ENABLED: "true" | "false" (default: "false")
    CHUK_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int (default: 5)
    CHUK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int (default: 2)
    CHUK_CIRCUIT_BREAKER_RESET_TIMEOUT: float seconds (default: 60.0)
    CHUK_CIRCUIT_BREAKER_FAILURE_WINDOW: float seconds (default: 60.0)

    # Rate limiting
    CHUK_RATE_LIMIT_ENABLED: "true" | "false" (default: "false")
    CHUK_RATE_LIMIT_GLOBAL: int requests per period (default: None)
    CHUK_RATE_LIMIT_PERIOD: float seconds (default: 60.0)
    CHUK_RATE_LIMIT_TOOLS: "tool1:limit:period,tool2:limit:period" (default: "")

    # Caching
    CHUK_CACHE_ENABLED: "true" | "false" (default: "true")
    CHUK_CACHE_TTL: int seconds (default: 300)

    # Retries
    CHUK_RETRY_ENABLED: "true" | "false" (default: "true")
    CHUK_RETRY_MAX: int (default: 3)

    # Execution
    CHUK_DEFAULT_TIMEOUT: float seconds (default: 10.0)
    CHUK_MAX_CONCURRENCY: int (default: None/unlimited)

Example:
    # Set environment variables for distributed deployment
    export CHUK_REGISTRY_BACKEND=redis
    export CHUK_RESILIENCE_BACKEND=redis
    export CHUK_REDIS_URL=redis://localhost:6379/0
    export CHUK_CIRCUIT_BREAKER_ENABLED=true
    export CHUK_RATE_LIMIT_ENABLED=true
    export CHUK_RATE_LIMIT_GLOBAL=100

    # Use in code - simple way
    from chuk_tool_processor import ToolProcessor
    from chuk_tool_processor.config import ProcessorConfig

    config = ProcessorConfig.from_env()
    processor = await config.create_processor()

    # Or manual way
    registry = await config.create_registry()
    executor = await config.create_executor(strategy)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BackendType(str, Enum):
    """Backend type for registry and resilience features."""

    MEMORY = "memory"
    REDIS = "redis"
    AUTO = "auto"  # Only for resilience - auto-detect Redis availability


# Alias for backwards compatibility
ResilienceBackend = BackendType


def _get_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


def _get_int(key: str, default: int | None = None) -> int | None:
    """Get integer from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(key: str, default: float | None = None) -> float | None:
    """Get float from environment variable."""
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    enabled: bool = False
    failure_threshold: int = 5
    success_threshold: int = 2
    reset_timeout: float = 60.0
    failure_window: float = 60.0
    half_open_max_calls: int = 1

    @classmethod
    def from_env(cls) -> CircuitBreakerConfig:
        """Load circuit breaker config from environment."""
        return cls(
            enabled=_get_bool("CHUK_CIRCUIT_BREAKER_ENABLED", False),
            failure_threshold=_get_int("CHUK_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5) or 5,
            success_threshold=_get_int("CHUK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD", 2) or 2,
            reset_timeout=_get_float("CHUK_CIRCUIT_BREAKER_RESET_TIMEOUT", 60.0) or 60.0,
            failure_window=_get_float("CHUK_CIRCUIT_BREAKER_FAILURE_WINDOW", 60.0) or 60.0,
            half_open_max_calls=_get_int("CHUK_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS", 1) or 1,
        )


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    enabled: bool = False
    global_limit: int | None = None
    global_period: float = 60.0
    tool_limits: dict[str, tuple[int, float]] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> RateLimitConfig:
        """Load rate limit config from environment."""
        # Parse tool limits from CHUK_RATE_LIMIT_TOOLS (format: "tool1:10:60,tool2:5:30")
        tool_limits: dict[str, tuple[int, float]] = {}
        tool_limits_str = os.environ.get("CHUK_RATE_LIMIT_TOOLS", "")
        if tool_limits_str:
            import contextlib

            for item in tool_limits_str.split(","):
                parts = item.strip().split(":")
                if len(parts) == 3:
                    tool_name, limit, period = parts
                    with contextlib.suppress(ValueError):
                        tool_limits[tool_name] = (int(limit), float(period))

        return cls(
            enabled=_get_bool("CHUK_RATE_LIMIT_ENABLED", False),
            global_limit=_get_int("CHUK_RATE_LIMIT_GLOBAL"),
            global_period=_get_float("CHUK_RATE_LIMIT_PERIOD", 60.0) or 60.0,
            tool_limits=tool_limits,
        )


@dataclass
class CacheConfig:
    """Caching configuration."""

    enabled: bool = True
    ttl: int = 300

    @classmethod
    def from_env(cls) -> CacheConfig:
        """Load cache config from environment."""
        return cls(
            enabled=_get_bool("CHUK_CACHE_ENABLED", True),
            ttl=_get_int("CHUK_CACHE_TTL", 300) or 300,
        )


@dataclass
class RetryConfig:
    """Retry configuration."""

    enabled: bool = True
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0

    @classmethod
    def from_env(cls) -> RetryConfig:
        """Load retry config from environment."""
        return cls(
            enabled=_get_bool("CHUK_RETRY_ENABLED", True),
            max_retries=_get_int("CHUK_RETRY_MAX", 3) or 3,
            base_delay=_get_float("CHUK_RETRY_BASE_DELAY", 1.0) or 1.0,
            max_delay=_get_float("CHUK_RETRY_MAX_DELAY", 60.0) or 60.0,
            exponential_base=_get_float("CHUK_RETRY_EXPONENTIAL_BASE", 2.0) or 2.0,
        )


@dataclass
class RegistryConfig:
    """Registry configuration."""

    backend: BackendType = BackendType.MEMORY
    redis_url: str = "redis://localhost:6379/0"
    key_prefix: str = "chuk"
    local_cache_ttl: float = 60.0

    @classmethod
    def from_env(cls) -> RegistryConfig:
        """Load registry config from environment."""
        backend_str = os.environ.get("CHUK_REGISTRY_BACKEND", "memory").lower()
        try:
            backend = BackendType(backend_str)
        except ValueError:
            backend = BackendType.MEMORY

        return cls(
            backend=backend,
            redis_url=os.environ.get("CHUK_REDIS_URL", "redis://localhost:6379/0"),
            key_prefix=os.environ.get("CHUK_REDIS_KEY_PREFIX", "chuk"),
            local_cache_ttl=_get_float("CHUK_REGISTRY_LOCAL_CACHE_TTL", 60.0) or 60.0,
        )


@dataclass
class ProcessorConfig:
    """
    Complete configuration for ToolProcessor with environment variable support.

    This class consolidates all configuration options and provides easy loading
    from environment variables. It supports both in-memory and Redis backends
    for registry and resilience features.

    Example:
        # Load from environment
        config = ProcessorConfig.from_env()

        # Simple usage - creates everything for you
        processor = await config.create_processor()
        async with processor:
            results = await processor.process(tool_calls)

        # Or create programmatically
        config = ProcessorConfig(
            registry=RegistryConfig(backend=BackendType.REDIS),
            resilience_backend=BackendType.REDIS,
            redis_url="redis://localhost:6379/0",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            rate_limit=RateLimitConfig(enabled=True, global_limit=100),
        )
        processor = await config.create_processor()
    """

    # Registry configuration
    registry: RegistryConfig = field(default_factory=RegistryConfig)

    # Resilience backend selection (rate limiting, circuit breaker)
    resilience_backend: BackendType = BackendType.MEMORY

    # Redis connection (shared)
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "chuk"

    # Execution settings
    default_timeout: float = 10.0
    max_concurrency: int | None = None

    # Feature configs
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Backwards compatibility alias
    @property
    def backend(self) -> BackendType:
        """Alias for resilience_backend (backwards compatibility)."""
        return self.resilience_backend

    @classmethod
    def from_env(cls) -> ProcessorConfig:
        """
        Load configuration from environment variables.

        Returns:
            ProcessorConfig with values from environment or defaults.
        """
        resilience_str = os.environ.get("CHUK_RESILIENCE_BACKEND", "memory").lower()
        try:
            resilience_backend = BackendType(resilience_str)
        except ValueError:
            resilience_backend = BackendType.MEMORY

        redis_url = os.environ.get("CHUK_REDIS_URL", "redis://localhost:6379/0")
        redis_key_prefix = os.environ.get("CHUK_REDIS_KEY_PREFIX", "chuk")

        # Registry config inherits redis settings
        registry_config = RegistryConfig.from_env()
        registry_config.redis_url = redis_url
        registry_config.key_prefix = redis_key_prefix

        return cls(
            registry=registry_config,
            resilience_backend=resilience_backend,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
            default_timeout=_get_float("CHUK_DEFAULT_TIMEOUT", 10.0) or 10.0,
            max_concurrency=_get_int("CHUK_MAX_CONCURRENCY"),
            circuit_breaker=CircuitBreakerConfig.from_env(),
            rate_limit=RateLimitConfig.from_env(),
            cache=CacheConfig.from_env(),
            retry=RetryConfig.from_env(),
        )

    def to_processor_kwargs(self) -> dict[str, Any]:
        """
        Convert config to kwargs for ToolProcessor.__init__.

        Returns:
            Dictionary of keyword arguments for ToolProcessor.

        Note:
            This returns kwargs for the standard ToolProcessor which uses
            in-memory backends. For Redis backends, use create_processor()
            instead.
        """
        return {
            "default_timeout": self.default_timeout,
            "max_concurrency": self.max_concurrency,
            "enable_caching": self.cache.enabled,
            "cache_ttl": self.cache.ttl,
            "enable_rate_limiting": self.rate_limit.enabled,
            "global_rate_limit": self.rate_limit.global_limit,
            "tool_rate_limits": self.rate_limit.tool_limits or None,
            "enable_retries": self.retry.enabled,
            "max_retries": self.retry.max_retries,
            "enable_circuit_breaker": self.circuit_breaker.enabled,
            "circuit_breaker_threshold": self.circuit_breaker.failure_threshold,
            "circuit_breaker_timeout": self.circuit_breaker.reset_timeout,
        }

    def uses_redis(self) -> bool:
        """Check if this config requires Redis for resilience features."""
        if self.resilience_backend == BackendType.REDIS:
            return True
        if self.resilience_backend == BackendType.AUTO:
            try:
                import redis  # noqa: F401

                return True
            except ImportError:
                return False
        return False

    def registry_uses_redis(self) -> bool:
        """Check if registry uses Redis."""
        return self.registry.backend == BackendType.REDIS

    async def create_registry(self) -> Any:
        """
        Create a registry based on configuration.

        Returns:
            ToolRegistryInterface implementation.

        Example:
            config = ProcessorConfig.from_env()
            registry = await config.create_registry()
        """
        from chuk_tool_processor.registry.providers import get_registry

        if self.registry.backend == BackendType.REDIS:
            return await get_registry(
                "redis",
                redis_url=self.registry.redis_url,
                key_prefix=self.registry.key_prefix,
                local_cache_ttl=self.registry.local_cache_ttl,
            )
        return await get_registry("memory")

    async def create_processor(self) -> Any:
        """
        Create a fully configured ToolProcessor.

        This is the recommended way to create a processor with Redis support.
        It handles all the wiring of registry, strategy, and resilience features.

        Returns:
            Configured ToolProcessor instance.

        Example:
            config = ProcessorConfig.from_env()
            processor = await config.create_processor()
            async with processor:
                results = await processor.process(tool_calls)
        """
        from chuk_tool_processor.core.processor import ToolProcessor
        from chuk_tool_processor.execution.strategies.inprocess_strategy import (
            InProcessStrategy,
        )

        # Create registry
        registry = await self.create_registry()

        # If using Redis for resilience, we need to create a custom executor
        if self.uses_redis() and (self.circuit_breaker.enabled or self.rate_limit.enabled):
            # Create base strategy
            strategy = InProcessStrategy(
                registry=registry,
                default_timeout=self.default_timeout,
                max_concurrency=self.max_concurrency,
            )

            # Wrap with Redis-backed resilience features
            executor = await create_executor(strategy, self)

            # Create processor with pre-configured executor
            # Note: We disable the built-in wrappers since we've already applied them
            return ToolProcessor(
                registry=registry,
                strategy=executor,  # Use our wrapped executor as the strategy
                default_timeout=self.default_timeout,
                max_concurrency=self.max_concurrency,
                enable_caching=self.cache.enabled,
                cache_ttl=self.cache.ttl,
                enable_rate_limiting=False,  # Already applied via Redis
                enable_retries=self.retry.enabled,
                max_retries=self.retry.max_retries,
                enable_circuit_breaker=False,  # Already applied via Redis
            )

        # Standard in-memory configuration
        return ToolProcessor(
            registry=registry,
            **self.to_processor_kwargs(),
        )


async def create_executor(
    strategy: Any,
    config: ProcessorConfig | None = None,
) -> Any:
    """
    Create an executor with resilience wrappers based on configuration.

    This is the recommended way to create a production executor with
    Redis support.

    Args:
        strategy: Base execution strategy (InProcessStrategy or SubprocessStrategy)
        config: Configuration to use. If None, loads from environment.

    Returns:
        Wrapped executor with configured resilience features.

    Example:
        from chuk_tool_processor import InProcessStrategy, get_default_registry
        from chuk_tool_processor.config import create_executor, ProcessorConfig

        registry = await get_default_registry()
        strategy = InProcessStrategy(registry)

        # Use environment config
        executor = await create_executor(strategy)

        # Or use explicit config
        config = ProcessorConfig(
            backend=ResilienceBackend.REDIS,
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
        executor = await create_executor(strategy, config)
    """
    if config is None:
        config = ProcessorConfig.from_env()

    # If using Redis backend
    if config.uses_redis():
        from chuk_tool_processor.execution.wrappers.factory import (
            CircuitBreakerSettings,
            RateLimiterSettings,
            WrapperBackend,
            create_production_executor,
        )

        cb_settings = None
        if config.circuit_breaker.enabled:
            cb_settings = CircuitBreakerSettings(
                failure_threshold=config.circuit_breaker.failure_threshold,
                success_threshold=config.circuit_breaker.success_threshold,
                reset_timeout=config.circuit_breaker.reset_timeout,
                half_open_max_calls=config.circuit_breaker.half_open_max_calls,
                failure_window=config.circuit_breaker.failure_window,
            )

        rl_settings = None
        if config.rate_limit.enabled:
            rl_settings = RateLimiterSettings(
                global_limit=config.rate_limit.global_limit,
                global_period=config.rate_limit.global_period,
                tool_limits=config.rate_limit.tool_limits,
            )

        return await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.REDIS,
            rate_limiter_backend=WrapperBackend.REDIS,
            redis_url=config.redis_url,
            circuit_breaker_settings=cb_settings,
            rate_limiter_settings=rl_settings,
            enable_circuit_breaker=config.circuit_breaker.enabled,
            enable_rate_limiter=config.rate_limit.enabled,
        )

    # Memory backend - use standard wrappers
    from chuk_tool_processor.execution.wrappers.circuit_breaker import (
        CircuitBreakerConfig as CBConfig,
    )
    from chuk_tool_processor.execution.wrappers.circuit_breaker import (
        CircuitBreakerExecutor,
    )
    from chuk_tool_processor.execution.wrappers.rate_limiting import (
        RateLimitedToolExecutor,
        RateLimiter,
    )

    executor = strategy

    if config.circuit_breaker.enabled:
        cb_config = CBConfig(
            failure_threshold=config.circuit_breaker.failure_threshold,
            success_threshold=config.circuit_breaker.success_threshold,
            reset_timeout=config.circuit_breaker.reset_timeout,
            half_open_max_calls=config.circuit_breaker.half_open_max_calls,
        )
        executor = CircuitBreakerExecutor(executor, default_config=cb_config)

    if config.rate_limit.enabled:
        limiter = RateLimiter(
            global_limit=config.rate_limit.global_limit,
            global_period=config.rate_limit.global_period,
            tool_limits=config.rate_limit.tool_limits,
        )
        executor = RateLimitedToolExecutor(executor, limiter)

    return executor


# Convenience exports
__all__ = [
    # Enums
    "BackendType",
    "ResilienceBackend",  # Alias for backwards compatibility
    # Config classes
    "RegistryConfig",
    "CircuitBreakerConfig",
    "RateLimitConfig",
    "CacheConfig",
    "RetryConfig",
    "ProcessorConfig",
    # Factory functions
    "create_executor",
]
