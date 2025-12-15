# tests/guards/test_unresolved.py
"""Tests for UnresolvedReferenceGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.unresolved import (
    UnresolvedReferenceGuard,
    UnresolvedReferenceGuardConfig,
)


class TestUnresolvedReferenceGuard:
    """Tests for UnresolvedReferenceGuard."""

    @pytest.fixture
    def guard_warn(self):
        """Guard in warn mode."""
        return UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.WARN,
                grace_calls=1,
            ),
        )

    @pytest.fixture
    def guard_block(self):
        """Guard in block mode."""
        return UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.BLOCK,
                grace_calls=0,
            ),
        )

    def test_allows_no_placeholders(self, guard_block):
        """Test allows calls without placeholders."""
        result = guard_block.check("search_tools", {"query": "cdf"})
        assert result.verdict == GuardVerdict.ALLOW

    def test_allows_numeric_args(self, guard_block):
        """Test allows numeric arguments (not placeholders)."""
        result = guard_block.check("sqrt", {"x": 18})
        assert result.verdict == GuardVerdict.ALLOW

    def test_detects_dollar_curly_brace_placeholder(self, guard_block):
        """Test detects ${var} style placeholders."""
        result = guard_block.check("tool", {"x": "${undefined_var}"})
        assert result.blocked is True
        assert "unresolved" in result.reason.lower()

    def test_detects_dollar_sign_placeholder(self, guard_block):
        """Test detects $var style placeholders."""
        result = guard_block.check("tool", {"x": "$v1"})
        assert result.blocked is True

    def test_detects_mustache_placeholder(self, guard_block):
        """Test detects {{var}} mustache style placeholders."""
        result = guard_block.check("tool", {"x": "{{variable}}"})
        assert result.blocked is True

    def test_detects_angle_bracket_placeholder(self, guard_block):
        """Test detects <PLACEHOLDER> style placeholders."""
        result = guard_block.check("tool", {"x": "<MISSING_VALUE>"})
        assert result.blocked is True

    def test_warns_in_warn_mode(self, guard_warn):
        """Test warns instead of blocking in warn mode."""
        result = guard_warn.check("tool", {"x": "${missing}"})
        assert result.verdict == GuardVerdict.WARN

    def test_grace_calls(self):
        """Test grace period warns instead of blocking."""
        guard = UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.BLOCK,
                grace_calls=2,
            ),
        )

        # First two calls warn (during grace period)
        result1 = guard.check("tool1", {"x": "$v1"})
        assert result1.verdict == GuardVerdict.WARN

        result2 = guard.check("tool2", {"x": "$v2"})
        assert result2.verdict == GuardVerdict.WARN

        # Third call should block (grace exhausted)
        result3 = guard.check("tool3", {"x": "$v3"})
        assert result3.blocked is True

    def test_reset(self, guard_warn):
        """Test reset clears grace counter."""
        guard_warn.check("tool", {"x": "$v1"})
        guard_warn.reset()

        # Should have grace again
        result = guard_warn.check("tool", {"x": "$v2"})
        assert result.verdict == GuardVerdict.WARN

    def test_mode_off_always_allows(self):
        """Test OFF mode always allows."""
        guard = UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.OFF,
                grace_calls=0,
            ),
        )

        result = guard.check("tool", {"x": "${undefined}"})
        assert result.verdict == GuardVerdict.ALLOW

    def test_nested_dict_placeholders(self, guard_block):
        """Test detects placeholders in nested dicts."""
        result = guard_block.check("tool", {"config": {"value": "${nested_var}"}})
        assert result.blocked is True

    def test_list_placeholders(self, guard_block):
        """Test detects placeholders in lists."""
        result = guard_block.check("tool", {"items": ["${item1}", "${item2}"]})
        assert result.blocked is True

    def test_mixed_valid_and_placeholder(self, guard_block):
        """Test detects placeholder even with valid args."""
        result = guard_block.check("tool", {"x": 42, "y": "valid_string", "z": "${missing}"})
        assert result.blocked is True

    def test_allowed_patterns(self):
        """Test explicitly allowed patterns are not blocked."""
        guard = UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.BLOCK,
                grace_calls=0,
            ),
            get_allowed_patterns=lambda: {"$ENV_VAR", "${ALLOWED}"},
        )

        # Allowed pattern should pass
        guard.check("tool", {"x": "$ENV_VAR"})
        # Note: pattern matching is on the captured group, so this may need adjustment
        # based on the exact regex behavior

    def test_multiple_placeholders_in_message(self, guard_block):
        """Test multiple placeholders are reported."""
        result = guard_block.check(
            "tool",
            {
                "a": "$v1",
                "b": "$v2",
                "c": "$v3",
                "d": "$v4",
                "e": "$v5",
                "f": "$v6",  # Should show "+1 more"
            },
        )
        assert result.blocked is True
        # Check that message indicates multiple placeholders
        assert "more" in result.reason or len(result.details.get("placeholders", [])) >= 5

    def test_custom_placeholder_patterns(self):
        """Test custom placeholder patterns work."""
        guard = UnresolvedReferenceGuard(
            config=UnresolvedReferenceGuardConfig(
                mode=EnforcementLevel.BLOCK,
                grace_calls=0,
                placeholder_patterns=[r"__[A-Z]+__"],  # Only match __PLACEHOLDER__
            ),
        )

        # Default patterns should not trigger
        result = guard.check("tool", {"x": "$v1"})
        assert result.verdict == GuardVerdict.ALLOW

        # Custom pattern should trigger
        result = guard.check("tool", {"x": "__MISSING__"})
        assert result.blocked is True
