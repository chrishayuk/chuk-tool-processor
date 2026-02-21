# tests/test_config_coverage.py
"""Coverage tests for chuk_tool_processor.config module.

Targets the uncovered helper functions, all from_env() class methods,
ProcessorConfig properties/methods, and the memory-backend create_executor path.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuk_tool_processor.config import (
    BackendType,
    CacheConfig,
    CircuitBreakerConfig,
    ProcessorConfig,
    RateLimitConfig,
    RegistryConfig,
    ResilienceBackend,
    RetryConfig,
    _get_bool,
    _get_float,
    _get_int,
    create_executor,
)


# ------------------------------------------------------------------ #
# _get_bool
# ------------------------------------------------------------------ #
class TestGetBool:
    """Tests for _get_bool helper."""

    def test_true_values(self):
        for val in ("true", "1", "yes", "on", "TRUE", "Yes", "ON"):
            with patch.dict(os.environ, {"TEST_KEY": val}):
                assert _get_bool("TEST_KEY") is True

    def test_false_values(self):
        for val in ("false", "0", "no", "off", "FALSE", "No", "OFF"):
            with patch.dict(os.environ, {"TEST_KEY": val}):
                assert _get_bool("TEST_KEY") is False

    def test_unrecognised_returns_default_false(self):
        with patch.dict(os.environ, {"TEST_KEY": "maybe"}):
            assert _get_bool("TEST_KEY") is False

    def test_unrecognised_returns_default_true(self):
        with patch.dict(os.environ, {"TEST_KEY": "maybe"}):
            assert _get_bool("TEST_KEY", default=True) is True

    def test_missing_key_returns_default(self):
        env = os.environ.copy()
        env.pop("TEST_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            assert _get_bool("TEST_KEY") is False
            assert _get_bool("TEST_KEY", default=True) is True

    def test_empty_string_returns_default(self):
        with patch.dict(os.environ, {"TEST_KEY": ""}):
            assert _get_bool("TEST_KEY", default=True) is True


# ------------------------------------------------------------------ #
# _get_int
# ------------------------------------------------------------------ #
class TestGetInt:
    """Tests for _get_int helper."""

    def test_valid_int(self):
        with patch.dict(os.environ, {"TEST_KEY": "42"}):
            assert _get_int("TEST_KEY") == 42

    def test_missing_key_returns_default(self):
        env = os.environ.copy()
        env.pop("TEST_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            assert _get_int("TEST_KEY") is None
            assert _get_int("TEST_KEY", default=7) == 7

    def test_invalid_value_returns_default(self):
        with patch.dict(os.environ, {"TEST_KEY": "not_a_number"}):
            assert _get_int("TEST_KEY") is None
            assert _get_int("TEST_KEY", default=99) == 99


# ------------------------------------------------------------------ #
# _get_float
# ------------------------------------------------------------------ #
class TestGetFloat:
    """Tests for _get_float helper."""

    def test_valid_float(self):
        with patch.dict(os.environ, {"TEST_KEY": "3.14"}):
            assert _get_float("TEST_KEY") == pytest.approx(3.14)

    def test_valid_integer_string(self):
        with patch.dict(os.environ, {"TEST_KEY": "10"}):
            assert _get_float("TEST_KEY") == pytest.approx(10.0)

    def test_missing_key_returns_default(self):
        env = os.environ.copy()
        env.pop("TEST_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            assert _get_float("TEST_KEY") is None
            assert _get_float("TEST_KEY", default=1.5) == pytest.approx(1.5)

    def test_invalid_value_returns_default(self):
        with patch.dict(os.environ, {"TEST_KEY": "abc"}):
            assert _get_float("TEST_KEY") is None
            assert _get_float("TEST_KEY", default=2.5) == pytest.approx(2.5)


# ------------------------------------------------------------------ #
# CircuitBreakerConfig.from_env
# ------------------------------------------------------------------ #
class TestCircuitBreakerConfigFromEnv:
    """Tests for CircuitBreakerConfig.from_env()."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = CircuitBreakerConfig.from_env()
            assert cfg.enabled is False
            assert cfg.failure_threshold == 5
            assert cfg.success_threshold == 2
            assert cfg.reset_timeout == pytest.approx(60.0)
            assert cfg.failure_window == pytest.approx(60.0)
            assert cfg.half_open_max_calls == 1

    def test_custom_values(self):
        env = {
            "CHUK_CIRCUIT_BREAKER_ENABLED": "true",
            "CHUK_CIRCUIT_BREAKER_FAILURE_THRESHOLD": "10",
            "CHUK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD": "3",
            "CHUK_CIRCUIT_BREAKER_RESET_TIMEOUT": "120.5",
            "CHUK_CIRCUIT_BREAKER_FAILURE_WINDOW": "90.0",
            "CHUK_CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS": "2",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CircuitBreakerConfig.from_env()
            assert cfg.enabled is True
            assert cfg.failure_threshold == 10
            assert cfg.success_threshold == 3
            assert cfg.reset_timeout == pytest.approx(120.5)
            assert cfg.failure_window == pytest.approx(90.0)
            assert cfg.half_open_max_calls == 2


# ------------------------------------------------------------------ #
# RateLimitConfig.from_env
# ------------------------------------------------------------------ #
class TestRateLimitConfigFromEnv:
    """Tests for RateLimitConfig.from_env()."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = RateLimitConfig.from_env()
            assert cfg.enabled is False
            assert cfg.global_limit is None
            assert cfg.global_period == pytest.approx(60.0)
            assert cfg.tool_limits == {}

    def test_with_global_limit(self):
        env = {
            "CHUK_RATE_LIMIT_ENABLED": "true",
            "CHUK_RATE_LIMIT_GLOBAL": "100",
            "CHUK_RATE_LIMIT_PERIOD": "30.0",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RateLimitConfig.from_env()
            assert cfg.enabled is True
            assert cfg.global_limit == 100
            assert cfg.global_period == pytest.approx(30.0)

    def test_tool_limits_parsing(self):
        env = {
            "CHUK_RATE_LIMIT_TOOLS": "search:10:60,weather:5:30",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RateLimitConfig.from_env()
            assert "search" in cfg.tool_limits
            assert cfg.tool_limits["search"] == (10, 60.0)
            assert "weather" in cfg.tool_limits
            assert cfg.tool_limits["weather"] == (5, 30.0)

    def test_tool_limits_malformed_entry_skipped(self):
        """Entries with wrong part count or non-numeric values are skipped."""
        env = {
            "CHUK_RATE_LIMIT_TOOLS": "good:10:60,bad_only_two:10,bad_value:abc:60",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RateLimitConfig.from_env()
            assert "good" in cfg.tool_limits
            assert "bad_only_two" not in cfg.tool_limits
            assert "bad_value" not in cfg.tool_limits

    def test_tool_limits_empty_string(self):
        env = {"CHUK_RATE_LIMIT_TOOLS": ""}
        with patch.dict(os.environ, env, clear=True):
            cfg = RateLimitConfig.from_env()
            assert cfg.tool_limits == {}


# ------------------------------------------------------------------ #
# CacheConfig.from_env
# ------------------------------------------------------------------ #
class TestCacheConfigFromEnv:
    """Tests for CacheConfig.from_env()."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = CacheConfig.from_env()
            assert cfg.enabled is True  # default is True
            assert cfg.ttl == 300

    def test_custom_values(self):
        env = {
            "CHUK_CACHE_ENABLED": "false",
            "CHUK_CACHE_TTL": "600",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CacheConfig.from_env()
            assert cfg.enabled is False
            assert cfg.ttl == 600


# ------------------------------------------------------------------ #
# RetryConfig.from_env
# ------------------------------------------------------------------ #
class TestRetryConfigFromEnv:
    """Tests for RetryConfig.from_env()."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = RetryConfig.from_env()
            assert cfg.enabled is True
            assert cfg.max_retries == 3
            assert cfg.base_delay == pytest.approx(1.0)
            assert cfg.max_delay == pytest.approx(60.0)
            assert cfg.exponential_base == pytest.approx(2.0)

    def test_custom_values(self):
        env = {
            "CHUK_RETRY_ENABLED": "false",
            "CHUK_RETRY_MAX": "5",
            "CHUK_RETRY_BASE_DELAY": "0.5",
            "CHUK_RETRY_MAX_DELAY": "120.0",
            "CHUK_RETRY_EXPONENTIAL_BASE": "3.0",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RetryConfig.from_env()
            assert cfg.enabled is False
            assert cfg.max_retries == 5
            assert cfg.base_delay == pytest.approx(0.5)
            assert cfg.max_delay == pytest.approx(120.0)
            assert cfg.exponential_base == pytest.approx(3.0)


# ------------------------------------------------------------------ #
# RegistryConfig.from_env
# ------------------------------------------------------------------ #
class TestRegistryConfigFromEnv:
    """Tests for RegistryConfig.from_env()."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = RegistryConfig.from_env()
            assert cfg.backend == BackendType.MEMORY
            assert cfg.redis_url == "redis://localhost:6379/0"
            assert cfg.key_prefix == "chuk"
            assert cfg.local_cache_ttl == pytest.approx(60.0)

    def test_redis_backend(self):
        env = {
            "CHUK_REGISTRY_BACKEND": "redis",
            "CHUK_REDIS_URL": "redis://myhost:6380/1",
            "CHUK_REDIS_KEY_PREFIX": "myapp",
            "CHUK_REGISTRY_LOCAL_CACHE_TTL": "30.0",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RegistryConfig.from_env()
            assert cfg.backend == BackendType.REDIS
            assert cfg.redis_url == "redis://myhost:6380/1"
            assert cfg.key_prefix == "myapp"
            assert cfg.local_cache_ttl == pytest.approx(30.0)

    def test_invalid_backend_falls_back_to_memory(self):
        env = {"CHUK_REGISTRY_BACKEND": "invalid_backend"}
        with patch.dict(os.environ, env, clear=True):
            cfg = RegistryConfig.from_env()
            assert cfg.backend == BackendType.MEMORY


# ------------------------------------------------------------------ #
# ProcessorConfig
# ------------------------------------------------------------------ #
class TestProcessorConfig:
    """Tests for ProcessorConfig."""

    def test_backend_property(self):
        """backend is an alias for resilience_backend."""
        cfg = ProcessorConfig(resilience_backend=BackendType.REDIS)
        assert cfg.backend == BackendType.REDIS

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = ProcessorConfig.from_env()
            assert cfg.resilience_backend == BackendType.MEMORY
            assert cfg.redis_url == "redis://localhost:6379/0"
            assert cfg.redis_key_prefix == "chuk"
            assert cfg.default_timeout == pytest.approx(10.0)
            assert cfg.max_concurrency is None

    def test_from_env_custom(self):
        env = {
            "CHUK_RESILIENCE_BACKEND": "redis",
            "CHUK_REDIS_URL": "redis://custom:6379/2",
            "CHUK_REDIS_KEY_PREFIX": "custom_prefix",
            "CHUK_DEFAULT_TIMEOUT": "30.0",
            "CHUK_MAX_CONCURRENCY": "4",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = ProcessorConfig.from_env()
            assert cfg.resilience_backend == BackendType.REDIS
            assert cfg.redis_url == "redis://custom:6379/2"
            assert cfg.redis_key_prefix == "custom_prefix"
            assert cfg.default_timeout == pytest.approx(30.0)
            assert cfg.max_concurrency == 4

    def test_from_env_invalid_resilience_backend(self):
        env = {"CHUK_RESILIENCE_BACKEND": "not_valid"}
        with patch.dict(os.environ, env, clear=True):
            cfg = ProcessorConfig.from_env()
            assert cfg.resilience_backend == BackendType.MEMORY

    def test_to_processor_kwargs(self):
        cfg = ProcessorConfig(
            default_timeout=15.0,
            max_concurrency=8,
            cache=CacheConfig(enabled=True, ttl=120),
            rate_limit=RateLimitConfig(
                enabled=True,
                global_limit=50,
                tool_limits={"search": (10, 60.0)},
            ),
            retry=RetryConfig(enabled=True, max_retries=5),
            circuit_breaker=CircuitBreakerConfig(
                enabled=True,
                failure_threshold=10,
                reset_timeout=30.0,
            ),
        )
        kwargs = cfg.to_processor_kwargs()
        assert kwargs["default_timeout"] == 15.0
        assert kwargs["max_concurrency"] == 8
        assert kwargs["enable_caching"] is True
        assert kwargs["cache_ttl"] == 120
        assert kwargs["enable_rate_limiting"] is True
        assert kwargs["global_rate_limit"] == 50
        assert kwargs["tool_rate_limits"] == {"search": (10, 60.0)}
        assert kwargs["enable_retries"] is True
        assert kwargs["max_retries"] == 5
        assert kwargs["enable_circuit_breaker"] is True
        assert kwargs["circuit_breaker_threshold"] == 10
        assert kwargs["circuit_breaker_timeout"] == 30.0

    def test_to_processor_kwargs_empty_tool_limits_is_none(self):
        cfg = ProcessorConfig(
            rate_limit=RateLimitConfig(enabled=False, tool_limits={}),
        )
        kwargs = cfg.to_processor_kwargs()
        assert kwargs["tool_rate_limits"] is None

    def test_uses_redis_with_redis_backend(self):
        cfg = ProcessorConfig(resilience_backend=BackendType.REDIS)
        assert cfg.uses_redis() is True

    def test_uses_redis_with_memory_backend(self):
        cfg = ProcessorConfig(resilience_backend=BackendType.MEMORY)
        assert cfg.uses_redis() is False

    def test_uses_redis_auto_with_redis_available(self):
        cfg = ProcessorConfig(resilience_backend=BackendType.AUTO)
        with patch.dict("sys.modules", {"redis": MagicMock()}):
            assert cfg.uses_redis() is True

    def test_uses_redis_auto_without_redis(self):
        cfg = ProcessorConfig(resilience_backend=BackendType.AUTO)
        import sys

        # Remove redis from modules if present and make import fail
        saved = sys.modules.pop("redis", None)
        try:
            with patch("builtins.__import__", side_effect=_import_side_effect_no_redis):
                assert cfg.uses_redis() is False
        finally:
            if saved is not None:
                sys.modules["redis"] = saved

    def test_registry_uses_redis_true(self):
        cfg = ProcessorConfig(
            registry=RegistryConfig(backend=BackendType.REDIS),
        )
        assert cfg.registry_uses_redis() is True

    def test_registry_uses_redis_false(self):
        cfg = ProcessorConfig(
            registry=RegistryConfig(backend=BackendType.MEMORY),
        )
        assert cfg.registry_uses_redis() is False


def _import_side_effect_no_redis(name, *args, **kwargs):
    """Side effect for __import__ that blocks 'redis' but allows everything else."""
    if name == "redis":
        raise ImportError("No module named 'redis'")
    return (
        __builtins__.__import__(name, *args, **kwargs)
        if hasattr(__builtins__, "__import__")
        else __import__(name, *args, **kwargs)
    )


# ------------------------------------------------------------------ #
# ResilienceBackend alias
# ------------------------------------------------------------------ #
class TestResilienceBackendAlias:
    """Backwards compatibility alias."""

    def test_alias_is_backend_type(self):
        assert ResilienceBackend is BackendType
        assert ResilienceBackend.MEMORY == BackendType.MEMORY


# ------------------------------------------------------------------ #
# create_executor (memory backend path)
# ------------------------------------------------------------------ #
class TestCreateExecutorMemory:
    """Tests for create_executor with memory backend."""

    @pytest.mark.asyncio
    async def test_no_wrappers_when_nothing_enabled(self):
        """With nothing enabled, strategy is returned unwrapped."""
        strategy = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.MEMORY,
            circuit_breaker=CircuitBreakerConfig(enabled=False),
            rate_limit=RateLimitConfig(enabled=False),
        )
        result = await create_executor(strategy, cfg)
        assert result is strategy

    @pytest.mark.asyncio
    async def test_circuit_breaker_wrapper(self):
        """Circuit breaker wraps the strategy."""
        strategy = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.MEMORY,
            circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=7),
            rate_limit=RateLimitConfig(enabled=False),
        )
        result = await create_executor(strategy, cfg)
        from chuk_tool_processor.execution.wrappers.circuit_breaker import (
            CircuitBreakerExecutor,
        )

        assert isinstance(result, CircuitBreakerExecutor)

    @pytest.mark.asyncio
    async def test_rate_limit_wrapper(self):
        """Rate limiter wraps the strategy."""
        strategy = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.MEMORY,
            circuit_breaker=CircuitBreakerConfig(enabled=False),
            rate_limit=RateLimitConfig(enabled=True, global_limit=100),
        )
        result = await create_executor(strategy, cfg)
        from chuk_tool_processor.execution.wrappers.rate_limiting import (
            RateLimitedToolExecutor,
        )

        assert isinstance(result, RateLimitedToolExecutor)

    @pytest.mark.asyncio
    async def test_both_wrappers(self):
        """Both circuit breaker and rate limiter wrap the strategy."""
        strategy = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.MEMORY,
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            rate_limit=RateLimitConfig(enabled=True, global_limit=50),
        )
        result = await create_executor(strategy, cfg)
        from chuk_tool_processor.execution.wrappers.rate_limiting import (
            RateLimitedToolExecutor,
        )

        # Outermost wrapper should be rate limiter (applied last)
        assert isinstance(result, RateLimitedToolExecutor)

    @pytest.mark.asyncio
    async def test_config_none_loads_from_env(self):
        """When config is None, from_env() is used."""
        strategy = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            result = await create_executor(strategy, None)
            # Default env: nothing enabled, so strategy returned as-is
            assert result is strategy


# ------------------------------------------------------------------ #
# create_registry
# ------------------------------------------------------------------ #
class TestCreateRegistry:
    """Tests for ProcessorConfig.create_registry()."""

    @pytest.mark.asyncio
    async def test_memory_registry(self):
        """Memory backend calls get_registry('memory')."""
        cfg = ProcessorConfig(
            registry=RegistryConfig(backend=BackendType.MEMORY),
        )
        mock_registry = MagicMock()
        with patch(
            "chuk_tool_processor.registry.providers.get_registry",
            new_callable=lambda: AsyncMock(return_value=mock_registry),
        ) as mock_get:
            result = await cfg.create_registry()
            mock_get.assert_awaited_once_with("memory")
            assert result is mock_registry

    @pytest.mark.asyncio
    async def test_redis_registry(self):
        """Redis backend calls get_registry with redis params."""
        cfg = ProcessorConfig(
            registry=RegistryConfig(
                backend=BackendType.REDIS,
                redis_url="redis://myhost:6379/1",
                key_prefix="test",
                local_cache_ttl=30.0,
            ),
        )
        mock_registry = MagicMock()
        with patch(
            "chuk_tool_processor.registry.providers.get_registry",
            new_callable=lambda: AsyncMock(return_value=mock_registry),
        ) as mock_get:
            result = await cfg.create_registry()
            mock_get.assert_awaited_once_with(
                "redis",
                redis_url="redis://myhost:6379/1",
                key_prefix="test",
                local_cache_ttl=30.0,
            )
            assert result is mock_registry


# ------------------------------------------------------------------ #
# create_processor
# ------------------------------------------------------------------ #
class TestCreateProcessor:
    """Tests for ProcessorConfig.create_processor()."""

    @pytest.mark.asyncio
    async def test_memory_processor(self):
        """Memory backend creates processor with to_processor_kwargs."""
        cfg = ProcessorConfig(
            resilience_backend=BackendType.MEMORY,
            circuit_breaker=CircuitBreakerConfig(enabled=False),
            rate_limit=RateLimitConfig(enabled=False),
        )
        mock_registry = MagicMock()
        mock_processor = MagicMock()

        with (
            patch(
                "chuk_tool_processor.config.ProcessorConfig.create_registry",
                new=AsyncMock(return_value=mock_registry),
            ),
            patch(
                "chuk_tool_processor.core.processor.ToolProcessor",
                return_value=mock_processor,
            ) as MockTP,
        ):
            result = await cfg.create_processor()
            assert result is mock_processor
            MockTP.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_processor_with_resilience(self):
        """Redis backend with resilience features wraps executor."""
        cfg = ProcessorConfig(
            resilience_backend=BackendType.REDIS,
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            rate_limit=RateLimitConfig(enabled=True, global_limit=50),
        )
        mock_registry = MagicMock()
        mock_executor = MagicMock()
        mock_processor = MagicMock()

        with (
            patch(
                "chuk_tool_processor.config.ProcessorConfig.create_registry",
                new=AsyncMock(return_value=mock_registry),
            ),
            patch(
                "chuk_tool_processor.config.create_executor",
                new=AsyncMock(return_value=mock_executor),
            ),
            patch(
                "chuk_tool_processor.core.processor.ToolProcessor",
                return_value=mock_processor,
            ) as MockTP,
        ):
            result = await cfg.create_processor()
            assert result is mock_processor
            call_kwargs = MockTP.call_args[1]
            assert call_kwargs["enable_rate_limiting"] is False
            assert call_kwargs["enable_circuit_breaker"] is False


# ------------------------------------------------------------------ #
# create_executor (Redis backend path)
# ------------------------------------------------------------------ #
class TestCreateExecutorRedis:
    """Tests for create_executor with Redis backend."""

    @pytest.mark.asyncio
    async def test_redis_executor_with_both_enabled(self):
        """Redis backend with both CB and RL calls create_production_executor."""
        strategy = MagicMock()
        mock_executor = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.REDIS,
            redis_url="redis://test:6379/0",
            circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=3),
            rate_limit=RateLimitConfig(enabled=True, global_limit=100),
        )

        with patch(
            "chuk_tool_processor.execution.wrappers.factory.create_production_executor",
            new_callable=lambda: AsyncMock(return_value=mock_executor),
        ) as mock_create:
            result = await create_executor(strategy, cfg)
            assert result is mock_executor
            mock_create.assert_awaited_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["redis_url"] == "redis://test:6379/0"
            assert call_kwargs["enable_circuit_breaker"] is True
            assert call_kwargs["enable_rate_limiter"] is True
            assert call_kwargs["circuit_breaker_settings"] is not None
            assert call_kwargs["rate_limiter_settings"] is not None

    @pytest.mark.asyncio
    async def test_redis_executor_cb_only(self):
        """Redis backend with only circuit breaker."""
        strategy = MagicMock()
        mock_executor = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.REDIS,
            circuit_breaker=CircuitBreakerConfig(enabled=True),
            rate_limit=RateLimitConfig(enabled=False),
        )

        with patch(
            "chuk_tool_processor.execution.wrappers.factory.create_production_executor",
            new_callable=lambda: AsyncMock(return_value=mock_executor),
        ) as mock_create:
            result = await create_executor(strategy, cfg)
            assert result is mock_executor
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["enable_circuit_breaker"] is True
            assert call_kwargs["enable_rate_limiter"] is False
            assert call_kwargs["circuit_breaker_settings"] is not None
            assert call_kwargs["rate_limiter_settings"] is None

    @pytest.mark.asyncio
    async def test_redis_executor_rl_only(self):
        """Redis backend with only rate limiter."""
        strategy = MagicMock()
        mock_executor = MagicMock()
        cfg = ProcessorConfig(
            resilience_backend=BackendType.REDIS,
            circuit_breaker=CircuitBreakerConfig(enabled=False),
            rate_limit=RateLimitConfig(enabled=True, global_limit=10),
        )

        with patch(
            "chuk_tool_processor.execution.wrappers.factory.create_production_executor",
            new_callable=lambda: AsyncMock(return_value=mock_executor),
        ) as mock_create:
            result = await create_executor(strategy, cfg)
            assert result is mock_executor
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["enable_circuit_breaker"] is False
            assert call_kwargs["enable_rate_limiter"] is True
            assert call_kwargs["circuit_breaker_settings"] is None
            assert call_kwargs["rate_limiter_settings"] is not None
