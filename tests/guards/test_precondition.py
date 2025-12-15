# tests/guards/test_precondition.py
"""Tests for PreconditionGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.precondition import PreconditionGuard, PreconditionGuardConfig

# Test tool sets - explicitly configured, no hardcoding in the guard
PARAMETERIZED_TOOLS = {"normal_cdf", "normal_sf", "t_cdf", "chi_cdf"}
SAFE_VALUES = {0.0, 1.0}


class TestPreconditionGuard:
    """Tests for PreconditionGuard."""

    @pytest.fixture
    def guard_no_bindings(self):
        """Guard with no bindings available."""
        return PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                safe_values=SAFE_VALUES,
            ),
            get_binding_count=lambda: 0,
            get_binding_values=lambda: set(),
            get_user_literals=lambda: set(),
        )

    @pytest.fixture
    def guard_with_bindings(self):
        """Guard with bindings available (strict mode - values must match)."""
        return PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                safe_values=SAFE_VALUES,
            ),
            get_binding_count=lambda: 2,
            get_binding_values=lambda: {1.5, 2.0, 666.0},
            get_user_literals=lambda: {37.0, 18.0, 900.0},
        )

    @pytest.fixture
    def guard_lenient_mode(self):
        """Guard in lenient mode (original behavior - any binding allows)."""
        return PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                lenient_mode=True,
            ),
            get_binding_count=lambda: 2,
        )

    def test_blocks_parameterized_without_values(self, guard_no_bindings):
        """Test blocks parameterized tools when no values exist."""
        result = guard_no_bindings.check("normal_cdf", {"x": 1.5})
        assert result.blocked is True
        assert "computed" in result.reason.lower() or "value" in result.reason.lower()

    def test_allows_parameterized_with_grounded_values(self, guard_with_bindings):
        """Test allows parameterized tools when x value is grounded."""
        # x=1.5 is in the binding values, so should be allowed
        result = guard_with_bindings.check("normal_cdf", {"x": 1.5})
        assert result.verdict == GuardVerdict.ALLOW

    def test_blocks_parameterized_with_ungrounded_values(self, guard_with_bindings):
        """Test blocks parameterized tools when x value is NOT grounded."""
        # x=9.99 is NOT in binding values or user literals
        result = guard_with_bindings.check("normal_cdf", {"x": 9.99})
        assert result.blocked is True
        assert "ungrounded" in result.reason.lower()

    def test_lenient_mode_allows_any_binding(self, guard_lenient_mode):
        """Test lenient mode allows if any bindings exist (original behavior)."""
        # In lenient mode, just having bindings is enough
        result = guard_lenient_mode.check("normal_cdf", {"x": 9.99})
        assert result.verdict == GuardVerdict.ALLOW

    def test_allows_non_parameterized_tools(self, guard_no_bindings):
        """Test non-parameterized tools are always allowed."""
        # search_tools not in parameterized_tools set
        result = guard_no_bindings.check("search_tools", {"query": "cdf"})
        assert result.verdict == GuardVerdict.ALLOW

        # Basic math tools (sqrt, multiply, etc.) not in parameterized_tools
        result = guard_no_bindings.check("multiply", {"a": 2, "b": 3})
        assert result.verdict == GuardVerdict.ALLOW

        result = guard_no_bindings.check("sqrt", {"x": 18})
        assert result.verdict == GuardVerdict.ALLOW

    def test_blocks_parameterized_tools_without_values(self, guard_no_bindings):
        """Test parameterized tools are blocked without values."""
        for tool in PARAMETERIZED_TOOLS:
            result = guard_no_bindings.check(tool, {"x": 1.5})
            assert result.blocked is True, f"{tool} should be blocked"

    def test_allows_parameterized_tools_with_grounded_values(self, guard_with_bindings):
        """Test parameterized tools are allowed with grounded values."""
        for tool in ["normal_cdf", "normal_sf", "t_cdf"]:
            # x=1.5 is in binding values
            result = guard_with_bindings.check(tool, {"x": 1.5})
            assert result.verdict == GuardVerdict.ALLOW, f"{tool} should be allowed"

    def test_allows_parameterized_tools_without_numeric_args(self, guard_no_bindings):
        """Test parameterized tools allowed when no numeric args provided."""
        # If there are no numeric args, the guard allows it
        result = guard_no_bindings.check("normal_cdf", {"description": "testing"})
        assert result.verdict == GuardVerdict.ALLOW

    def test_skips_tool_name_arg(self):
        """Test tool_name argument is skipped."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(parameterized_tools=PARAMETERIZED_TOOLS),
            get_binding_count=lambda: 0,
        )
        # tool_name should be ignored even if numeric
        result = guard.check("normal_cdf", {"tool_name": 123})
        # Should allow because no numeric args (tool_name is skipped)
        assert result.verdict == GuardVerdict.ALLOW

    def test_skips_bool_values(self):
        """Test boolean values are skipped."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(parameterized_tools=PARAMETERIZED_TOOLS),
            get_binding_count=lambda: 0,
        )
        # Bool should be skipped even though bool is subclass of int
        result = guard.check("normal_cdf", {"flag": True})
        # Should allow because no numeric args (bool is skipped)
        assert result.verdict == GuardVerdict.ALLOW

    def test_handles_dotted_tool_names(self):
        """Test tools with dots in name are handled correctly."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(parameterized_tools=PARAMETERIZED_TOOLS),
            get_binding_count=lambda: 0,
        )
        # normal_cdf should be blocked regardless of prefix
        result = guard.check("stats.normal_cdf", {"x": 1.5})
        assert result.blocked is True

    def test_no_binding_callback(self):
        """Test behavior when no binding callback provided."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(parameterized_tools=PARAMETERIZED_TOOLS),
            get_binding_count=None,
        )
        # Should block parameterized tools with numeric args when no callback
        result = guard.check("normal_cdf", {"x": 1.5})
        assert result.blocked is True

    def test_safe_values_allowed(self):
        """Test that configured safe values are allowed."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                safe_values=SAFE_VALUES,
            ),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: {2.5},  # Only x value is grounded
            get_user_literals=lambda: set(),
        )
        # mean=0, std=1 are safe values, so allowed
        result = guard.check("normal_cdf", {"x": 2.5, "mean": 0, "std": 1})
        assert result.verdict == GuardVerdict.ALLOW

    def test_blocks_ungrounded_values(self):
        """Test that ungrounded values ARE blocked."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                safe_values=SAFE_VALUES,
            ),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: {2.5},  # Only x value is grounded
            get_user_literals=lambda: set(),
        )
        # mean=666 is NOT grounded - should be blocked
        result = guard.check("normal_cdf", {"x": 2.5, "mean": 666})
        assert result.blocked is True
        assert "666" in result.reason

    def test_safe_values_skipped(self):
        """Test that safe values are skipped from checking."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                safe_values=SAFE_VALUES,
            ),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: set(),  # No binding values
            get_user_literals=lambda: set(),
        )
        # x=0 and x=1 should be skipped as safe values
        result = guard.check("normal_cdf", {"x": 0})
        assert result.verdict == GuardVerdict.ALLOW

        result = guard.check("normal_cdf", {"x": 1})
        assert result.verdict == GuardVerdict.ALLOW

    def test_user_literals_allow_values(self):
        """Test that user-provided literals are allowed."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(parameterized_tools=PARAMETERIZED_TOOLS),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: set(),
            get_user_literals=lambda: {37.0, 900.0},  # User said 37 and 900
        )
        # 37 is from user, should be allowed
        result = guard.check("normal_cdf", {"x": 37.0})
        assert result.verdict == GuardVerdict.ALLOW

    def test_float_tolerance(self):
        """Test float comparison tolerance."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools=PARAMETERIZED_TOOLS,
                float_tolerance=1e-6,
            ),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: {2.5},
            get_user_literals=lambda: set(),
        )
        # 2.5 + tiny epsilon should still match
        result = guard.check("normal_cdf", {"x": 2.5 + 1e-10})
        assert result.verdict == GuardVerdict.ALLOW

        # But 2.500001 should NOT match
        result = guard.check("normal_cdf", {"x": 2.500001})
        assert result.blocked is True

    def test_empty_config_allows_all(self):
        """Test that empty config (no parameterized tools) allows everything."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(),  # Empty - no parameterized tools
            get_binding_count=lambda: 0,
        )
        # Should allow any tool since none are marked as parameterized
        result = guard.check("normal_cdf", {"x": 1.5})
        assert result.verdict == GuardVerdict.ALLOW

    def test_custom_parameterized_tools(self):
        """Test custom parameterized tool configuration."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools={"my_special_tool"},
            ),
            get_binding_count=lambda: 0,
        )
        # my_special_tool should be blocked
        result = guard.check("my_special_tool", {"x": 1.5})
        assert result.blocked is True

        # normal_cdf should be allowed (not in custom set)
        result = guard.check("normal_cdf", {"x": 1.5})
        assert result.verdict == GuardVerdict.ALLOW

    def test_custom_safe_values(self):
        """Test custom safe values configuration."""
        guard = PreconditionGuard(
            config=PreconditionGuardConfig(
                parameterized_tools={"my_tool"},
                safe_values={42.0, 100.0},  # Custom safe values
            ),
            get_binding_count=lambda: 1,
            get_binding_values=lambda: set(),
            get_user_literals=lambda: set(),
        )
        # 42 is safe - should allow
        result = guard.check("my_tool", {"x": 42})
        assert result.verdict == GuardVerdict.ALLOW

        # 0 is NOT safe (not in custom set) - should block
        result = guard.check("my_tool", {"x": 0})
        assert result.blocked is True
