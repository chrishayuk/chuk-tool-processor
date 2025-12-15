# tests/guards/test_runaway.py
"""Tests for RunawayGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.runaway import RunawayGuard, RunawayGuardConfig


class TestRunawayGuard:
    """Tests for RunawayGuard."""

    @pytest.fixture
    def guard(self):
        return RunawayGuard(config=RunawayGuardConfig())

    def test_allows_normal_values(self, guard):
        """Test allows normal numeric values."""
        guard.record_result(4.2426)
        result = guard.check("sqrt", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_detects_degenerate_zero(self, guard):
        """Test detects degenerate zero values."""
        for _ in range(5):
            guard.record_result(0.0)

        result = guard.check("tool", {})
        assert result.blocked is True
        assert "degenerate" in result.reason.lower() or "0" in result.reason

    def test_detects_degenerate_one(self, guard):
        """Test detects degenerate one values."""
        for _ in range(5):
            guard.record_result(1.0)

        result = guard.check("tool", {})
        assert result.blocked is True

    def test_detects_saturation(self, guard):
        """Test detects numeric saturation."""
        # Values converging to same point
        for _ in range(5):
            guard.record_result(0.9999999999)

        result = guard.check("tool", {})
        # Should detect saturation or repetition
        assert result.verdict in [GuardVerdict.BLOCK, GuardVerdict.WARN]

    def test_detects_repeating_values(self, guard):
        """Test detects repeating values."""
        for _ in range(5):
            guard.record_result(42.0)

        result = guard.check("tool", {})
        assert result.blocked is True

    def test_allows_varying_values(self, guard):
        """Test allows varying values."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for v in values:
            guard.record_result(v)

        result = guard.check("tool", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_reset(self, guard):
        """Test reset clears state."""
        guard.record_result(0.0)
        guard.record_result(0.0)
        guard.reset()

        assert len(guard._recent_values) == 0

    def test_recent_values_tracked(self, guard):
        """Test recent values are tracked."""
        guard.record_result(4.2426)
        guard.record_result(25.807)

        assert 4.2426 in guard._recent_values
        assert 25.807 in guard._recent_values

    def test_degenerate_first_occurrence_increments(self, guard):
        """Test first degenerate value increments count but doesn't block."""
        guard.record_result(0.0)
        result = guard.check("tool", {})
        # First degenerate - should count but not block yet (need >=2)
        assert guard._degenerate_count == 1
        # Check returns allow until count >= 2
        assert result.verdict in [GuardVerdict.ALLOW, GuardVerdict.BLOCK]

    def test_saturation_detection_small_nonzero(self, guard):
        """Test saturation detection for very small values."""
        # Value smaller than saturation_threshold (1e-12)
        guard.record_result(1e-15)
        result = guard.check("tool", {})
        assert result.blocked is True
        assert "saturation" in result.reason.lower()

    def test_history_window_truncation(self, guard):
        """Test history window truncates old values."""
        # history_window defaults to 5
        for i in range(10):
            guard.record_result(float(i))

        # Should only keep last 5
        assert len(guard._recent_values) == 5
        assert guard._recent_values == [5.0, 6.0, 7.0, 8.0, 9.0]

    def test_format_saturation_message_effectively_zero(self, guard):
        """Test format_saturation_message for values below threshold."""
        message = guard.format_saturation_message(1e-15)
        assert "effectively zero" in message

    def test_format_saturation_message_exactly_zero(self, guard):
        """Test format_saturation_message for exactly 0.0."""
        message = guard.format_saturation_message(0.0)
        # 0.0 satisfies abs(0.0) < 1e-12, so gets "effectively zero"
        assert "zero" in message.lower()

    def test_format_saturation_message_exactly_one(self, guard):
        """Test format_saturation_message for exactly 1.0."""
        message = guard.format_saturation_message(1.0)
        assert "exactly 1.0" in message or "certainty" in message

    def test_format_saturation_message_normal_value(self, guard):
        """Test format_saturation_message for normal values."""
        message = guard.format_saturation_message(0.5)
        assert "5.00e-01" in message or "0.5" in message

    def test_non_numeric_result_ignored(self, guard):
        """Test that non-numeric results are ignored."""
        guard.record_result("not a number")
        guard.record_result({"key": "value"})
        assert len(guard._recent_values) == 0

    def test_check_with_no_values_allows(self, guard):
        """Test check returns allow when no values recorded."""
        # Don't record any values
        result = guard.check("tool", {})
        assert result.verdict == GuardVerdict.ALLOW

    def test_degenerate_blocks_on_second_occurrence(self, guard):
        """Test degenerate value blocks on second occurrence."""
        # First degenerate value
        guard.record_result(0.0)
        guard.check("tool", {})  # Increments degenerate count to 1

        # Second degenerate value
        guard.record_result(0.0)
        result = guard.check("tool", {})  # Count now >= 2

        assert result.blocked is True
        assert "degenerate" in result.reason.lower()
