# tests/guards/test_plan_shape.py
"""Tests for PlanShapeGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.plan_shape import (
    PlanShapeConfig,
    PlanShapeGuard,
    PlanShapeViolationType,
    ToolCallSpec,
)


class TestPlanShapeGuard:
    """Tests for PlanShapeGuard."""

    @pytest.fixture
    def guard(self) -> PlanShapeGuard:
        """Default guard with low limits for testing."""
        return PlanShapeGuard(
            config=PlanShapeConfig(
                max_chain_length=5,
                max_unique_tools=5,
                max_fan_out=10,
                max_batch_size=20,
            )
        )

    def test_initial_state(self, guard: PlanShapeGuard):
        """Test initial state is empty."""
        state = guard.get_state()
        assert state.chain_depth == 0
        assert len(state.tools_seen) == 0
        assert state.total_calls == 0

    def test_check_allows_within_limits(self, guard: PlanShapeGuard):
        """Test check allows within limits."""
        result = guard.check("tool", {})
        assert result.allowed

    def test_record_call_increments_state(self, guard: PlanShapeGuard):
        """Test recording calls updates state."""
        guard.record_call("tool1")
        guard.record_call("tool2")
        guard.record_call("tool1")

        state = guard.get_state()
        assert state.chain_depth == 3
        assert state.tools_seen == {"tool1", "tool2"}
        assert state.total_calls == 3

    def test_chain_too_long_blocks(self, guard: PlanShapeGuard):
        """Test exceeding chain length blocks."""
        for i in range(5):
            guard.record_call(f"tool{i}")

        result = guard.check("tool_overflow", {})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.CHAIN_TOO_LONG.value for v in violations)

    def test_too_many_unique_tools_blocks(self, guard: PlanShapeGuard):
        """Test exceeding unique tools blocks."""
        for i in range(5):
            guard.record_call(f"tool_{i}")

        # Adding 6th unique tool should block
        result = guard.check("tool_6", {})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS.value for v in violations)

    def test_same_tool_doesnt_count_as_new(self, guard: PlanShapeGuard):
        """Test same tool doesn't increment unique count."""
        for _ in range(10):
            guard.record_call("same_tool")

        # Same tool should be allowed (only 1 unique)
        guard.check("same_tool", {})
        # Chain might be exceeded, but unique tools should be fine
        state = guard.get_state()
        assert len(state.tools_seen) == 1


class TestPlanShapeGuardPlan:
    """Tests for plan checking."""

    @pytest.fixture
    def guard(self) -> PlanShapeGuard:
        return PlanShapeGuard(
            config=PlanShapeConfig(
                max_chain_length=5,
                max_unique_tools=5,
                max_fan_out=10,
                max_batch_size=20,
                fan_out_threshold=5,
            )
        )

    def test_check_plan_allows_valid(self, guard: PlanShapeGuard):
        """Test check_plan allows valid plan."""
        plan = [
            ToolCallSpec(tool_name="tool1", arguments={"x": 1}),
            ToolCallSpec(tool_name="tool2", arguments={"x": 2}),
        ]
        result = guard.check_plan(plan)
        assert result.allowed

    def test_check_plan_batch_too_large(self, guard: PlanShapeGuard):
        """Test check_plan blocks oversized batch."""
        plan = [
            ToolCallSpec(tool_name=f"tool{i}")
            for i in range(25)  # Exceeds max_batch_size=20
        ]
        result = guard.check_plan(plan)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.BATCH_TOO_LARGE.value for v in violations)

    def test_check_plan_too_many_unique(self, guard: PlanShapeGuard):
        """Test check_plan blocks too many unique tools."""
        plan = [
            ToolCallSpec(tool_name=f"unique_tool_{i}")
            for i in range(10)  # Exceeds max_unique_tools=5
        ]
        result = guard.check_plan(plan)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS.value for v in violations)

    def test_check_plan_fan_out_too_large(self, guard: PlanShapeGuard):
        """Test check_plan blocks excessive fan-out."""
        # All calls depend on same source = fan-out
        plan = [
            ToolCallSpec(tool_name="worker", depends_on=["source"])
            for _ in range(15)  # Exceeds max_fan_out=10
        ]
        result = guard.check_plan(plan)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.FAN_OUT_TOO_LARGE.value for v in violations)

    def test_check_plan_fan_out_fan_in_detected(self, guard: PlanShapeGuard):
        """Test check_plan detects fan-out-fan-in pattern."""
        # Many calls depend on same source = map-reduce bomb
        plan = [
            ToolCallSpec(tool_name="mapper", depends_on=["source"])
            for _ in range(6)  # Exceeds fan_out_threshold=5
        ]
        result = guard.check_plan(plan)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.FAN_OUT_FAN_IN_DETECTED.value for v in violations)

    def test_check_plan_chain_length(self, guard: PlanShapeGuard):
        """Test check_plan validates chain length."""
        # Create deep dependency chain
        plan = [
            ToolCallSpec(
                tool_name=f"tool{i}",
                depends_on=[f"dep{j}" for j in range(10)],  # Long dependency list
            )
            for i in range(3)
        ]
        result = guard.check_plan(plan)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.CHAIN_TOO_LONG.value for v in violations)


class TestPlanShapeGuardBatch:
    """Tests for batch checking."""

    @pytest.fixture
    def guard(self) -> PlanShapeGuard:
        return PlanShapeGuard(
            config=PlanShapeConfig(
                max_batch_size=10,
                max_fan_out=5,
                max_unique_tools=3,
            )
        )

    def test_check_batch_allows_valid(self, guard: PlanShapeGuard):
        """Test check_batch allows valid batch."""
        calls = [("tool", {"x": i}) for i in range(3)]
        result = guard.check_batch(calls)
        assert result.allowed

    def test_check_batch_too_large(self, guard: PlanShapeGuard):
        """Test check_batch blocks oversized batch."""
        calls = [("tool", {}) for _ in range(15)]
        result = guard.check_batch(calls)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.BATCH_TOO_LARGE.value for v in violations)

    def test_check_batch_fan_out_exceeded(self, guard: PlanShapeGuard):
        """Test check_batch blocks excessive fan-out."""
        calls = [("tool", {}) for _ in range(8)]  # Exceeds max_fan_out=5
        result = guard.check_batch(calls)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.FAN_OUT_TOO_LARGE.value for v in violations)

    def test_check_batch_unique_tools(self, guard: PlanShapeGuard):
        """Test check_batch validates unique tools."""
        calls = [
            ("tool1", {}),
            ("tool2", {}),
            ("tool3", {}),
            ("tool4", {}),  # 4th unique, exceeds max_unique_tools=3
        ]
        result = guard.check_batch(calls)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == PlanShapeViolationType.TOO_MANY_UNIQUE_TOOLS.value for v in violations)

    def test_check_batch_considers_existing_state(self, guard: PlanShapeGuard):
        """Test batch check considers already seen tools."""
        guard.record_call("existing1")
        guard.record_call("existing2")

        # Now batch with one more unique should exceed limit
        calls = [("new_tool1", {}), ("new_tool2", {})]
        result = guard.check_batch(calls)
        assert result.blocked


class TestPlanShapeGuardState:
    """Tests for state management."""

    def test_record_fan_out(self):
        """Test recording fan-out events."""
        guard = PlanShapeGuard()

        guard.record_fan_out(10)
        state = guard.get_state()
        assert state.current_fan_out == 10
        assert state.max_fan_out_seen == 10

        guard.record_fan_out(5)
        state = guard.get_state()
        assert state.current_fan_out == 5
        assert state.max_fan_out_seen == 10  # Max preserved

    def test_record_fan_in(self):
        """Test recording fan-in events."""
        guard = PlanShapeGuard()

        guard.record_fan_out(10)
        guard.record_fan_in()

        state = guard.get_state()
        assert state.current_fan_out == 0
        assert state.max_fan_out_seen == 10

    def test_reset(self):
        """Test reset clears all state."""
        guard = PlanShapeGuard()

        guard.record_call("tool1")
        guard.record_call("tool2")
        guard.record_fan_out(10)

        guard.reset()

        state = guard.get_state()
        assert state.chain_depth == 0
        assert len(state.tools_seen) == 0
        assert state.current_fan_out == 0
        assert state.max_fan_out_seen == 0

    def test_warn_enforcement_level(self):
        """Test warn enforcement level."""
        guard = PlanShapeGuard(
            config=PlanShapeConfig(
                max_chain_length=2,
                enforcement_level=EnforcementLevel.WARN,
            )
        )

        guard.record_call("tool1")
        guard.record_call("tool2")

        result = guard.check("tool3", {})
        assert result.verdict == GuardVerdict.WARN
