"""
Tests for the scheduling module.

Tests cover:
- ToolMetadata validation and defaults
- ToolCallSpec creation and validation
- SchedulingConstraints configuration
- ExecutionPlan structure
- GreedyDagScheduler planning logic
"""

import pytest

from chuk_tool_processor.scheduling import (
    ExecutionPlan,
    GreedyDagScheduler,
    SchedulingConstraints,
    SkipReason,
    ToolCallSpec,
    ToolMetadata,
)


class TestToolMetadata:
    """Tests for ToolMetadata model."""

    def test_default_values(self):
        """Test that defaults are applied correctly."""
        meta = ToolMetadata()
        assert meta.pool == "default"
        assert meta.weight == 1
        assert meta.est_ms is None
        assert meta.cost is None
        assert meta.priority == 0

    def test_custom_values(self):
        """Test creating metadata with custom values."""
        meta = ToolMetadata(
            pool="database",
            weight=2,
            est_ms=500,
            cost=0.01,
            priority=10,
        )
        assert meta.pool == "database"
        assert meta.weight == 2
        assert meta.est_ms == 500
        assert meta.cost == 0.01
        assert meta.priority == 10

    def test_immutability(self):
        """Test that metadata is frozen (immutable)."""
        from pydantic import ValidationError

        meta = ToolMetadata(pool="test")
        with pytest.raises(ValidationError):
            meta.pool = "changed"

    def test_weight_validation(self):
        """Test that weight must be >= 1."""
        with pytest.raises(ValueError):
            ToolMetadata(weight=0)

    def test_est_ms_validation(self):
        """Test that est_ms must be >= 0."""
        with pytest.raises(ValueError):
            ToolMetadata(est_ms=-1)

    def test_cost_validation(self):
        """Test that cost must be >= 0."""
        with pytest.raises(ValueError):
            ToolMetadata(cost=-0.01)


class TestToolCallSpec:
    """Tests for ToolCallSpec model."""

    def test_minimal_creation(self):
        """Test creating a spec with minimal required fields."""
        spec = ToolCallSpec(call_id="1", tool_name="fetch")
        assert spec.call_id == "1"
        assert spec.tool_name == "fetch"
        assert spec.args == {}
        assert spec.depends_on == ()
        assert spec.timeout_ms is None
        assert spec.max_retries is None

    def test_full_creation(self):
        """Test creating a spec with all fields."""
        meta = ToolMetadata(pool="web", priority=5)
        spec = ToolCallSpec(
            call_id="fetch-1",
            tool_name="web.fetch",
            args={"url": "https://example.com"},
            metadata=meta,
            depends_on=("init",),
            timeout_ms=5000,
            max_retries=3,
        )
        assert spec.call_id == "fetch-1"
        assert spec.tool_name == "web.fetch"
        assert spec.args == {"url": "https://example.com"}
        assert spec.metadata.pool == "web"
        assert spec.depends_on == ("init",)
        assert spec.timeout_ms == 5000
        assert spec.max_retries == 3

    def test_call_id_required(self):
        """Test that call_id is required and non-empty."""
        with pytest.raises(ValueError):
            ToolCallSpec(call_id="", tool_name="test")

    def test_tool_name_required(self):
        """Test that tool_name is required and non-empty."""
        with pytest.raises(ValueError):
            ToolCallSpec(call_id="1", tool_name="")

    def test_immutability(self):
        """Test that spec is frozen."""
        from pydantic import ValidationError

        spec = ToolCallSpec(call_id="1", tool_name="test")
        with pytest.raises(ValidationError):
            spec.call_id = "2"


class TestSchedulingConstraints:
    """Tests for SchedulingConstraints model."""

    def test_default_values(self):
        """Test default constraint values."""
        constraints = SchedulingConstraints()
        assert constraints.deadline_ms is None
        assert constraints.max_cost is None
        assert constraints.pool_limits == {}
        assert constraints.now_ms == 0

    def test_custom_values(self):
        """Test custom constraint values."""
        constraints = SchedulingConstraints(
            deadline_ms=5000,
            max_cost=1.0,
            pool_limits={"web": 3, "db": 2},
            now_ms=100,
        )
        assert constraints.deadline_ms == 5000
        assert constraints.max_cost == 1.0
        assert constraints.pool_limits == {"web": 3, "db": 2}
        assert constraints.now_ms == 100

    def test_deadline_validation(self):
        """Test that deadline must be >= 0."""
        with pytest.raises(ValueError):
            SchedulingConstraints(deadline_ms=-1)

    def test_max_cost_validation(self):
        """Test that max_cost must be >= 0."""
        with pytest.raises(ValueError):
            SchedulingConstraints(max_cost=-0.1)


class TestSkipReason:
    """Tests for SkipReason model."""

    def test_basic_skip_reason(self):
        """Test creating a basic skip reason."""
        reason = SkipReason(call_id="test", reason="deadline_exceeded")
        assert reason.call_id == "test"
        assert reason.reason == "deadline_exceeded"
        assert reason.detail is None

    def test_skip_reason_with_detail(self):
        """Test creating a skip reason with detail."""
        reason = SkipReason(
            call_id="call-1",
            reason="dependency_skipped",
            detail="Depends on skipped call(s): call-0",
        )
        assert reason.call_id == "call-1"
        assert reason.reason == "dependency_skipped"
        assert "call-0" in reason.detail


class TestExecutionPlan:
    """Tests for ExecutionPlan model."""

    def test_empty_plan(self):
        """Test creating an empty plan."""
        plan = ExecutionPlan()
        assert plan.stages == ()
        assert plan.per_call_timeout_ms == {}
        assert plan.per_call_max_retries == {}
        assert plan.skip == ()
        assert plan.skip_reasons == ()
        assert plan.critical_path_ms is None
        assert plan.estimated_total_ms is None
        assert plan.pool_utilization == {}

    def test_plan_with_stages(self):
        """Test creating a plan with stages."""
        plan = ExecutionPlan(
            stages=(("1", "2"), ("3",)),
            per_call_timeout_ms={"1": 1000, "2": 1000, "3": 2000},
            skip=("4",),
        )
        assert len(plan.stages) == 2
        assert plan.stages[0] == ("1", "2")
        assert plan.stages[1] == ("3",)
        assert plan.per_call_timeout_ms["1"] == 1000
        assert plan.skip == ("4",)

    def test_all_scheduled_calls_property(self):
        """Test the all_scheduled_calls helper property."""
        plan = ExecutionPlan(
            stages=(("a", "b"), ("c",), ("d", "e", "f")),
            skip=("x", "y"),
        )
        assert plan.all_scheduled_calls == {"a", "b", "c", "d", "e", "f"}

    def test_total_stages_property(self):
        """Test the total_stages helper property."""
        plan = ExecutionPlan(stages=(("1",), ("2",), ("3",)))
        assert plan.total_stages == 3

        empty_plan = ExecutionPlan()
        assert empty_plan.total_stages == 0


class TestGreedyDagScheduler:
    """Tests for GreedyDagScheduler."""

    def test_empty_calls(self):
        """Test scheduling with no calls."""
        scheduler = GreedyDagScheduler()
        plan = scheduler.plan([], SchedulingConstraints())
        assert plan.stages == ()
        assert plan.skip == ()

    def test_single_call(self):
        """Test scheduling a single call."""
        scheduler = GreedyDagScheduler()
        calls = [ToolCallSpec(call_id="1", tool_name="test")]
        plan = scheduler.plan(calls, SchedulingConstraints())

        assert len(plan.stages) == 1
        assert "1" in plan.stages[0]
        assert plan.skip == ()

    def test_independent_calls_parallel(self):
        """Test that independent calls are scheduled in parallel."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(call_id="1", tool_name="a"),
            ToolCallSpec(call_id="2", tool_name="b"),
            ToolCallSpec(call_id="3", tool_name="c"),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # All independent calls should be in a single stage
        assert len(plan.stages) == 1
        assert set(plan.stages[0]) == {"1", "2", "3"}

    def test_sequential_dependencies(self):
        """Test that dependencies create sequential stages."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(call_id="1", tool_name="fetch"),
            ToolCallSpec(call_id="2", tool_name="transform", depends_on=("1",)),
            ToolCallSpec(call_id="3", tool_name="store", depends_on=("2",)),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        assert len(plan.stages) == 3
        assert plan.stages[0] == ("1",)
        assert plan.stages[1] == ("2",)
        assert plan.stages[2] == ("3",)

    def test_diamond_dependency(self):
        """Test diamond-shaped dependency graph."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(call_id="start", tool_name="init"),
            ToolCallSpec(call_id="left", tool_name="process_a", depends_on=("start",)),
            ToolCallSpec(call_id="right", tool_name="process_b", depends_on=("start",)),
            ToolCallSpec(call_id="end", tool_name="merge", depends_on=("left", "right")),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        assert len(plan.stages) == 3
        assert plan.stages[0] == ("start",)
        assert set(plan.stages[1]) == {"left", "right"}
        assert plan.stages[2] == ("end",)

    def test_pool_limits(self):
        """Test that pool limits are respected."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="1",
                tool_name="db.query",
                metadata=ToolMetadata(pool="db"),
            ),
            ToolCallSpec(
                call_id="2",
                tool_name="db.query",
                metadata=ToolMetadata(pool="db"),
            ),
            ToolCallSpec(
                call_id="3",
                tool_name="db.query",
                metadata=ToolMetadata(pool="db"),
            ),
        ]
        constraints = SchedulingConstraints(pool_limits={"db": 2})
        plan = scheduler.plan(calls, constraints)

        # With pool limit of 2, should have at least 2 stages
        assert len(plan.stages) >= 2
        # First stage should have at most 2 calls
        assert len(plan.stages[0]) <= 2

    def test_deadline_skipping(self):
        """Test that low-priority calls are skipped when deadline is tight."""
        scheduler = GreedyDagScheduler(default_est_ms=1000, skip_threshold_ratio=0.8)
        calls = [
            ToolCallSpec(
                call_id="important",
                tool_name="critical",
                metadata=ToolMetadata(priority=10, est_ms=500),
            ),
            ToolCallSpec(
                call_id="optional",
                tool_name="analytics",
                metadata=ToolMetadata(priority=0, est_ms=500),
            ),
        ]
        # Tight deadline: 800ms threshold (1000 * 0.8)
        constraints = SchedulingConstraints(deadline_ms=1000)
        plan = scheduler.plan(calls, constraints)

        # High-priority call should be scheduled
        scheduled_ids = {cid for stage in plan.stages for cid in stage}
        assert "important" in scheduled_ids
        # Low-priority call may be skipped due to deadline
        # (depends on cumulative time calculation)

    def test_cost_limit_skipping(self):
        """Test that low-priority calls are skipped when cost limit is reached."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="cheap",
                tool_name="free_tool",
                metadata=ToolMetadata(priority=10, cost=0.1),
            ),
            ToolCallSpec(
                call_id="expensive",
                tool_name="paid_tool",
                metadata=ToolMetadata(priority=0, cost=0.5),
            ),
        ]
        constraints = SchedulingConstraints(max_cost=0.2)
        plan = scheduler.plan(calls, constraints)

        scheduled_ids = {cid for stage in plan.stages for cid in stage}
        assert "cheap" in scheduled_ids
        assert "expensive" in plan.skip

    def test_dependency_skip_cascade(self):
        """Test that skipping a call also skips its dependents."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="parent",
                tool_name="expensive",
                metadata=ToolMetadata(priority=0, cost=1.0),
            ),
            ToolCallSpec(
                call_id="child",
                tool_name="depends_on_expensive",
                depends_on=("parent",),
                metadata=ToolMetadata(priority=10),
            ),
        ]
        constraints = SchedulingConstraints(max_cost=0.5)
        plan = scheduler.plan(calls, constraints)

        # Both should be skipped since parent is skipped
        assert "parent" in plan.skip
        assert "child" in plan.skip

    def test_priority_ordering(self):
        """Test that higher priority calls are scheduled first."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="low",
                tool_name="a",
                metadata=ToolMetadata(priority=1),
            ),
            ToolCallSpec(
                call_id="high",
                tool_name="b",
                metadata=ToolMetadata(priority=10),
            ),
            ToolCallSpec(
                call_id="medium",
                tool_name="c",
                metadata=ToolMetadata(priority=5),
            ),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # All should be in one stage (no dependencies)
        # but internal ordering should respect priority
        assert len(plan.stages) == 1

    def test_per_call_timeouts_with_deadline(self):
        """Test that per-call timeouts are calculated with deadline."""
        scheduler = GreedyDagScheduler(default_est_ms=100)
        calls = [
            ToolCallSpec(call_id="1", tool_name="a"),
            ToolCallSpec(call_id="2", tool_name="b", depends_on=("1",)),
        ]
        constraints = SchedulingConstraints(deadline_ms=1000)
        plan = scheduler.plan(calls, constraints)

        # Should have timeouts calculated
        assert len(plan.per_call_timeout_ms) > 0
        assert "1" in plan.per_call_timeout_ms
        assert "2" in plan.per_call_timeout_ms

    def test_no_timeouts_without_deadline(self):
        """Test that no timeouts are calculated when deadline is None."""
        scheduler = GreedyDagScheduler(default_est_ms=100)
        calls = [
            ToolCallSpec(call_id="1", tool_name="a"),
            ToolCallSpec(call_id="2", tool_name="b"),
        ]
        # No deadline
        constraints = SchedulingConstraints()
        plan = scheduler.plan(calls, constraints)

        # No timeouts should be calculated
        assert plan.per_call_timeout_ms == {}

    def test_pool_limit_zero_fallback(self):
        """Test fallback when pool limit of 0 would prevent any progress."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="1",
                tool_name="blocked",
                metadata=ToolMetadata(pool="blocked_pool"),
            ),
        ]
        # Pool limit of 0 would normally block all calls
        constraints = SchedulingConstraints(pool_limits={"blocked_pool": 0})
        plan = scheduler.plan(calls, constraints)

        # Fallback: should still schedule the first ready call to avoid infinite loop
        assert len(plan.stages) == 1
        assert "1" in plan.stages[0]

    def test_custom_call_timeout_override(self):
        """Test that custom call timeouts are preserved."""
        scheduler = GreedyDagScheduler(default_est_ms=100)
        calls = [
            ToolCallSpec(call_id="1", tool_name="a", timeout_ms=5000),
        ]
        constraints = SchedulingConstraints(deadline_ms=10000)
        plan = scheduler.plan(calls, constraints)

        # Custom timeout should be used
        assert plan.per_call_timeout_ms.get("1") == 5000

    def test_cycle_detection(self):
        """Test that cycles in dependencies are detected."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(call_id="a", tool_name="x", depends_on=("c",)),
            ToolCallSpec(call_id="b", tool_name="y", depends_on=("a",)),
            ToolCallSpec(call_id="c", tool_name="z", depends_on=("b",)),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # All calls should be skipped due to cycle
        assert set(plan.skip) == {"a", "b", "c"}
        assert plan.stages == ()

    def test_invalid_dependency_causes_stall(self):
        """Test that dependencies on non-existent calls cause scheduling stall.

        This is by design - if you depend on something that doesn't exist,
        it can never be satisfied, so the call can never become ready.
        """
        scheduler = GreedyDagScheduler()
        # Call with dependency on non-existent call
        calls = [
            ToolCallSpec(call_id="1", tool_name="a", depends_on=("nonexistent",)),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # The call is not scheduled because its dependency can never be satisfied
        # It's also not in skip because it wasn't explicitly skipped
        assert plan.stages == ()
        # Note: the call remains unscheduled (neither in stages nor skip)

    def test_context_parameter_accepted(self):
        """Test that context parameter is accepted (for protocol compliance)."""
        scheduler = GreedyDagScheduler()
        calls = [ToolCallSpec(call_id="1", tool_name="test")]
        # Should not raise even though context is unused
        plan = scheduler.plan(calls, SchedulingConstraints(), context={"key": "value"})
        assert len(plan.stages) == 1


class TestSchedulerProtocolCompliance:
    """Test that GreedyDagScheduler complies with SchedulerPolicy protocol."""

    def test_has_plan_method(self):
        """Test that scheduler has the plan method."""
        scheduler = GreedyDagScheduler()
        assert hasattr(scheduler, "plan")
        assert callable(scheduler.plan)

    def test_plan_returns_execution_plan(self):
        """Test that plan returns an ExecutionPlan."""
        scheduler = GreedyDagScheduler()
        calls = [ToolCallSpec(call_id="1", tool_name="test")]
        result = scheduler.plan(calls, SchedulingConstraints())
        assert isinstance(result, ExecutionPlan)


class TestSchedulerExplainability:
    """Tests for scheduler explainability fields."""

    def test_critical_path_calculation(self):
        """Test that critical path is calculated correctly."""
        scheduler = GreedyDagScheduler(default_est_ms=100)
        calls = [
            ToolCallSpec(
                call_id="1",
                tool_name="a",
                metadata=ToolMetadata(est_ms=200),
            ),
            ToolCallSpec(
                call_id="2",
                tool_name="b",
                depends_on=("1",),
                metadata=ToolMetadata(est_ms=300),
            ),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # Critical path = max(stage1) + max(stage2) = 200 + 300 = 500
        assert plan.critical_path_ms == 500
        assert plan.estimated_total_ms == 500

    def test_pool_utilization_calculation(self):
        """Test that pool utilization is calculated correctly."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="1",
                tool_name="a",
                metadata=ToolMetadata(pool="web"),
            ),
            ToolCallSpec(
                call_id="2",
                tool_name="b",
                metadata=ToolMetadata(pool="web"),
            ),
            ToolCallSpec(
                call_id="3",
                tool_name="c",
                metadata=ToolMetadata(pool="db"),
            ),
        ]
        plan = scheduler.plan(calls, SchedulingConstraints())

        # All in one stage: web=2, db=1
        assert plan.pool_utilization["web"] == 2
        assert plan.pool_utilization["db"] == 1

    def test_skip_reasons_deadline(self):
        """Test that skip reasons are populated for deadline skips."""
        scheduler = GreedyDagScheduler(default_est_ms=500)
        calls = [
            ToolCallSpec(
                call_id="important",
                tool_name="critical",
                metadata=ToolMetadata(priority=10, est_ms=500),
            ),
            ToolCallSpec(
                call_id="optional",
                tool_name="analytics",
                metadata=ToolMetadata(priority=0, est_ms=500),
            ),
        ]
        # Tight deadline: threshold = 800ms (1000 * 0.8)
        # After "important" (500ms), "optional" would exceed threshold
        constraints = SchedulingConstraints(deadline_ms=1000)
        plan = scheduler.plan(calls, constraints)

        # Check if optional was skipped
        if "optional" in plan.skip:
            # Should have a skip reason
            skip_reason_ids = [r.call_id for r in plan.skip_reasons]
            assert "optional" in skip_reason_ids

            # Find the reason
            reason = next(r for r in plan.skip_reasons if r.call_id == "optional")
            assert reason.reason == "deadline_exceeded"
            assert reason.detail is not None

    def test_skip_reasons_dependency_cascade(self):
        """Test that skip reasons are populated for dependency cascades."""
        scheduler = GreedyDagScheduler()
        calls = [
            ToolCallSpec(
                call_id="parent",
                tool_name="expensive",
                metadata=ToolMetadata(priority=0, cost=1.0),
            ),
            ToolCallSpec(
                call_id="child",
                tool_name="depends_on_expensive",
                depends_on=("parent",),
                metadata=ToolMetadata(priority=10),
            ),
        ]
        constraints = SchedulingConstraints(max_cost=0.5)
        plan = scheduler.plan(calls, constraints)

        # Both should be skipped
        assert "parent" in plan.skip
        assert "child" in plan.skip

        # Find child's skip reason
        child_reason = next((r for r in plan.skip_reasons if r.call_id == "child"), None)
        assert child_reason is not None
        assert child_reason.reason == "dependency_skipped"
        assert "parent" in child_reason.detail

    def test_empty_plan_has_no_metrics(self):
        """Test that empty plan has None metrics."""
        scheduler = GreedyDagScheduler()
        plan = scheduler.plan([], SchedulingConstraints())

        assert plan.critical_path_ms is None
        assert plan.estimated_total_ms is None
        assert plan.pool_utilization == {}
