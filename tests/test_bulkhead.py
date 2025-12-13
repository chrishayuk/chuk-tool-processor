# tests/test_bulkhead.py
"""Tests for Bulkhead concurrency isolation."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from chuk_tool_processor.execution.bulkhead import (
    Bulkhead,
    BulkheadConfig,
    BulkheadFullError,
    BulkheadLimitType,
    BulkheadStats,
)


class TestBulkheadConfig:
    """Test BulkheadConfig validation."""

    def test_default_config(self):
        """Test default configuration."""
        config = BulkheadConfig()

        assert config.default_limit == 10
        assert config.tool_limits == {}
        assert config.namespace_limits == {}
        assert config.global_limit is None
        assert config.acquisition_timeout is None
        assert config.enable_metrics is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = BulkheadConfig(
            default_limit=5,
            tool_limits={"slow_tool": 2},
            namespace_limits={"external": 3},
            global_limit=20,
            acquisition_timeout=1.0,
        )

        assert config.default_limit == 5
        assert config.tool_limits == {"slow_tool": 2}
        assert config.namespace_limits == {"external": 3}
        assert config.global_limit == 20
        assert config.acquisition_timeout == 1.0

    def test_validation_default_limit(self):
        """Test default_limit must be >= 1."""
        with pytest.raises(ValueError):
            BulkheadConfig(default_limit=0)

    def test_validation_global_limit(self):
        """Test global_limit must be >= 1 if set."""
        with pytest.raises(ValueError):
            BulkheadConfig(global_limit=0)


class TestBulkheadBasicOperations:
    """Test basic bulkhead operations."""

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """Test basic acquire and release."""
        bulkhead = Bulkhead()

        async with bulkhead.acquire("test_tool"):
            stats = bulkhead.get_stats("test_tool")
            assert stats is not None
            assert stats.current_active == 1

        # After release
        stats = bulkhead.get_stats("test_tool")
        assert stats.current_active == 0
        assert stats.acquired == 1
        assert stats.released == 1

    @pytest.mark.asyncio
    async def test_concurrent_within_limit(self):
        """Test concurrent executions within limit."""
        config = BulkheadConfig(default_limit=3)
        bulkhead = Bulkhead(config)

        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def task():
            nonlocal active, max_active
            async with bulkhead.acquire("test_tool"):
                async with lock:
                    active += 1
                    max_active = max(max_active, active)
                await asyncio.sleep(0.01)
                async with lock:
                    active -= 1

        # Run 3 concurrent tasks (within limit)
        await asyncio.gather(*[task() for _ in range(3)])

        assert max_active == 3
        stats = bulkhead.get_stats("test_tool")
        assert stats.peak_active == 3

    @pytest.mark.asyncio
    async def test_tool_limit_respected(self):
        """Test that tool-specific limits are respected."""
        config = BulkheadConfig(
            default_limit=10,
            tool_limits={"limited_tool": 2},
        )
        bulkhead = Bulkhead(config)

        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def task():
            nonlocal active, max_active
            async with bulkhead.acquire("limited_tool"):
                async with lock:
                    active += 1
                    max_active = max(max_active, active)
                await asyncio.sleep(0.02)
                async with lock:
                    active -= 1

        # Run 5 concurrent tasks but only 2 should be active at once
        await asyncio.gather(*[task() for _ in range(5)])

        assert max_active == 2
        stats = bulkhead.get_stats("limited_tool")
        assert stats.peak_active == 2
        assert stats.acquired == 5


class TestBulkheadNamespaces:
    """Test namespace-level bulkhead limits."""

    @pytest.mark.asyncio
    async def test_namespace_limit(self):
        """Test namespace limits are enforced."""
        config = BulkheadConfig(
            default_limit=10,
            namespace_limits={"limited_ns": 2},
        )
        bulkhead = Bulkhead(config)

        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def task(tool_name: str):
            nonlocal active, max_active
            async with bulkhead.acquire(tool_name, namespace="limited_ns"):
                async with lock:
                    active += 1
                    max_active = max(max_active, active)
                await asyncio.sleep(0.02)
                async with lock:
                    active -= 1

        # Run 5 tasks across different tools in same namespace
        await asyncio.gather(
            task("tool_a"),
            task("tool_b"),
            task("tool_a"),
            task("tool_b"),
            task("tool_a"),
        )

        # Only 2 should be active at once due to namespace limit
        assert max_active == 2

    @pytest.mark.asyncio
    async def test_namespace_and_tool_limits(self):
        """Test both namespace and tool limits are enforced."""
        config = BulkheadConfig(
            default_limit=10,
            tool_limits={"tool_a": 1},
            namespace_limits={"ns": 3},
        )
        bulkhead = Bulkhead(config)

        tool_a_max = 0
        total_max = 0
        lock = asyncio.Lock()
        tool_a_active = 0
        total_active = 0

        async def task(tool_name: str):
            nonlocal tool_a_max, total_max, tool_a_active, total_active
            async with bulkhead.acquire(tool_name, namespace="ns"):
                async with lock:
                    total_active += 1
                    total_max = max(total_max, total_active)
                    if tool_name == "tool_a":
                        tool_a_active += 1
                        tool_a_max = max(tool_a_max, tool_a_active)
                await asyncio.sleep(0.02)
                async with lock:
                    total_active -= 1
                    if tool_name == "tool_a":
                        tool_a_active -= 1

        await asyncio.gather(
            task("tool_a"),
            task("tool_a"),
            task("tool_b"),
            task("tool_b"),
        )

        # tool_a limited to 1, namespace to 3
        assert tool_a_max == 1
        assert total_max <= 3


class TestBulkheadGlobalLimit:
    """Test global bulkhead limits."""

    @pytest.mark.asyncio
    async def test_global_limit(self):
        """Test global limit across all tools."""
        config = BulkheadConfig(
            default_limit=10,
            global_limit=3,
        )
        bulkhead = Bulkhead(config)

        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def task(tool_name: str):
            nonlocal active, max_active
            async with bulkhead.acquire(tool_name):
                async with lock:
                    active += 1
                    max_active = max(max_active, active)
                await asyncio.sleep(0.02)
                async with lock:
                    active -= 1

        # Run tasks for different tools
        await asyncio.gather(
            task("tool_a"),
            task("tool_b"),
            task("tool_c"),
            task("tool_d"),
            task("tool_e"),
        )

        assert max_active == 3


class TestBulkheadTimeout:
    """Test bulkhead timeout behavior."""

    @pytest.mark.asyncio
    async def test_acquisition_timeout(self):
        """Test timeout when acquiring slot."""
        config = BulkheadConfig(
            default_limit=1,
            acquisition_timeout=0.1,
        )
        bulkhead = Bulkhead(config)

        async def long_task():
            async with bulkhead.acquire("test_tool"):
                await asyncio.sleep(1.0)

        async def short_task():
            async with bulkhead.acquire("test_tool"):
                pass

        # Start long task
        long = asyncio.create_task(long_task())
        await asyncio.sleep(0.01)  # Let it acquire

        # Short task should timeout
        with pytest.raises(BulkheadFullError) as exc_info:
            await short_task()

        assert exc_info.value.limit_type == BulkheadLimitType.TOOL
        assert exc_info.value.tool == "test_tool"
        assert exc_info.value.timeout == 0.1

        # Cleanup
        long.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await long

    @pytest.mark.asyncio
    async def test_timeout_override(self):
        """Test timeout can be overridden per-call."""
        config = BulkheadConfig(
            default_limit=1,
            acquisition_timeout=10.0,  # Long default
        )
        bulkhead = Bulkhead(config)

        async def blocker():
            async with bulkhead.acquire("test_tool"):
                await asyncio.sleep(1.0)

        # Start blocker
        task = asyncio.create_task(blocker())
        await asyncio.sleep(0.01)

        # Use short override timeout
        with pytest.raises(BulkheadFullError):
            async with bulkhead.acquire("test_tool", timeout=0.05):
                pass

        # Cleanup
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestBulkheadStats:
    """Test bulkhead statistics."""

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Test statistics are tracked correctly."""
        bulkhead = Bulkhead()

        # Initial state
        assert bulkhead.get_stats("test_tool") is None

        # After acquisition
        async with bulkhead.acquire("test_tool", namespace="ns"):
            stats = bulkhead.get_stats("test_tool", "ns")
            assert stats is not None
            assert stats.tool == "test_tool"
            assert stats.namespace == "ns"
            assert stats.current_active == 1
            assert stats.acquired == 1
            assert stats.released == 0

        # After release
        stats = bulkhead.get_stats("test_tool", "ns")
        assert stats.current_active == 0
        assert stats.released == 1

    @pytest.mark.asyncio
    async def test_peak_active_tracking(self):
        """Test peak_active is tracked correctly."""
        config = BulkheadConfig(default_limit=5)
        bulkhead = Bulkhead(config)

        async def task():
            async with bulkhead.acquire("test_tool"):
                await asyncio.sleep(0.02)

        # Run 3 concurrent
        await asyncio.gather(*[task() for _ in range(3)])

        stats = bulkhead.get_stats("test_tool")
        assert stats.peak_active == 3

    @pytest.mark.asyncio
    async def test_get_all_stats(self):
        """Test getting all statistics."""
        bulkhead = Bulkhead()

        async with bulkhead.acquire("tool_a", "ns1"):
            pass
        async with bulkhead.acquire("tool_b", "ns2"):
            pass

        all_stats = bulkhead.get_all_stats()
        assert len(all_stats) == 2
        assert "ns1.tool_a" in all_stats
        assert "ns2.tool_b" in all_stats


class TestBulkheadDynamicConfig:
    """Test dynamic configuration updates."""

    @pytest.mark.asyncio
    async def test_configure_tool(self):
        """Test updating tool limit dynamically."""
        bulkhead = Bulkhead()

        # Initially uses default (10)
        assert bulkhead.get_tool_limit("test_tool") == 10

        # Update limit
        bulkhead.configure_tool("test_tool", 5)
        assert bulkhead.get_tool_limit("test_tool") == 5

    @pytest.mark.asyncio
    async def test_configure_namespace(self):
        """Test updating namespace limit dynamically."""
        bulkhead = Bulkhead()

        # Initially no namespace limit
        assert bulkhead.get_namespace_limit("test_ns") is None

        # Add limit
        bulkhead.configure_namespace("test_ns", 3)
        assert bulkhead.get_namespace_limit("test_ns") == 3


class TestBulkheadQueueDepth:
    """Test queue depth monitoring."""

    @pytest.mark.asyncio
    async def test_queue_depth(self):
        """Test queue depth reporting."""
        config = BulkheadConfig(default_limit=1)
        bulkhead = Bulkhead(config)

        # Initially no queue
        assert await bulkhead.get_queue_depth("test_tool") == 0

        # Block the tool
        async def blocker():
            async with bulkhead.acquire("test_tool"):
                await asyncio.sleep(0.5)

        task = asyncio.create_task(blocker())
        await asyncio.sleep(0.01)  # Let it acquire

        # Now at limit, queue depth should show slots used
        depth = await bulkhead.get_queue_depth("test_tool")
        assert depth == 1

        # Cleanup
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestBulkheadStatsModel:
    """Test BulkheadStats Pydantic model."""

    def test_stats_model_creation(self):
        """Test creating stats model."""
        stats = BulkheadStats(
            tool="my_tool",
            namespace="my_ns",
            acquired=10,
            released=8,
            current_active=2,
            peak_active=5,
        )

        assert stats.tool == "my_tool"
        assert stats.namespace == "my_ns"
        assert stats.acquired == 10
        assert stats.released == 8
        assert stats.current_active == 2
        assert stats.peak_active == 5

    def test_stats_validation(self):
        """Test stats validation."""
        with pytest.raises(ValueError):
            BulkheadStats(
                tool="test",
                namespace="ns",
                acquired=-1,  # Must be >= 0
            )


class TestBulkheadFullError:
    """Test BulkheadFullError."""

    def test_error_message(self):
        """Test error message formatting."""
        error = BulkheadFullError(
            tool="slow_api",
            namespace="external",
            limit_type=BulkheadLimitType.TOOL,
            limit=2,
            timeout=1.5,
        )

        assert "slow_api" in str(error)
        assert "tool limit: 2" in str(error)
        assert "1.5s timeout" in str(error)
        assert error.limit_type == BulkheadLimitType.TOOL

    def test_error_without_timeout(self):
        """Test error message without timeout."""
        error = BulkheadFullError(
            tool="test",
            namespace="ns",
            limit_type=BulkheadLimitType.NAMESPACE,
            limit=5,
        )

        assert "timeout" not in str(error)
        assert "namespace limit: 5" in str(error)
