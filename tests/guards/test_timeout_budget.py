# tests/guards/test_timeout_budget.py
"""Tests for TimeoutBudgetGuard."""

import time

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.timeout_budget import (
    BudgetStatus,
    DegradeAction,
    TimeoutBudgetConfig,
    TimeoutBudgetGuard,
)


class TestTimeoutBudgetGuard:
    """Tests for TimeoutBudgetGuard."""

    @pytest.fixture
    def guard(self) -> TimeoutBudgetGuard:
        """Guard with short timeout for testing."""
        return TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(
                per_turn_budget_ms=1000,  # 1 second
                soft_budget_ratio=0.5,  # 500ms soft limit
            )
        )

    def test_initial_state(self, guard: TimeoutBudgetGuard):
        """Test initial state."""
        state = guard.get_state()
        assert state.turn_start_ms is None
        assert state.turn_elapsed_ms == 0
        assert state.status == BudgetStatus.OK

    def test_start_turn(self, guard: TimeoutBudgetGuard):
        """Test starting a turn."""
        guard.start_turn()
        state = guard.get_state()
        assert state.turn_start_ms is not None
        assert state.status == BudgetStatus.OK

    def test_check_allows_within_budget(self, guard: TimeoutBudgetGuard):
        """Test check allows within budget."""
        guard.start_turn()
        result = guard.check("tool", {})
        assert result.allowed

    def test_check_blocks_after_timeout(self):
        """Test check blocks after timeout exceeded."""
        guard = TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(per_turn_budget_ms=10)  # 10ms
        )
        guard.start_turn()
        time.sleep(0.02)  # 20ms
        result = guard.check("tool", {})
        assert result.blocked
        assert "budget exceeded" in result.reason.lower()

    def test_soft_limit_warning(self):
        """Test soft limit triggers warning."""
        guard = TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(
                per_turn_budget_ms=100,  # 100ms
                soft_budget_ratio=0.3,  # 30ms soft limit
            )
        )
        guard.start_turn()
        time.sleep(0.05)  # 50ms - past soft limit but under hard
        result = guard.check("tool", {})
        assert result.verdict == GuardVerdict.WARN
        assert guard.is_degraded()

    def test_degrade_actions_set(self):
        """Test degrade actions are set when soft limit exceeded."""
        guard = TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(
                per_turn_budget_ms=100,
                soft_budget_ratio=0.3,
                degrade_actions=[
                    DegradeAction.DISABLE_RETRIES,
                    DegradeAction.REDUCE_PARALLELISM,
                ],
            )
        )
        guard.start_turn()
        time.sleep(0.05)
        guard.check("tool", {})

        assert guard.should_disable_retries()
        assert guard.should_reduce_parallelism()

    def test_record_execution(self, guard: TimeoutBudgetGuard):
        """Test recording execution duration."""
        guard.start_turn()
        guard.record_execution(100)
        guard.record_execution(200)

        state = guard.get_state()
        assert state.executions == 2
        assert state.total_execution_ms == 300

    def test_get_remaining_budget(self, guard: TimeoutBudgetGuard):
        """Test getting remaining budget."""
        remaining = guard.get_remaining_budget_ms()
        assert remaining == 1000  # Full budget when not started

        guard.start_turn()
        remaining = guard.get_remaining_budget_ms()
        assert remaining <= 1000
        assert remaining > 0

    def test_end_turn(self, guard: TimeoutBudgetGuard):
        """Test ending a turn."""
        guard.start_turn()
        guard.record_execution(100)
        time.sleep(0.01)

        state = guard.end_turn()
        assert state.executions == 1
        assert state.turn_elapsed_ms > 0

        # After end, start should be None
        current_state = guard.get_state()
        assert current_state.turn_start_ms is None

    def test_plan_budget(self):
        """Test plan-level budget."""
        guard = TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(
                per_turn_budget_ms=1000,
                per_plan_budget_ms=50,  # 50ms plan budget
            )
        )
        guard.start_plan()
        guard.start_turn()
        time.sleep(0.06)  # Exceed plan budget

        result = guard.check("tool", {})
        assert result.blocked
        assert "plan" in result.reason.lower()

    def test_reset(self, guard: TimeoutBudgetGuard):
        """Test reset clears all state."""
        guard.start_turn()
        guard.record_execution(100)
        guard._state.status = BudgetStatus.SOFT_LIMIT

        guard.reset()

        state = guard.get_state()
        assert state.turn_start_ms is None
        assert state.executions == 0
        assert state.status == BudgetStatus.OK

    def test_warn_enforcement_level(self):
        """Test warn enforcement level."""
        guard = TimeoutBudgetGuard(
            config=TimeoutBudgetConfig(
                per_turn_budget_ms=10,
                enforcement_level=EnforcementLevel.WARN,
            )
        )
        guard.start_turn()
        time.sleep(0.02)

        result = guard.check("tool", {})
        assert result.verdict == GuardVerdict.WARN

    def test_no_check_before_start(self, guard: TimeoutBudgetGuard):
        """Test check before starting turn is allowed."""
        # Turn not started, should allow
        result = guard.check("tool", {})
        assert result.allowed
