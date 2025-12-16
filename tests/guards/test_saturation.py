# tests/guards/test_saturation.py
"""Tests for SaturationGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.saturation import SaturationGuard, SaturationGuardConfig

# Test configuration
CDF_TOOLS = {"normal_cdf", "t_cdf", "chi_cdf"}


class TestSaturationGuard:
    """Tests for SaturationGuard."""

    @pytest.fixture
    def guard(self):
        """Guard configured for CDF tools."""
        return SaturationGuard(
            config=SaturationGuardConfig(
                cdf_tools=CDF_TOOLS,
                z_threshold=8.0,
                degenerate_values={0.0, 1.0},
            )
        )

    @pytest.fixture
    def blocking_guard(self):
        """Guard that blocks on extreme inputs."""
        return SaturationGuard(
            config=SaturationGuardConfig(
                cdf_tools=CDF_TOOLS,
                z_threshold=8.0,
                block_on_extreme=True,
                degenerate_values={0.0, 1.0},
            )
        )

    def test_allows_normal_z_score(self, guard):
        """Test allows reasonable Z-scores."""
        result = guard.check("normal_cdf", {"x": 1.96, "mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.ALLOW

    def test_warns_extreme_z_score(self, guard):
        """Test warns on extreme Z-scores."""
        # Z = 55 is way beyond threshold
        result = guard.check("normal_cdf", {"x": 55, "mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.WARN
        assert "SATURATION_WARNING" in result.reason

    def test_blocks_extreme_when_configured(self, blocking_guard):
        """Test blocks on extreme Z-scores when configured."""
        result = blocking_guard.check("normal_cdf", {"x": 55, "mean": 0, "std": 1})
        assert result.blocked is True

    def test_allows_non_cdf_tools(self, guard):
        """Test allows non-CDF tools regardless of args."""
        result = guard.check("multiply", {"a": 1000, "b": 1000})
        assert result.verdict == GuardVerdict.ALLOW

    def test_computes_z_from_mean_std(self, guard):
        """Test correctly computes Z with non-standard mean/std."""
        # x=100, mean=50, std=5 -> Z = 10 > threshold
        result = guard.check("normal_cdf", {"x": 100, "mean": 50, "std": 5})
        assert result.verdict == GuardVerdict.WARN

    def test_handles_missing_x(self, guard):
        """Test handles missing x argument gracefully."""
        result = guard.check("normal_cdf", {"mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.ALLOW

    def test_handles_non_numeric_x(self, guard):
        """Test handles non-numeric x gracefully."""
        result = guard.check("normal_cdf", {"x": "not a number"})
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_allows_normal_values(self, guard):
        """Test output check allows non-degenerate values."""
        result = guard.check_output("normal_cdf", {}, 0.975)
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_tracks_degenerate(self, guard):
        """Test output check tracks consecutive degenerate outputs."""
        # First two degenerate outputs - should allow
        guard.check_output("normal_cdf", {}, 1.0)
        guard.check_output("normal_cdf", {}, 1.0)

        # Third should warn
        result = guard.check_output("normal_cdf", {}, 1.0)
        assert result.verdict == GuardVerdict.WARN
        assert "DEGENERATE_OUTPUT" in result.reason

    def test_output_check_resets_on_non_degenerate(self, guard):
        """Test output check resets counter on non-degenerate value."""
        guard.check_output("normal_cdf", {}, 1.0)
        guard.check_output("normal_cdf", {}, 1.0)

        # Non-degenerate resets counter
        guard.check_output("normal_cdf", {}, 0.5)

        # Next degenerate starts fresh
        result = guard.check_output("normal_cdf", {}, 1.0)
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_ignores_non_cdf(self, guard):
        """Test output check ignores non-CDF tools."""
        result = guard.check_output("multiply", {}, 1.0)
        assert result.verdict == GuardVerdict.ALLOW

    def test_reset(self, guard):
        """Test reset clears state."""
        guard.check_output("normal_cdf", {}, 1.0)
        guard.check_output("normal_cdf", {}, 1.0)

        guard.reset()

        # After reset, counter starts fresh
        result = guard.check_output("normal_cdf", {}, 1.0)
        assert result.verdict == GuardVerdict.ALLOW

    def test_get_status(self, guard):
        """Test get_status returns state."""
        guard.check_output("normal_cdf", {}, 1.0)
        guard.check_output("normal_cdf", {}, 1.0)

        status = guard.get_status()
        assert status["consecutive_degenerate"] == 2
        assert 1.0 in status["recent_results"]

    def test_extracts_numeric_from_dict(self, guard):
        """Test extracts numeric from dict result."""
        guard.check_output("normal_cdf", {}, {"result": 1.0})
        # Should track the 1.0
        assert guard._consecutive_degenerate == 1

    def test_z_threshold_boundary(self, guard):
        """Test exactly at threshold."""
        # Z = 8.0 exactly
        result = guard.check("normal_cdf", {"x": 8.0, "mean": 0, "std": 1})
        # At threshold, still allowed (> not >=)
        assert result.verdict == GuardVerdict.ALLOW

        # Z = 8.01 just over
        result = guard.check("normal_cdf", {"x": 8.01, "mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.WARN

    def test_empty_config_allows_all(self):
        """Test empty config (no CDF tools) allows everything."""
        guard = SaturationGuard(config=SaturationGuardConfig())

        result = guard.check("normal_cdf", {"x": 100})
        assert result.verdict == GuardVerdict.ALLOW

    def test_handles_zero_std(self, guard):
        """Test handles zero std gracefully (infinite Z)."""
        result = guard.check("normal_cdf", {"x": 1, "mean": 0, "std": 0})
        assert result.verdict == GuardVerdict.WARN

    def test_dotted_tool_names(self, guard):
        """Test handles namespaced tool names."""
        result = guard.check("stats.normal_cdf", {"x": 55, "mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.WARN

    def test_output_check_string_result(self, guard):
        """Test output check handles string numeric results."""
        result = guard.check_output("normal_cdf", {}, "0.975")
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_string_non_numeric(self, guard):
        """Test output check handles non-numeric strings gracefully."""
        result = guard.check_output("normal_cdf", {}, "not a number")
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_none_result(self, guard):
        """Test output check handles None result."""
        result = guard.check_output("normal_cdf", {}, None)
        assert result.verdict == GuardVerdict.ALLOW

    def test_output_check_list_result(self, guard):
        """Test output check handles list result (returns None from extract)."""
        result = guard.check_output("normal_cdf", {}, [1.0, 2.0, 3.0])
        assert result.verdict == GuardVerdict.ALLOW

    def test_extracts_numeric_from_dict_value_key(self, guard):
        """Test extracts numeric from dict with 'value' key."""
        guard.check_output("normal_cdf", {}, {"value": 1.0})
        assert guard._consecutive_degenerate == 1

    def test_extracts_numeric_from_dict_output_key(self, guard):
        """Test extracts numeric from dict with 'output' key."""
        guard.check_output("normal_cdf", {}, {"output": 1.0})
        assert guard._consecutive_degenerate == 1

    def test_extracts_numeric_from_nested_dict(self, guard):
        """Test extracts numeric from nested dict."""
        guard.check_output("normal_cdf", {}, {"result": {"value": 1.0}})
        assert guard._consecutive_degenerate == 1

    def test_extracts_numeric_from_int(self, guard):
        """Test extracts numeric from int value."""
        guard.check_output("normal_cdf", {}, 1)
        assert guard._consecutive_degenerate == 1

    def test_output_check_dotted_tool_names(self, guard):
        """Test output check handles namespaced tool names."""
        # First two degenerate outputs from namespaced tool
        guard.check_output("stats.normal_cdf", {}, 1.0)
        guard.check_output("stats.normal_cdf", {}, 1.0)

        # Third should warn
        result = guard.check_output("stats.normal_cdf", {}, 1.0)
        assert result.verdict == GuardVerdict.WARN
        assert "DEGENERATE_OUTPUT" in result.reason

    def test_output_check_degenerate_zero(self, guard):
        """Test output check detects 0.0 as degenerate."""
        guard.check_output("normal_cdf", {}, 0.0)
        guard.check_output("normal_cdf", {}, 0.0)
        result = guard.check_output("normal_cdf", {}, 0.0)
        assert result.verdict == GuardVerdict.WARN

    def test_default_config(self):
        """Test default config initialization."""
        guard = SaturationGuard()
        assert guard.config.cdf_tools == set()
        assert guard.config.z_threshold == 8.0
        assert guard.config.block_on_extreme is False
        assert guard.config.degenerate_values == set()
