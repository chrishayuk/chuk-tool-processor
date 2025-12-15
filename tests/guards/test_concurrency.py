# tests/guards/test_concurrency.py
"""Tests for ConcurrencyGuard."""

import pytest

from chuk_tool_processor.guards.concurrency import (
    ConcurrencyConfig,
    ConcurrencyGuard,
    ConcurrencyLimitExceeded,
)


class TestConcurrencyGuard:
    """Tests for ConcurrencyGuard."""

    @pytest.fixture
    def guard(self) -> ConcurrencyGuard:
        """Default guard."""
        return ConcurrencyGuard(
            config=ConcurrencyConfig(
                global_max=5,
                default_namespace_max=10,  # Higher than global for isolated testing
                default_tool_max=2,
            )
        )

    def test_initial_state(self, guard: ConcurrencyGuard):
        """Test initial state is empty."""
        state = guard.get_state()
        assert state.global_in_flight == 0
        assert len(state.tool_in_flight) == 0

    def test_check_allows_within_limit(self, guard: ConcurrencyGuard):
        """Test check allows when within limits."""
        result = guard.check("tool", {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_acquire_increments_counters(self, guard: ConcurrencyGuard):
        """Test acquire increments all counters."""
        result = await guard.acquire("ns.tool")
        assert result.allowed

        state = guard.get_state()
        assert state.global_in_flight == 1
        assert state.namespace_in_flight.get("ns") == 1
        assert state.tool_in_flight.get("ns.tool") == 1

    @pytest.mark.asyncio
    async def test_release_decrements_counters(self, guard: ConcurrencyGuard):
        """Test release decrements all counters."""
        await guard.acquire("ns.tool")
        await guard.release("ns.tool")

        state = guard.get_state()
        assert state.global_in_flight == 0
        assert state.namespace_in_flight.get("ns", 0) == 0
        assert state.tool_in_flight.get("ns.tool", 0) == 0

    @pytest.mark.asyncio
    async def test_global_limit_blocks(self, guard: ConcurrencyGuard):
        """Test global limit blocks when exceeded."""
        # Acquire up to global max
        for i in range(5):
            result = await guard.acquire(f"tool_{i}")
            assert result.allowed

        # Next should be blocked
        result = await guard.acquire("tool_overflow")
        assert result.blocked
        assert "global" in result.reason

    @pytest.mark.asyncio
    async def test_tool_limit_blocks(self, guard: ConcurrencyGuard):
        """Test per-tool limit blocks when exceeded."""
        # Acquire up to tool max
        for _ in range(2):
            result = await guard.acquire("my_tool")
            assert result.allowed

        # Next should be blocked
        result = await guard.acquire("my_tool")
        assert result.blocked
        assert "tool" in result.reason

    @pytest.mark.asyncio
    async def test_namespace_limit_blocks(self):
        """Test per-namespace limit blocks when exceeded."""
        # Create guard with low namespace limit
        guard = ConcurrencyGuard(
            config=ConcurrencyConfig(
                global_max=100,
                default_namespace_max=3,
                default_tool_max=10,
            )
        )
        # Acquire up to namespace max (3 different tools in same namespace)
        for i in range(3):
            result = await guard.acquire(f"ns.tool_{i}")
            assert result.allowed

        # Next should be blocked
        result = await guard.acquire("ns.tool_overflow")
        assert result.blocked
        assert "namespace" in result.reason

    @pytest.mark.asyncio
    async def test_session_limit(self):
        """Test per-session limit."""
        guard = ConcurrencyGuard(config=ConcurrencyConfig(global_max=100, per_session_max=2))

        for _ in range(2):
            result = await guard.acquire("tool", session_id="session1")
            assert result.allowed

        result = await guard.acquire("tool", session_id="session1")
        assert result.blocked
        assert "session" in result.reason

        # Different session should work
        result = await guard.acquire("tool", session_id="session2")
        assert result.allowed

    @pytest.mark.asyncio
    async def test_slot_context_manager(self, guard: ConcurrencyGuard):
        """Test slot context manager."""
        async with guard.slot("my_tool"):
            state = guard.get_state()
            assert state.global_in_flight == 1

        state = guard.get_state()
        assert state.global_in_flight == 0

    @pytest.mark.asyncio
    async def test_slot_raises_on_limit(self):
        """Test slot raises exception when limit exceeded."""
        guard = ConcurrencyGuard(config=ConcurrencyConfig(global_max=0))

        with pytest.raises(ConcurrencyLimitExceeded):
            async with guard.slot("tool"):
                pass

    def test_reset(self, guard: ConcurrencyGuard):
        """Test reset clears all state."""
        guard._state.global_in_flight = 5
        guard._state.tool_in_flight["tool"] = 3

        guard.reset()

        state = guard.get_state()
        assert state.global_in_flight == 0
        assert len(state.tool_in_flight) == 0

    def test_custom_limits(self):
        """Test custom per-tool and per-namespace limits."""
        guard = ConcurrencyGuard(
            config=ConcurrencyConfig(
                global_max=100,
                per_namespace_max={"special": 10},
                per_tool_max={"heavy_tool": 1},
            )
        )

        # Check that custom limits are used
        violations = guard._check_limits("heavy_tool", None)
        assert len(violations) == 0

        guard._state.tool_in_flight["heavy_tool"] = 1
        violations = guard._check_limits("heavy_tool", None)
        assert any("heavy_tool" in v for v in violations)

    def test_default_namespace_extraction(self, guard: ConcurrencyGuard):
        """Test namespace extraction from tool name."""
        assert guard._get_namespace("ns.tool") == "ns"
        assert guard._get_namespace("tool") == "default"
        assert guard._get_namespace("a.b.c") == "a.b"
