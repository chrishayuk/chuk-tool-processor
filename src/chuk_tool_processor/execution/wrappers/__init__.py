# chuk_tool_processor/execution/wrappers/__init__.py
"""Execution wrappers for adding production features to tool execution."""

from chuk_tool_processor.execution.wrappers.caching import (
    CacheInterface,
    CachingToolExecutor,
    InMemoryCache,
    cacheable,
)
from chuk_tool_processor.execution.wrappers.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerExecutor,
    CircuitState,
)

# Factory functions for configurable backends
from chuk_tool_processor.execution.wrappers.factory import (
    CircuitBreakerInterface,
    CircuitBreakerSettings,
    RateLimiterInterface,
    RateLimiterSettings,
    WrapperBackend,
    create_circuit_breaker,
    create_production_executor,
    create_rate_limiter,
)
from chuk_tool_processor.execution.wrappers.rate_limiting import (
    RateLimitedToolExecutor,
    RateLimiter,
)
from chuk_tool_processor.execution.wrappers.retry import (
    RetryableToolExecutor,
    RetryConfig,
    retryable,
)

# Redis-backed distributed implementations (optional, requires redis package)
try:
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreaker as RedisCircuitBreaker,
    )
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerConfig as RedisCircuitBreakerConfig,
    )
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        RedisCircuitBreakerExecutor as RedisCircuitBreakerExecutor,
    )
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        create_redis_circuit_breaker as create_redis_circuit_breaker,
    )
    from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
        create_redis_circuit_breaker_executor as create_redis_circuit_breaker_executor,
    )
    from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
        RedisRateLimiter as RedisRateLimiter,
    )
    from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
        create_redis_rate_limiter as create_redis_rate_limiter,
    )

    _redis_available = True
except ImportError:
    _redis_available = False

__all__ = [
    # Caching
    "CacheInterface",
    "CachingToolExecutor",
    "InMemoryCache",
    "cacheable",
    # Circuit breaker
    "CircuitBreakerConfig",
    "CircuitBreakerExecutor",
    "CircuitState",
    # Rate limiting
    "RateLimitedToolExecutor",
    "RateLimiter",
    # Retry
    "RetryableToolExecutor",
    "RetryConfig",
    "retryable",
    # Factory functions
    "WrapperBackend",
    "CircuitBreakerInterface",
    "CircuitBreakerSettings",
    "RateLimiterInterface",
    "RateLimiterSettings",
    "create_circuit_breaker",
    "create_rate_limiter",
    "create_production_executor",
]

# Add Redis exports if available
if _redis_available:
    __all__.extend(
        [
            # Redis circuit breaker
            "RedisCircuitBreaker",
            "RedisCircuitBreakerConfig",
            "RedisCircuitBreakerExecutor",
            "create_redis_circuit_breaker",
            "create_redis_circuit_breaker_executor",
            # Redis rate limiting
            "RedisRateLimiter",
            "create_redis_rate_limiter",
        ]
    )
