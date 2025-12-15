# tests/guards/test_per_tool.py
"""Tests for PerToolGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.per_tool import PerToolGuard, PerToolGuardConfig


class TestPerToolGuard:
    """Tests for PerToolGuard."""

    @pytest.fixture
    def guard(self):
        return PerToolGuard(config=PerToolGuardConfig(default_limit=3))

    def test_allows_exempt_tools_always(self, guard):
        """Test exempt tools (sqrt, multiply, etc.) are always allowed."""
        # Exempt tools can be called unlimited times
        for _ in range(10):
            guard.record_call("sqrt")
        result = guard.check("sqrt", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_allows_under_limit(self, guard):
        """Test allows non-exempt calls under limit."""
        guard.record_call("normal_cdf")
        result = guard.check("normal_cdf", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_blocks_at_limit(self, guard):
        """Test blocks non-exempt tools at limit."""
        # Use a non-exempt tool (not in sqrt, multiply, etc.)
        for _ in range(3):
            guard.record_call("normal_cdf")

        result = guard.check("normal_cdf", {})
        assert result.blocked is True

    def test_tracks_per_tool(self, guard):
        """Test tracks calls per tool."""
        guard.record_call("normal_cdf")
        guard.record_call("t_test")

        # normal_cdf at 1, t_test at 1 (both under limit of 3)
        result_cdf = guard.check("normal_cdf", {})
        result_t = guard.check("t_test", {})

        assert result_cdf.verdict == GuardVerdict.ALLOW
        assert result_t.verdict == GuardVerdict.ALLOW

    def test_reset(self, guard):
        """Test reset clears counts."""
        guard.record_call("normal_cdf")
        guard.record_call("normal_cdf")
        guard.reset()

        result = guard.check("normal_cdf", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_custom_limit(self):
        """Test custom limit per tool."""
        guard = PerToolGuard(config=PerToolGuardConfig(default_limit=5))
        # Record 3 calls (under limit of 5)
        for _ in range(3):
            guard.record_call("normal_cdf")

        result = guard.check("normal_cdf", {})
        assert result.verdict == GuardVerdict.ALLOW

        # 4th call warns (at limit-1), 5th call reaches limit, 6th blocks
        guard.record_call("normal_cdf")
        guard.record_call("normal_cdf")
        result = guard.check("normal_cdf", {})
        assert result.blocked is True

    def test_warns_near_limit(self):
        """Test warns when approaching limit."""
        guard = PerToolGuard(config=PerToolGuardConfig(default_limit=3))
        guard.record_call("normal_cdf")
        guard.record_call("normal_cdf")

        # At count=2, limit=3, warns (count >= limit - 1)
        result = guard.check("normal_cdf", {})
        assert result.verdict == GuardVerdict.WARN

    def test_get_call_count(self):
        """Test get_call_count returns correct count."""
        guard = PerToolGuard(config=PerToolGuardConfig(default_limit=5))
        assert guard.get_call_count("normal_cdf") == 0

        guard.record_call("normal_cdf")
        assert guard.get_call_count("normal_cdf") == 1

        guard.record_call("normal_cdf")
        assert guard.get_call_count("normal_cdf") == 2

    def test_get_status(self):
        """Test get_status returns tool status."""
        guard = PerToolGuard(config=PerToolGuardConfig(default_limit=3))
        guard.record_call("normal_cdf")
        guard.record_call("t_test")
        guard.record_call("t_test")

        status = guard.get_status()
        assert status["normal_cdf"]["count"] == 1
        assert status["normal_cdf"]["limit"] == 3
        assert status["t_test"]["count"] == 2
        assert status["t_test"]["limit"] == 3

    def test_tool_specific_limit(self):
        """Test per-tool limit override."""
        guard = PerToolGuard(
            config=PerToolGuardConfig(
                default_limit=3,
                tool_limits={"special_tool": 1},
            )
        )

        guard.record_call("special_tool")
        result = guard.check("special_tool", {})
        assert result.blocked is True

    def test_handles_dotted_tool_names(self):
        """Test tools with dots in name are handled correctly."""
        guard = PerToolGuard(config=PerToolGuardConfig(default_limit=3))
        # sqrt should be exempt regardless of prefix
        result = guard.check("math.sqrt", {})
        assert result.verdict == GuardVerdict.ALLOW
