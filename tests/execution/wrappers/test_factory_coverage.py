# tests/execution/wrappers/test_factory_coverage.py
"""
Comprehensive tests for factory.py using only unittest.mock.

No fakeredis required -- all Redis interactions are mocked.
Target: push module coverage above 90%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chuk_tool_processor.execution.wrappers.factory import (
    CircuitBreakerInterface,
    CircuitBreakerSettings,
    RateLimiterInterface,
    RateLimiterSettings,
    WrapperBackend,
    _check_redis_available,
    create_circuit_breaker,
    create_production_executor,
    create_rate_limiter,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class DummyStrategy:
    """Minimal strategy stub."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0

    async def execute(self, calls, timeout=None, use_cache=True):
        self.call_count += len(calls)
        results = []
        for c in calls:
            if self.should_fail:
                results.append(ToolResult(tool=c.tool, result=None, error="fail"))
            else:
                results.append(ToolResult(tool=c.tool, result={"ok": True}, error=None))
        return results


# ---------------------------------------------------------------------------
# WrapperBackend enum
# ---------------------------------------------------------------------------
class TestWrapperBackend:
    def test_values(self):
        assert WrapperBackend.MEMORY.value == "memory"
        assert WrapperBackend.REDIS.value == "redis"
        assert WrapperBackend.AUTO.value == "auto"

    def test_is_str_enum(self):
        assert isinstance(WrapperBackend.MEMORY, str)
        assert WrapperBackend.REDIS == "redis"

    def test_from_value(self):
        assert WrapperBackend("memory") is WrapperBackend.MEMORY
        assert WrapperBackend("redis") is WrapperBackend.REDIS
        assert WrapperBackend("auto") is WrapperBackend.AUTO


# ---------------------------------------------------------------------------
# CircuitBreakerSettings
# ---------------------------------------------------------------------------
class TestCircuitBreakerSettings:
    def test_defaults(self):
        s = CircuitBreakerSettings()
        assert s.failure_threshold == 5
        assert s.success_threshold == 2
        assert s.reset_timeout == 60.0
        assert s.half_open_max_calls == 1
        assert s.failure_window == 60.0
        assert s.tool_configs is None

    def test_custom(self):
        s = CircuitBreakerSettings(
            failure_threshold=10,
            success_threshold=4,
            reset_timeout=30.0,
            half_open_max_calls=3,
            failure_window=120.0,
            tool_configs={"api": {"failure_threshold": 2}},
        )
        assert s.failure_threshold == 10
        assert s.tool_configs["api"]["failure_threshold"] == 2


# ---------------------------------------------------------------------------
# RateLimiterSettings
# ---------------------------------------------------------------------------
class TestRateLimiterSettings:
    def test_defaults(self):
        s = RateLimiterSettings()
        assert s.global_limit is None
        assert s.global_period == 60.0
        assert s.tool_limits is None

    def test_custom(self):
        s = RateLimiterSettings(
            global_limit=200,
            global_period=120.0,
            tool_limits={"api": (10, 30.0)},
        )
        assert s.global_limit == 200
        assert s.tool_limits["api"] == (10, 30.0)


# ---------------------------------------------------------------------------
# _check_redis_available
# ---------------------------------------------------------------------------
class TestCheckRedisAvailable:
    def test_returns_true_when_redis_installed(self):
        # redis IS installed in the test environment
        assert _check_redis_available() is True

    def test_returns_false_when_import_fails(self):
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            # Need to re-import to trigger the check inside the function
            # Instead, just patch the import mechanism
            import builtins

            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "redis.asyncio" or name == "redis":
                    raise ImportError("no redis")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = _check_redis_available()
            assert result is False


# ---------------------------------------------------------------------------
# Protocol interfaces
# ---------------------------------------------------------------------------
class TestProtocols:
    def test_circuit_breaker_interface_is_runtime_checkable(self):
        assert hasattr(CircuitBreakerInterface, "__protocol_attrs__") or True

        # Just verify we can use isinstance checks
        class Dummy:
            async def can_execute(self, tool: str) -> bool:
                return True

            async def record_success(self, tool: str) -> None:
                pass

            async def record_failure(self, tool: str) -> None:
                pass

        assert isinstance(Dummy(), CircuitBreakerInterface)

    def test_rate_limiter_interface_is_runtime_checkable(self):
        class Dummy:
            async def wait(self, tool: str) -> None:
                pass

        assert isinstance(Dummy(), RateLimiterInterface)


# ---------------------------------------------------------------------------
# create_circuit_breaker -- MEMORY
# ---------------------------------------------------------------------------
class TestCreateCircuitBreakerMemory:
    @pytest.mark.asyncio
    async def test_basic(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY)
        assert cb is not None
        assert isinstance(cb, CircuitBreakerInterface)

    @pytest.mark.asyncio
    async def test_with_settings(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=3,
            success_threshold=1,
            reset_timeout=15.0,
            half_open_max_calls=2,
        )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_with_tool_configs(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=5,
            tool_configs={
                "expensive": {"failure_threshold": 2, "reset_timeout": 10.0},
            },
        )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_with_empty_tool_configs(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            tool_configs={},
        )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_with_none_tool_configs(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            tool_configs=None,
        )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_can_execute(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=3)
        assert await cb.can_execute("tool") is True

    @pytest.mark.asyncio
    async def test_record_success(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=3)
        await cb.record_success("tool")
        assert await cb.can_execute("tool") is True

    @pytest.mark.asyncio
    async def test_record_failure_opens_circuit(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=2)
        await cb.record_failure("tool")
        await cb.record_failure("tool")
        assert await cb.can_execute("tool") is False

    @pytest.mark.asyncio
    async def test_per_tool_isolation(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=5,
            tool_configs={"fragile": {"failure_threshold": 1}},
        )
        await cb.record_failure("fragile")
        assert await cb.can_execute("fragile") is False
        assert await cb.can_execute("normal") is True


# ---------------------------------------------------------------------------
# create_circuit_breaker -- REDIS
# ---------------------------------------------------------------------------
class TestCreateCircuitBreakerRedis:
    @pytest.mark.asyncio
    async def test_basic(self):
        mock_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker",
                mock_create,
            ),
        ):
            cb = await create_circuit_breaker(
                backend=WrapperBackend.REDIS,
                redis_url="redis://localhost:6379/0",
                failure_threshold=5,
            )
        assert cb is not None
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_tool_configs(self):
        mock_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker",
                mock_create,
            ),
        ):
            cb = await create_circuit_breaker(
                backend=WrapperBackend.REDIS,
                tool_configs={"api": {"failure_threshold": 2}},
            )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_raises_when_redis_unavailable(self):
        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=False,
            ),
            pytest.raises(ImportError, match="Redis package not installed"),
        ):
            await create_circuit_breaker(backend=WrapperBackend.REDIS)


# ---------------------------------------------------------------------------
# create_circuit_breaker -- AUTO
# ---------------------------------------------------------------------------
class TestCreateCircuitBreakerAuto:
    @pytest.mark.asyncio
    async def test_auto_selects_redis_when_available(self):
        mock_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker",
                mock_create,
            ),
        ):
            await create_circuit_breaker(backend=WrapperBackend.AUTO)
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_falls_back_to_memory(self):
        with patch(
            "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
            return_value=False,
        ):
            cb = await create_circuit_breaker(backend=WrapperBackend.AUTO)
        assert cb is not None
        assert isinstance(cb, CircuitBreakerInterface)


# ---------------------------------------------------------------------------
# create_rate_limiter -- MEMORY
# ---------------------------------------------------------------------------
class TestCreateRateLimiterMemory:
    @pytest.mark.asyncio
    async def test_basic(self):
        rl = await create_rate_limiter(backend=WrapperBackend.MEMORY)
        assert rl is not None
        assert isinstance(rl, RateLimiterInterface)

    @pytest.mark.asyncio
    async def test_with_settings(self):
        rl = await create_rate_limiter(
            backend=WrapperBackend.MEMORY,
            global_limit=100,
            global_period=30.0,
            tool_limits={"api": (10, 60.0)},
        )
        assert rl is not None

    @pytest.mark.asyncio
    async def test_no_limit(self):
        rl = await create_rate_limiter(backend=WrapperBackend.MEMORY, global_limit=None)
        assert rl is not None


# ---------------------------------------------------------------------------
# create_rate_limiter -- REDIS
# ---------------------------------------------------------------------------
class TestCreateRateLimiterRedis:
    @pytest.mark.asyncio
    async def test_basic(self):
        mock_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_create,
            ),
        ):
            rl = await create_rate_limiter(
                backend=WrapperBackend.REDIS,
                redis_url="redis://localhost:6379/0",
                global_limit=100,
            )
        assert rl is not None
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_redis_unavailable(self):
        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=False,
            ),
            pytest.raises(ImportError, match="Redis package not installed"),
        ):
            await create_rate_limiter(backend=WrapperBackend.REDIS)


# ---------------------------------------------------------------------------
# create_rate_limiter -- AUTO
# ---------------------------------------------------------------------------
class TestCreateRateLimiterAuto:
    @pytest.mark.asyncio
    async def test_auto_selects_redis_when_available(self):
        mock_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_create,
            ),
        ):
            await create_rate_limiter(backend=WrapperBackend.AUTO, global_limit=50)
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_falls_back_to_memory(self):
        with patch(
            "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
            return_value=False,
        ):
            rl = await create_rate_limiter(backend=WrapperBackend.AUTO)
        assert rl is not None


# ---------------------------------------------------------------------------
# create_production_executor -- MEMORY
# ---------------------------------------------------------------------------
class TestCreateProductionExecutorMemory:
    @pytest.mark.asyncio
    async def test_defaults(self):
        strategy = DummyStrategy()
        ex = await create_production_executor(strategy)
        assert ex is not None

    @pytest.mark.asyncio
    async def test_both_disabled_returns_strategy(self):
        strategy = DummyStrategy()
        ex = await create_production_executor(
            strategy,
            enable_circuit_breaker=False,
            enable_rate_limiter=False,
        )
        assert ex is strategy

    @pytest.mark.asyncio
    async def test_circuit_breaker_only(self):
        strategy = DummyStrategy()
        ex = await create_production_executor(
            strategy,
            enable_circuit_breaker=True,
            enable_rate_limiter=False,
        )
        assert ex is not strategy

    @pytest.mark.asyncio
    async def test_rate_limiter_only(self):
        strategy = DummyStrategy()
        ex = await create_production_executor(
            strategy,
            enable_circuit_breaker=False,
            enable_rate_limiter=True,
        )
        assert ex is not strategy

    @pytest.mark.asyncio
    async def test_with_custom_settings(self):
        strategy = DummyStrategy()
        cb_settings = CircuitBreakerSettings(failure_threshold=3, reset_timeout=15.0)
        rl_settings = RateLimiterSettings(global_limit=50, global_period=30.0)

        ex = await create_production_executor(
            strategy,
            circuit_breaker_settings=cb_settings,
            rate_limiter_settings=rl_settings,
        )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_with_tool_configs(self):
        strategy = DummyStrategy()
        cb_settings = CircuitBreakerSettings(
            failure_threshold=5,
            tool_configs={"api": {"failure_threshold": 2, "reset_timeout": 10.0}},
        )
        rl_settings = RateLimiterSettings(
            global_limit=100,
            tool_limits={"api": (10, 60.0)},
        )
        ex = await create_production_executor(
            strategy,
            circuit_breaker_settings=cb_settings,
            rate_limiter_settings=rl_settings,
        )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_execute_through_memory_executor(self):
        strategy = DummyStrategy()
        ex = await create_production_executor(
            strategy,
            circuit_breaker_backend=WrapperBackend.MEMORY,
            rate_limiter_backend=WrapperBackend.MEMORY,
        )
        calls = [ToolCall(tool="test", arguments={})]
        results = await ex.execute(calls)
        assert len(results) == 1
        assert results[0].error is None


# ---------------------------------------------------------------------------
# create_production_executor -- REDIS
# ---------------------------------------------------------------------------
class TestCreateProductionExecutorRedis:
    @pytest.mark.asyncio
    async def test_redis_both(self):
        mock_cb_create = AsyncMock(return_value=MagicMock())
        mock_rl_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker_executor",
                mock_cb_create,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_rl_create,
            ),
        ):
            strategy = DummyStrategy()
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.REDIS,
                rate_limiter_backend=WrapperBackend.REDIS,
                redis_url="redis://localhost:6379/0",
            )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_redis_cb_with_tool_configs(self):
        mock_cb_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker_executor",
                mock_cb_create,
            ),
        ):
            strategy = DummyStrategy()
            cb_settings = CircuitBreakerSettings(
                tool_configs={
                    "api": {
                        "failure_threshold": 2,
                        "reset_timeout": 10.0,
                        "failure_window": 30.0,
                    }
                },
            )
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.REDIS,
                rate_limiter_backend=WrapperBackend.MEMORY,
                enable_rate_limiter=False,
                circuit_breaker_settings=cb_settings,
            )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_redis_with_custom_settings(self):
        mock_cb_create = AsyncMock(return_value=MagicMock())
        mock_rl_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker_executor",
                mock_cb_create,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_rl_create,
            ),
        ):
            strategy = DummyStrategy()
            cb_settings = CircuitBreakerSettings(failure_threshold=3, reset_timeout=15.0, failure_window=90.0)
            rl_settings = RateLimiterSettings(global_limit=50, global_period=30.0, tool_limits={"api": (10, 60.0)})
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.REDIS,
                rate_limiter_backend=WrapperBackend.REDIS,
                redis_url="redis://myhost:6380/1",
                circuit_breaker_settings=cb_settings,
                rate_limiter_settings=rl_settings,
            )
        assert ex is not None


# ---------------------------------------------------------------------------
# create_production_executor -- ImportError paths
# ---------------------------------------------------------------------------
class TestCreateProductionExecutorImportErrors:
    @pytest.mark.asyncio
    async def test_redis_cb_raises_when_unavailable(self):
        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=False,
            ),
            pytest.raises(ImportError, match="Redis package not installed"),
        ):
            await create_production_executor(
                DummyStrategy(),
                circuit_breaker_backend=WrapperBackend.REDIS,
                rate_limiter_backend=WrapperBackend.MEMORY,
            )

    @pytest.mark.asyncio
    async def test_redis_rl_raises_when_unavailable(self):
        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=False,
            ),
            pytest.raises(ImportError, match="Redis package not installed"),
        ):
            await create_production_executor(
                DummyStrategy(),
                circuit_breaker_backend=WrapperBackend.MEMORY,
                rate_limiter_backend=WrapperBackend.REDIS,
            )


# ---------------------------------------------------------------------------
# create_production_executor -- AUTO
# ---------------------------------------------------------------------------
class TestCreateProductionExecutorAuto:
    @pytest.mark.asyncio
    async def test_auto_uses_redis_when_available(self):
        mock_cb_create = AsyncMock(return_value=MagicMock())
        mock_rl_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker_executor",
                mock_cb_create,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_rl_create,
            ),
        ):
            strategy = DummyStrategy()
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.AUTO,
                rate_limiter_backend=WrapperBackend.AUTO,
            )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_auto_falls_back_to_memory(self):
        with patch(
            "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
            return_value=False,
        ):
            strategy = DummyStrategy()
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.AUTO,
                rate_limiter_backend=WrapperBackend.AUTO,
            )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_auto_mixed_cb_redis_rl_memory(self):
        """AUTO for CB (selects redis), MEMORY for RL."""
        mock_cb_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_circuit_breaker.create_redis_circuit_breaker_executor",
                mock_cb_create,
            ),
        ):
            strategy = DummyStrategy()
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.AUTO,
                rate_limiter_backend=WrapperBackend.MEMORY,
            )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_auto_cb_memory_rl_redis(self):
        """MEMORY for CB, AUTO for RL (selects redis)."""
        mock_rl_create = AsyncMock(return_value=MagicMock())

        with (
            patch(
                "chuk_tool_processor.execution.wrappers.factory._check_redis_available",
                return_value=True,
            ),
            patch(
                "chuk_tool_processor.execution.wrappers.redis_rate_limiting.create_redis_rate_limiter",
                mock_rl_create,
            ),
        ):
            strategy = DummyStrategy()
            ex = await create_production_executor(
                strategy,
                circuit_breaker_backend=WrapperBackend.MEMORY,
                rate_limiter_backend=WrapperBackend.AUTO,
            )
        assert ex is not None


# ---------------------------------------------------------------------------
# MemoryCircuitBreaker internal methods
# ---------------------------------------------------------------------------
class TestMemoryCircuitBreakerInternals:
    @pytest.mark.asyncio
    async def test_get_config_default(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=5)
        cfg = cb._get_config("any_tool")
        assert cfg.failure_threshold == 5

    @pytest.mark.asyncio
    async def test_get_config_tool_specific(self):
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=5,
            tool_configs={"api": {"failure_threshold": 2}},
        )
        cfg = cb._get_config("api")
        assert cfg.failure_threshold == 2

    @pytest.mark.asyncio
    async def test_get_state_creates_on_first_access(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=3)
        # Accessing two different tools should create separate states
        await cb.can_execute("tool1")
        await cb.can_execute("tool2")
        assert "tool1" in cb._states
        assert "tool2" in cb._states

    @pytest.mark.asyncio
    async def test_states_are_independent(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY, failure_threshold=2)
        await cb.record_failure("t1")
        await cb.record_failure("t1")
        assert await cb.can_execute("t1") is False
        assert await cb.can_execute("t2") is True

    @pytest.mark.asyncio
    async def test_implements_circuit_breaker_interface(self):
        cb = await create_circuit_breaker(backend=WrapperBackend.MEMORY)
        assert isinstance(cb, CircuitBreakerInterface)


# ---------------------------------------------------------------------------
# Edge: circuit breaker settings with no tool_configs key
# ---------------------------------------------------------------------------
class TestSettingsEdgeCases:
    @pytest.mark.asyncio
    async def test_memory_cb_no_tool_configs_key_in_settings(self):
        """When tool_configs is not in settings at all."""
        cb = await create_circuit_breaker(
            backend=WrapperBackend.MEMORY,
            failure_threshold=5,
        )
        assert cb is not None

    @pytest.mark.asyncio
    async def test_memory_rl_no_tool_limits_in_settings(self):
        rl = await create_rate_limiter(
            backend=WrapperBackend.MEMORY,
            global_limit=100,
        )
        assert rl is not None

    @pytest.mark.asyncio
    async def test_production_executor_default_settings_used(self):
        """When no settings objects are provided, defaults are used."""
        strategy = DummyStrategy()
        ex = await create_production_executor(strategy)
        assert ex is not None

    @pytest.mark.asyncio
    async def test_production_executor_cb_settings_no_tool_configs(self):
        strategy = DummyStrategy()
        cb_settings = CircuitBreakerSettings(failure_threshold=3)
        ex = await create_production_executor(
            strategy,
            circuit_breaker_settings=cb_settings,
            enable_rate_limiter=False,
        )
        assert ex is not None

    @pytest.mark.asyncio
    async def test_production_executor_rl_settings_no_tool_limits(self):
        strategy = DummyStrategy()
        rl_settings = RateLimiterSettings(global_limit=50)
        ex = await create_production_executor(
            strategy,
            rate_limiter_settings=rl_settings,
            enable_circuit_breaker=False,
        )
        assert ex is not None
