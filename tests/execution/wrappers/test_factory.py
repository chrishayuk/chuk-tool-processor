# tests/execution/wrappers/test_factory.py
"""
Tests for the factory module for creating circuit breakers and rate limiters.

These tests cover both memory and Redis backends using fakeredis for in-memory
Redis simulation.
"""

import pytest
import pytest_asyncio

# Check if redis and fakeredis are available
pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")

from chuk_tool_processor.execution.wrappers.factory import (  # noqa: E402
    CircuitBreakerSettings,
    RateLimiterSettings,
    WrapperBackend,
    _check_redis_available,
    create_circuit_breaker,
    create_production_executor,
    create_rate_limiter,
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


class DummyStrategy:
    """Simple strategy for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0

    async def execute(self, calls, timeout=None, use_cache=True):
        self.call_count += len(calls)
        results = []
        for c in calls:
            if self.should_fail:
                results.append(
                    ToolResult(
                        tool=c.tool,
                        result=None,
                        error="Simulated failure",
                    )
                )
            else:
                results.append(
                    ToolResult(
                        tool=c.tool,
                        result={"success": True},
                        error=None,
                    )
                )
        return results


# --------------------------------------------------------------------------- #
# Tests - WrapperBackend Enum
# --------------------------------------------------------------------------- #
def test_wrapper_backend_values():
    """Test WrapperBackend enum values."""
    assert WrapperBackend.MEMORY.value == "memory"
    assert WrapperBackend.REDIS.value == "redis"
    assert WrapperBackend.AUTO.value == "auto"


def test_check_redis_available():
    """Test Redis availability check."""
    # Since we have redis installed for tests, this should return True
    assert _check_redis_available() is True


# --------------------------------------------------------------------------- #
# Tests - CircuitBreakerSettings
# --------------------------------------------------------------------------- #
def test_circuit_breaker_settings_defaults():
    """Test CircuitBreakerSettings default values."""
    settings = CircuitBreakerSettings()
    assert settings.failure_threshold == 5
    assert settings.success_threshold == 2
    assert settings.reset_timeout == 60.0
    assert settings.half_open_max_calls == 1
    assert settings.failure_window == 60.0
    assert settings.tool_configs is None


def test_circuit_breaker_settings_custom():
    """Test CircuitBreakerSettings custom values."""
    settings = CircuitBreakerSettings(
        failure_threshold=10,
        success_threshold=3,
        reset_timeout=30.0,
        half_open_max_calls=2,
        failure_window=120.0,
        tool_configs={"test_tool": {"failure_threshold": 3}},
    )
    assert settings.failure_threshold == 10
    assert settings.success_threshold == 3
    assert settings.reset_timeout == 30.0
    assert settings.half_open_max_calls == 2
    assert settings.failure_window == 120.0
    assert "test_tool" in settings.tool_configs


# --------------------------------------------------------------------------- #
# Tests - RateLimiterSettings
# --------------------------------------------------------------------------- #
def test_rate_limiter_settings_defaults():
    """Test RateLimiterSettings default values."""
    settings = RateLimiterSettings()
    assert settings.global_limit is None
    assert settings.global_period == 60.0
    assert settings.tool_limits is None


def test_rate_limiter_settings_custom():
    """Test RateLimiterSettings custom values."""
    settings = RateLimiterSettings(
        global_limit=100,
        global_period=30.0,
        tool_limits={"api": (10, 60.0)},
    )
    assert settings.global_limit == 100
    assert settings.global_period == 30.0
    assert settings.tool_limits["api"] == (10, 60.0)


# --------------------------------------------------------------------------- #
# Tests - create_circuit_breaker (Memory)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_circuit_breaker_memory():
    """Test creating a memory-backed circuit breaker."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=5,
        reset_timeout=60.0,
    )
    assert breaker is not None
    # Memory breaker is a CircuitBreakerExecutor


@pytest.mark.asyncio
async def test_create_circuit_breaker_memory_with_tool_configs():
    """Test creating memory circuit breaker with tool-specific configs."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=5,
        tool_configs={"expensive_tool": {"failure_threshold": 2, "reset_timeout": 30.0}},
    )
    assert breaker is not None


# --------------------------------------------------------------------------- #
# Tests - create_circuit_breaker (Redis)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_circuit_breaker_redis(fake_redis, monkeypatch):
    """Test creating a Redis-backed circuit breaker."""
    from chuk_tool_processor.execution.wrappers import redis_circuit_breaker

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
        )

        return RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
            tool_configs=kwargs.get("tool_configs"),
            key_prefix=kwargs.get("key_prefix", "circuitbreaker"),
        )

    monkeypatch.setattr(redis_circuit_breaker, "create_redis_circuit_breaker", mock_create)

    breaker = await create_circuit_breaker(
        backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        failure_threshold=5,
        reset_timeout=60.0,
    )
    assert breaker is not None


@pytest.mark.asyncio
async def test_create_circuit_breaker_redis_with_tool_configs(fake_redis, monkeypatch):
    """Test creating Redis circuit breaker with tool-specific configs."""
    from chuk_tool_processor.execution.wrappers import redis_circuit_breaker

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
        )

        return RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
            tool_configs=kwargs.get("tool_configs"),
            key_prefix=kwargs.get("key_prefix", "circuitbreaker"),
        )

    monkeypatch.setattr(redis_circuit_breaker, "create_redis_circuit_breaker", mock_create)

    breaker = await create_circuit_breaker(
        backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        failure_threshold=5,
        tool_configs={"expensive_tool": {"failure_threshold": 2}},
    )
    assert breaker is not None


# --------------------------------------------------------------------------- #
# Tests - create_circuit_breaker (Auto)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_circuit_breaker_auto(fake_redis, monkeypatch):
    """Test creating circuit breaker with AUTO backend detection."""
    from chuk_tool_processor.execution.wrappers import redis_circuit_breaker

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
        )

        return RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
        )

    monkeypatch.setattr(redis_circuit_breaker, "create_redis_circuit_breaker", mock_create)

    # With Redis available, AUTO should use Redis
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.AUTO,
        failure_threshold=5,
    )
    assert breaker is not None


# --------------------------------------------------------------------------- #
# Tests - create_rate_limiter (Memory)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_rate_limiter_memory():
    """Test creating a memory-backed rate limiter."""
    limiter = await create_rate_limiter(
        backend=WrapperBackend.MEMORY,
        global_limit=100,
        global_period=60.0,
    )
    assert limiter is not None


@pytest.mark.asyncio
async def test_create_rate_limiter_memory_with_tool_limits():
    """Test creating memory rate limiter with tool-specific limits."""
    limiter = await create_rate_limiter(
        backend=WrapperBackend.MEMORY,
        global_limit=100,
        tool_limits={"expensive_api": (10, 60.0)},
    )
    assert limiter is not None


@pytest.mark.asyncio
async def test_create_rate_limiter_memory_no_limit():
    """Test creating memory rate limiter without global limit."""
    limiter = await create_rate_limiter(
        backend=WrapperBackend.MEMORY,
        global_limit=None,
    )
    assert limiter is not None


# --------------------------------------------------------------------------- #
# Tests - create_rate_limiter (Redis)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_rate_limiter_redis(fake_redis, monkeypatch):
    """Test creating a Redis-backed rate limiter."""
    from chuk_tool_processor.execution.wrappers import redis_rate_limiting

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
            key_prefix=kwargs.get("key_prefix", "ratelimit"),
        )

    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_create)

    limiter = await create_rate_limiter(
        backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        global_limit=100,
        global_period=60.0,
    )
    assert limiter is not None


@pytest.mark.asyncio
async def test_create_rate_limiter_redis_with_tool_limits(fake_redis, monkeypatch):
    """Test creating Redis rate limiter with tool-specific limits."""
    from chuk_tool_processor.execution.wrappers import redis_rate_limiting

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
            key_prefix=kwargs.get("key_prefix", "ratelimit"),
        )

    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_create)

    limiter = await create_rate_limiter(
        backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        global_limit=100,
        tool_limits={"api": (10, 60.0)},
    )
    assert limiter is not None


# --------------------------------------------------------------------------- #
# Tests - create_rate_limiter (Auto)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_rate_limiter_auto(fake_redis, monkeypatch):
    """Test creating rate limiter with AUTO backend detection."""
    from chuk_tool_processor.execution.wrappers import redis_rate_limiting

    async def mock_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
        )

    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_create)

    # With Redis available, AUTO should use Redis
    limiter = await create_rate_limiter(
        backend=WrapperBackend.AUTO,
        global_limit=100,
    )
    assert limiter is not None


# --------------------------------------------------------------------------- #
# Tests - create_production_executor (Memory)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_production_executor_memory_defaults():
    """Test creating production executor with memory backend defaults."""
    strategy = DummyStrategy()

    executor = await create_production_executor(strategy)

    assert executor is not None
    # Should have both circuit breaker and rate limiter enabled by default


@pytest.mark.asyncio
async def test_create_production_executor_memory_with_settings():
    """Test creating production executor with custom settings."""
    strategy = DummyStrategy()

    cb_settings = CircuitBreakerSettings(
        failure_threshold=3,
        reset_timeout=30.0,
    )
    rl_settings = RateLimiterSettings(
        global_limit=50,
        global_period=30.0,
    )

    executor = await create_production_executor(
        strategy,
        circuit_breaker_settings=cb_settings,
        rate_limiter_settings=rl_settings,
    )

    assert executor is not None


@pytest.mark.asyncio
async def test_create_production_executor_memory_circuit_breaker_only():
    """Test creating production executor with only circuit breaker."""
    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        enable_circuit_breaker=True,
        enable_rate_limiter=False,
    )

    assert executor is not None


@pytest.mark.asyncio
async def test_create_production_executor_memory_rate_limiter_only():
    """Test creating production executor with only rate limiter."""
    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        enable_circuit_breaker=False,
        enable_rate_limiter=True,
    )

    assert executor is not None


@pytest.mark.asyncio
async def test_create_production_executor_memory_no_wrappers():
    """Test creating production executor with no wrappers."""
    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        enable_circuit_breaker=False,
        enable_rate_limiter=False,
    )

    # Should return the original strategy
    assert executor is strategy


@pytest.mark.asyncio
async def test_create_production_executor_with_tool_configs():
    """Test creating production executor with per-tool configurations."""
    strategy = DummyStrategy()

    cb_settings = CircuitBreakerSettings(
        failure_threshold=5,
        tool_configs={"expensive_tool": {"failure_threshold": 2, "reset_timeout": 15.0}},
    )
    rl_settings = RateLimiterSettings(
        global_limit=100,
        tool_limits={"expensive_tool": (5, 60.0)},
    )

    executor = await create_production_executor(
        strategy,
        circuit_breaker_settings=cb_settings,
        rate_limiter_settings=rl_settings,
    )

    assert executor is not None


# --------------------------------------------------------------------------- #
# Tests - create_production_executor (Redis)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_production_executor_redis(fake_redis, monkeypatch):
    """Test creating production executor with Redis backends."""
    from chuk_tool_processor.execution.wrappers import (
        redis_circuit_breaker,
        redis_rate_limiting,
    )

    # Mock Redis circuit breaker executor
    async def mock_cb_executor(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerExecutor,
        )

        cb = RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
            tool_configs=kwargs.get("tool_configs"),
        )
        return RedisCircuitBreakerExecutor(args[0], cb)

    # Mock Redis rate limiter
    async def mock_rl_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
        )

    monkeypatch.setattr(
        redis_circuit_breaker,
        "create_redis_circuit_breaker_executor",
        mock_cb_executor,
    )
    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_rl_create)

    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        circuit_breaker_backend=WrapperBackend.REDIS,
        rate_limiter_backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
    )

    assert executor is not None


@pytest.mark.asyncio
async def test_create_production_executor_redis_with_settings(fake_redis, monkeypatch):
    """Test creating production executor with Redis backends and custom settings."""
    from chuk_tool_processor.execution.wrappers import (
        redis_circuit_breaker,
        redis_rate_limiting,
    )

    async def mock_cb_executor(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerExecutor,
        )

        cb = RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
            tool_configs=kwargs.get("tool_configs"),
        )
        return RedisCircuitBreakerExecutor(args[0], cb)

    async def mock_rl_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
        )

    monkeypatch.setattr(
        redis_circuit_breaker,
        "create_redis_circuit_breaker_executor",
        mock_cb_executor,
    )
    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_rl_create)

    strategy = DummyStrategy()

    cb_settings = CircuitBreakerSettings(
        failure_threshold=3,
        reset_timeout=30.0,
        failure_window=120.0,
    )
    rl_settings = RateLimiterSettings(
        global_limit=50,
        global_period=30.0,
        tool_limits={"api": (10, 60.0)},
    )

    executor = await create_production_executor(
        strategy,
        circuit_breaker_backend=WrapperBackend.REDIS,
        rate_limiter_backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        circuit_breaker_settings=cb_settings,
        rate_limiter_settings=rl_settings,
    )

    assert executor is not None


@pytest.mark.asyncio
async def test_create_production_executor_redis_with_tool_configs(fake_redis, monkeypatch):
    """Test creating production executor with Redis backends and tool configs."""
    from chuk_tool_processor.execution.wrappers import (
        redis_circuit_breaker,
        redis_rate_limiting,
    )

    async def mock_cb_executor(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerExecutor,
        )

        cb = RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
            tool_configs=kwargs.get("tool_configs"),
        )
        return RedisCircuitBreakerExecutor(args[0], cb)

    async def mock_rl_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
            tool_limits=kwargs.get("tool_limits"),
        )

    monkeypatch.setattr(
        redis_circuit_breaker,
        "create_redis_circuit_breaker_executor",
        mock_cb_executor,
    )
    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_rl_create)

    strategy = DummyStrategy()

    cb_settings = CircuitBreakerSettings(
        failure_threshold=5,
        tool_configs={
            "expensive_tool": {
                "failure_threshold": 2,
                "reset_timeout": 15.0,
                "failure_window": 30.0,
            }
        },
    )

    executor = await create_production_executor(
        strategy,
        circuit_breaker_backend=WrapperBackend.REDIS,
        rate_limiter_backend=WrapperBackend.REDIS,
        redis_url="redis://localhost:6379/0",
        circuit_breaker_settings=cb_settings,
    )

    assert executor is not None


# --------------------------------------------------------------------------- #
# Tests - create_production_executor (Auto)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_production_executor_auto(fake_redis, monkeypatch):
    """Test creating production executor with AUTO backend detection."""
    from chuk_tool_processor.execution.wrappers import (
        redis_circuit_breaker,
        redis_rate_limiting,
    )

    async def mock_cb_executor(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_circuit_breaker import (
            RedisCircuitBreaker,
            RedisCircuitBreakerConfig,
            RedisCircuitBreakerExecutor,
        )

        cb = RedisCircuitBreaker(
            fake_redis,
            default_config=kwargs.get("default_config") or RedisCircuitBreakerConfig(),
        )
        return RedisCircuitBreakerExecutor(args[0], cb)

    async def mock_rl_create(*args, **kwargs):
        from chuk_tool_processor.execution.wrappers.redis_rate_limiting import (
            RedisRateLimiter,
        )

        return RedisRateLimiter(
            fake_redis,
            global_limit=kwargs.get("global_limit"),
            global_period=kwargs.get("global_period", 60.0),
        )

    monkeypatch.setattr(
        redis_circuit_breaker,
        "create_redis_circuit_breaker_executor",
        mock_cb_executor,
    )
    monkeypatch.setattr(redis_rate_limiting, "create_redis_rate_limiter", mock_rl_create)

    strategy = DummyStrategy()

    # With Redis available, AUTO should use Redis
    executor = await create_production_executor(
        strategy,
        circuit_breaker_backend=WrapperBackend.AUTO,
        rate_limiter_backend=WrapperBackend.AUTO,
    )

    assert executor is not None


# --------------------------------------------------------------------------- #
# Tests - Execution with production executor
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_production_executor_execute_success():
    """Test executing through a memory production executor."""
    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        circuit_breaker_backend=WrapperBackend.MEMORY,
        rate_limiter_backend=WrapperBackend.MEMORY,
    )

    calls = [ToolCall(tool="test_tool", arguments={})]
    results = await executor.execute(calls)

    assert len(results) == 1
    assert results[0].error is None


@pytest.mark.asyncio
async def test_production_executor_execute_multiple():
    """Test executing multiple calls through production executor."""
    strategy = DummyStrategy()

    executor = await create_production_executor(
        strategy,
        enable_rate_limiter=False,  # Disable rate limiting for faster test
    )

    calls = [
        ToolCall(tool="tool1", arguments={}),
        ToolCall(tool="tool2", arguments={}),
        ToolCall(tool="tool3", arguments={}),
    ]
    results = await executor.execute(calls)

    assert len(results) == 3
    for r in results:
        assert r.error is None


# --------------------------------------------------------------------------- #
# Tests - MemoryCircuitBreaker (for coverage)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_memory_circuit_breaker_can_execute():
    """Test MemoryCircuitBreaker.can_execute method."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=3,
    )

    # Should be able to execute initially
    can_exec = await breaker.can_execute("test_tool")
    assert can_exec is True


@pytest.mark.asyncio
async def test_memory_circuit_breaker_record_success():
    """Test MemoryCircuitBreaker.record_success method."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=3,
    )

    # Record success
    await breaker.record_success("test_tool")

    # Should still be able to execute
    can_exec = await breaker.can_execute("test_tool")
    assert can_exec is True


@pytest.mark.asyncio
async def test_memory_circuit_breaker_record_failure():
    """Test MemoryCircuitBreaker.record_failure method."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=3,
    )

    # Record failures
    await breaker.record_failure("test_tool")
    await breaker.record_failure("test_tool")
    await breaker.record_failure("test_tool")

    # Circuit should be open now
    can_exec = await breaker.can_execute("test_tool")
    assert can_exec is False


@pytest.mark.asyncio
async def test_memory_circuit_breaker_get_config():
    """Test MemoryCircuitBreaker._get_config method with tool-specific config."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=5,
        tool_configs={"special_tool": {"failure_threshold": 2}},
    )

    # Test with special tool (should use custom config with threshold=2)
    await breaker.record_failure("special_tool")
    await breaker.record_failure("special_tool")

    # Special tool should be open (threshold=2)
    can_exec_special = await breaker.can_execute("special_tool")
    assert can_exec_special is False

    # Normal tool should still work (threshold=5)
    await breaker.record_failure("normal_tool")
    await breaker.record_failure("normal_tool")
    can_exec_normal = await breaker.can_execute("normal_tool")
    assert can_exec_normal is True


@pytest.mark.asyncio
async def test_memory_circuit_breaker_get_state():
    """Test MemoryCircuitBreaker._get_state creates new state on first access."""
    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=3,
    )

    # Access two different tools
    await breaker.can_execute("tool1")
    await breaker.can_execute("tool2")

    # Both should have separate states
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool1")
    await breaker.record_failure("tool1")

    # tool1 should be open, tool2 should be closed
    assert await breaker.can_execute("tool1") is False
    assert await breaker.can_execute("tool2") is True


# --------------------------------------------------------------------------- #
# Tests - ImportError branches (Redis not available)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_circuit_breaker_redis_import_error(monkeypatch):
    """Test create_circuit_breaker raises ImportError when Redis not available."""
    from chuk_tool_processor.execution.wrappers import factory

    # Mock _check_redis_available to return False
    monkeypatch.setattr(factory, "_check_redis_available", lambda: False)

    with pytest.raises(ImportError) as exc_info:
        await create_circuit_breaker(
            backend=WrapperBackend.REDIS,
            failure_threshold=5,
        )

    assert "Redis package not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_rate_limiter_redis_import_error(monkeypatch):
    """Test create_rate_limiter raises ImportError when Redis not available."""
    from chuk_tool_processor.execution.wrappers import factory

    # Mock _check_redis_available to return False
    monkeypatch.setattr(factory, "_check_redis_available", lambda: False)

    with pytest.raises(ImportError) as exc_info:
        await create_rate_limiter(
            backend=WrapperBackend.REDIS,
            global_limit=100,
        )

    assert "Redis package not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_production_executor_redis_cb_import_error(monkeypatch):
    """Test create_production_executor raises ImportError when Redis CB not available."""
    from chuk_tool_processor.execution.wrappers import factory

    # Mock _check_redis_available to return False
    monkeypatch.setattr(factory, "_check_redis_available", lambda: False)

    strategy = DummyStrategy()

    with pytest.raises(ImportError) as exc_info:
        await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.REDIS,
            rate_limiter_backend=WrapperBackend.MEMORY,
        )

    assert "Redis package not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_production_executor_redis_rl_import_error(monkeypatch):
    """Test create_production_executor raises ImportError when Redis RL not available."""
    from chuk_tool_processor.execution.wrappers import factory

    # Mock _check_redis_available to return False
    monkeypatch.setattr(factory, "_check_redis_available", lambda: False)

    strategy = DummyStrategy()

    with pytest.raises(ImportError) as exc_info:
        await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.MEMORY,
            rate_limiter_backend=WrapperBackend.REDIS,
        )

    assert "Redis package not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_check_redis_not_available(monkeypatch):
    """Test _check_redis_available when redis is not installed.

    Note: This test is tricky because redis IS installed in the test environment.
    We test the ImportError branches indirectly through the other tests
    (test_create_circuit_breaker_redis_import_error, etc.) by mocking
    _check_redis_available to return False.
    """
    # The ImportError branches are tested in:
    # - test_create_circuit_breaker_redis_import_error
    # - test_create_rate_limiter_redis_import_error
    # - test_create_production_executor_redis_cb_import_error
    # - test_create_production_executor_redis_rl_import_error
    pass


# --------------------------------------------------------------------------- #
# Tests - Protocol interface compliance
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_memory_circuit_breaker_implements_protocol():
    """Test that MemoryCircuitBreaker implements CircuitBreakerInterface."""
    from chuk_tool_processor.execution.wrappers.factory import CircuitBreakerInterface

    breaker = await create_circuit_breaker(
        backend=WrapperBackend.MEMORY,
        failure_threshold=3,
    )

    # Check it implements the protocol
    assert isinstance(breaker, CircuitBreakerInterface)


@pytest.mark.asyncio
async def test_memory_rate_limiter_implements_protocol():
    """Test that RateLimiter implements RateLimiterInterface."""
    from chuk_tool_processor.execution.wrappers.factory import RateLimiterInterface

    limiter = await create_rate_limiter(
        backend=WrapperBackend.MEMORY,
        global_limit=100,
    )

    # Check it implements the protocol
    assert isinstance(limiter, RateLimiterInterface)
