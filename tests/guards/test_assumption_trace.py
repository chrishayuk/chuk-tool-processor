# tests/guards/test_assumption_trace.py
"""Tests for AssumptionTraceGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.assumption_trace import (
    AssumptionTraceGuard,
    AssumptionTraceGuardConfig,
    inventory_sigma_constraints,
)


class TestAssumptionTraceGuard:
    """Tests for AssumptionTraceGuard."""

    @pytest.fixture
    def guard(self):
        """Guard with basic config."""
        return AssumptionTraceGuard(
            config=AssumptionTraceGuardConfig(
                tool_arg_constraints={
                    ("multiply", "a"): "sigma_daily",
                },
            )
        )

    @pytest.fixture
    def blocking_guard(self):
        """Guard that blocks on violations."""
        return AssumptionTraceGuard(
            config=AssumptionTraceGuardConfig(
                tool_arg_constraints={
                    ("multiply", "a"): "sigma_daily",
                },
                block_on_violation=True,
            )
        )

    def test_allows_when_no_assumptions(self, guard):
        """Test allows tool calls when no assumptions registered."""
        result = guard.check("multiply", {"a": 37, "b": 4.24})
        assert result.verdict == GuardVerdict.ALLOW

    def test_allows_matching_assumption(self, guard):
        """Test allows when tool arg matches assumption."""
        guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        result = guard.check("multiply", {"a": 11.1, "b": 4.24})
        assert result.verdict == GuardVerdict.ALLOW

    def test_warns_on_violation(self, guard):
        """Test warns when tool arg violates assumption."""
        guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        # Using 37 instead of 11.1 - the classic error
        result = guard.check("multiply", {"a": 37, "b": 4.24})
        assert result.verdict == GuardVerdict.WARN
        assert "ASSUMPTION_VIOLATION" in result.reason
        assert "sigma_daily" in result.reason
        assert "11.1" in result.reason
        assert "37" in result.reason

    def test_blocks_when_configured(self, blocking_guard):
        """Test blocks on violation when configured."""
        blocking_guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        result = blocking_guard.check("multiply", {"a": 37, "b": 4.24})
        assert result.blocked is True

    def test_tracks_violations(self, guard):
        """Test violations are tracked."""
        guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        guard.check("multiply", {"a": 37, "b": 4.24})

        violations = guard.get_violations()
        assert len(violations) == 1
        assert violations[0].expected_value == 11.1
        assert violations[0].actual_value == 37

    def test_respects_tolerance(self, guard):
        """Test respects numeric tolerance."""
        guard.register_assumption("sigma_daily", 11.1, "stated CV=0.3")

        # Close enough within relative tolerance (1%)
        result = guard.check("multiply", {"a": 11.11, "b": 4.24})
        assert result.verdict == GuardVerdict.ALLOW

    def test_records_tool_trace(self, guard):
        """Test records tool calls in trace."""
        guard.check("multiply", {"a": 37, "b": 18})
        guard.check("sqrt", {"x": 18})

        trace = guard.get_trace()
        assert len(trace) == 2
        assert trace[0].tool_name == "multiply"
        assert trace[1].tool_name == "sqrt"

    def test_reset_clears_state(self, guard):
        """Test reset clears all state."""
        guard.register_assumption("sigma_daily", 11.1, "")
        guard.check("multiply", {"a": 37, "b": 4.24})

        guard.reset()

        assert len(guard.get_assumptions()) == 0
        assert len(guard.get_trace()) == 0
        assert len(guard.get_violations()) == 0

    def test_namespaced_tool_matching(self, guard):
        """Test matches namespaced tool names."""
        guard.register_assumption("sigma_daily", 11.1, "")

        # Should match "multiply" even with namespace
        result = guard.check("math.multiply", {"a": 37, "b": 4.24})
        assert result.verdict == GuardVerdict.WARN

    def test_get_status(self, guard):
        """Test get_status returns state."""
        guard.register_assumption("sigma_daily", 11.1, "CV=0.3")
        guard.check("multiply", {"a": 37, "b": 4.24})

        status = guard.get_status()
        assert "assumptions" in status
        assert "sigma_daily" in status["assumptions"]
        assert status["trace_length"] == 1
        assert status["violations"] == 1

    def test_check_output_records_result(self, guard):
        """Test check_output records tool result."""
        guard.check("multiply", {"a": 5, "b": 3})
        guard.check_output("multiply", {"a": 5, "b": 3}, 15)

        trace = guard.get_trace()
        assert trace[0].result == 15


class TestAssumptionExtraction:
    """Tests for assumption extraction from text."""

    @pytest.fixture
    def guard(self):
        """Guard with extraction patterns."""
        return AssumptionTraceGuard(
            config=AssumptionTraceGuardConfig(
                assumption_patterns={
                    "sigma_daily": r"σ_daily\s*[=:]\s*(\d+\.?\d*)",
                    "cv": r"CV\s*[=:]\s*(\d+\.?\d*)",
                },
            )
        )

    def test_extracts_sigma_daily(self, guard):
        """Test extracts σ_daily from text."""
        text = "I'll assume CV=0.3, so σ_daily = 11.1 units/day"

        extracted = guard.extract_assumptions(text)

        # Should extract σ_daily = 11.1
        sigma = guard.get_assumptions().get("sigma_daily")
        assert sigma is not None
        assert sigma.value == 11.1

    def test_extracts_cv(self, guard):
        """Test extracts CV from text."""
        text = "Using a coefficient of variation CV = 0.3"

        guard.extract_assumptions(text)

        cv = guard.get_assumptions().get("cv")
        assert cv is not None
        assert cv.value == 0.3

    def test_extracts_multiple_assumptions(self, guard):
        """Test extracts multiple assumptions."""
        text = "I'll use CV = 0.3 and σ_daily = 11.1"

        guard.extract_assumptions(text)

        assumptions = guard.get_assumptions()
        assert "cv" in assumptions
        assert "sigma_daily" in assumptions


class TestInventorySigmaConstraints:
    """Tests for the pre-built inventory config."""

    def test_inventory_config_catches_mu_sigma_swap(self):
        """Test inventory config catches using μ instead of σ."""
        config = inventory_sigma_constraints()
        guard = AssumptionTraceGuard(config)

        # Simulate the actual failure: model says σ_daily=11.1 but uses μ=37
        guard.register_assumption("sigma_daily", 11.1, "CV=0.3")

        # This is the bug: using 37 (μ) instead of 11.1 (σ)
        result = guard.check("multiply", {"a": 37, "b": 4.24})

        assert result.verdict == GuardVerdict.WARN
        assert "11.1" in result.reason
        assert "37" in result.reason

    def test_inventory_config_allows_correct_computation(self):
        """Test inventory config allows correct σ_LT computation."""
        config = inventory_sigma_constraints()
        guard = AssumptionTraceGuard(config)

        guard.register_assumption("sigma_daily", 11.1, "CV=0.3")

        # Correct: using σ_daily = 11.1
        result = guard.check("multiply", {"a": 11.1, "b": 4.24})

        assert result.verdict == GuardVerdict.ALLOW


class TestContextInference:
    """Tests for computation context inference."""

    @pytest.fixture
    def guard(self):
        """Guard with context triggers."""
        return AssumptionTraceGuard(
            config=AssumptionTraceGuardConfig(
                context_triggers={
                    "sigma_lt": {"sqrt", "lead_time"},
                },
            )
        )

    def test_infers_context_from_tool_name(self, guard):
        """Test infers context from tool name."""
        context = guard.infer_context("sqrt", {"x": 18})
        assert context == "sigma_lt"

    def test_no_context_for_unrelated_tool(self, guard):
        """Test no context for unrelated tools."""
        context = guard.infer_context("add", {"a": 1, "b": 2})
        assert context is None

    def test_explicit_context_overrides(self, guard):
        """Test explicit context setting overrides inference."""
        guard.set_context("explicit_context")

        # Even though sqrt would infer sigma_lt, explicit context wins
        guard.check("sqrt", {"x": 18})

        status = guard.get_status()
        assert status["current_context"] == "explicit_context"
