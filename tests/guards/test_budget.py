# tests/guards/test_budget.py
"""Tests for BudgetGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.budget import BudgetGuard, BudgetGuardConfig


class TestBudgetGuard:
    """Tests for BudgetGuard."""

    @pytest.fixture
    def guard(self):
        config = BudgetGuardConfig(
            discovery_budget=3,
            execution_budget=5,
            total_budget=8,
        )
        return BudgetGuard(config=config)

    def test_allows_under_budget(self, guard):
        """Test allows calls under budget."""
        result = guard.check("sqrt", {"x": 18})
        assert result.verdict == GuardVerdict.ALLOW

    def test_tracks_discovery_calls(self, guard):
        """Test discovery calls are tracked."""
        guard.record_call("search_tools")
        status = guard.get_status()
        assert status["discovery"]["used"] == 1

    def test_tracks_execution_calls(self, guard):
        """Test execution calls are tracked."""
        guard.record_call("sqrt")
        status = guard.get_status()
        assert status["execution"]["used"] == 1

    def test_blocks_when_discovery_exhausted(self, guard):
        """Test blocks when discovery budget exhausted."""
        for _ in range(3):
            guard.record_call("search_tools")

        result = guard.check("list_tools", {})
        assert result.blocked is True

    def test_blocks_when_execution_exhausted(self, guard):
        """Test blocks when execution budget exhausted."""
        for _ in range(5):
            guard.record_call("sqrt")

        result = guard.check("multiply", {})
        assert result.blocked is True

    def test_discovery_exhausted_allows_execution(self, guard):
        """Test discovery exhaustion still allows execution."""
        for _ in range(3):
            guard.record_call("search_tools")

        result = guard.check("sqrt", {})
        # Should warn or allow, not block
        assert result.verdict != GuardVerdict.BLOCK or "execution" not in result.reason.lower()

    def test_reset(self, guard):
        """Test reset clears counts."""
        guard.record_call("sqrt")
        guard.record_call("search_tools")
        guard.reset()

        status = guard.get_status()
        assert status["discovery"]["used"] == 0
        assert status["execution"]["used"] == 0

    def test_register_discovered_tool(self, guard):
        """Test registering discovered tools."""
        guard.register_discovered_tool("normal_cdf")
        assert "normal_cdf" in guard._discovered_tools

    def test_get_status(self, guard):
        """Test get_status returns correct info."""
        guard.record_call("sqrt")
        guard.record_call("search_tools")

        status = guard.get_status()
        assert status["discovery"]["used"] == 1
        assert status["discovery"]["limit"] == 3
        assert status["execution"]["used"] == 1
        assert status["execution"]["limit"] == 5

    def test_blocks_when_total_exhausted(self, guard):
        """Test blocks when total budget exhausted."""
        # Config: total_budget=8
        # Fill up total without hitting individual limits
        for _ in range(4):
            guard.record_call("sqrt")  # execution
        for _ in range(3):
            guard.record_call("search_tools")  # discovery
        # Now total=7, need one more
        guard.record_call("multiply")  # total=8

        # Next call should be blocked by total budget
        result = guard.check("divide", {})
        assert result.blocked is True
        assert "exhausted" in result.reason.lower()

    def test_format_discovery_exhausted_with_tools(self, guard):
        """Test discovery exhausted message with discovered tools."""
        guard.register_discovered_tool("normal_cdf")
        guard.register_discovered_tool("sqrt")

        for _ in range(3):
            guard.record_call("search_tools")

        result = guard.check("list_tools", {})
        assert result.blocked is True
        # Should mention discovered tools
        assert "discovered" in result.reason.lower() or "use" in result.reason.lower()

    def test_format_total_exhausted_message(self, guard):
        """Test total exhausted message."""
        # Fill up total budget
        for _ in range(8):
            guard.record_call("sqrt")

        result = guard.check("multiply", {})
        assert result.blocked is True
        assert "exhausted" in result.reason.lower()

    def test_total_budget_blocks_even_when_individual_budgets_ok(self):
        """Test total budget blocks when it's hit first."""
        # Config with high individual budgets but low total
        config = BudgetGuardConfig(
            discovery_budget=10,
            execution_budget=10,
            total_budget=3,
        )
        guard = BudgetGuard(config=config)

        # Make 3 calls (hits total budget)
        guard.record_call("sqrt")
        guard.record_call("multiply")
        guard.record_call("divide")

        # Next call should be blocked by total budget
        result = guard.check("pow", {})
        assert result.blocked is True
        assert result.details.get("budget_type") == "total"
