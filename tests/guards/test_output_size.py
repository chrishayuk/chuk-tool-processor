# tests/guards/test_output_size.py
"""Tests for OutputSizeGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.output_size import (
    OutputSizeConfig,
    OutputSizeGuard,
    SizeViolationType,
    TruncationMode,
)


class TestOutputSizeGuard:
    """Tests for OutputSizeGuard."""

    @pytest.fixture
    def guard(self) -> OutputSizeGuard:
        """Default guard."""
        return OutputSizeGuard(
            config=OutputSizeConfig(
                max_bytes=1000,
                max_array_length=10,
                max_depth=5,
            )
        )

    def test_pre_execution_always_allows(self, guard: OutputSizeGuard):
        """Test pre-execution check always allows."""
        result = guard.check("tool", {"any": "args"})
        assert result.allowed

    def test_small_output_allowed(self, guard: OutputSizeGuard):
        """Test small output is allowed."""
        result = guard.check_output("tool", {}, {"data": "small"})
        assert result.allowed

    def test_large_bytes_blocked(self):
        """Test large byte output is blocked."""
        guard = OutputSizeGuard(config=OutputSizeConfig(max_bytes=100, truncation_mode=TruncationMode.ERROR))
        large_output = {"data": "x" * 200}
        result = guard.check_output("tool", {}, large_output)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == SizeViolationType.BYTES_EXCEEDED.value for v in violations)

    def test_array_length_exceeded(self, guard: OutputSizeGuard):
        """Test array length limit."""
        result = guard.check_output("tool", {}, {"items": list(range(20))})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == SizeViolationType.ARRAY_LENGTH_EXCEEDED.value for v in violations)

    def test_nested_array_length(self, guard: OutputSizeGuard):
        """Test nested array length is checked."""
        result = guard.check_output("tool", {}, {"data": {"nested": {"items": list(range(20))}}})
        assert result.blocked

    def test_depth_exceeded(self, guard: OutputSizeGuard):
        """Test depth limit."""
        deep_data: dict = {"level": 1}
        current = deep_data
        for i in range(10):
            current["nested"] = {"level": i}
            current = current["nested"]

        result = guard.check_output("tool", {}, deep_data)
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == SizeViolationType.DEPTH_EXCEEDED.value for v in violations)

    def test_token_limit(self):
        """Test token estimation limit."""
        guard = OutputSizeGuard(
            config=OutputSizeConfig(
                max_bytes=100000,
                max_tokens=10,  # Very low for testing
                truncation_mode=TruncationMode.ERROR,
            )
        )
        # 100 chars = ~25 tokens
        result = guard.check_output("tool", {}, {"data": "x" * 100})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == SizeViolationType.TOKENS_EXCEEDED.value for v in violations)

    def test_truncate_mode(self):
        """Test truncation mode returns repair verdict."""
        guard = OutputSizeGuard(config=OutputSizeConfig(max_array_length=5, truncation_mode=TruncationMode.TRUNCATE))
        result = guard.check_output("tool", {}, {"items": list(range(20))})
        assert result.verdict == GuardVerdict.REPAIR
        assert result.fallback_response is not None
        assert "partial" in result.fallback_response

    def test_valid_output_within_limits(self, guard: OutputSizeGuard):
        """Test output within all limits passes."""
        result = guard.check_output("tool", {}, {"items": [1, 2, 3], "nested": {"data": "value"}})
        assert result.allowed


class TestTruncation:
    """Tests for output truncation."""

    def test_array_truncation(self):
        """Test array is properly truncated."""
        guard = OutputSizeGuard(config=OutputSizeConfig(max_array_length=3, truncation_mode=TruncationMode.TRUNCATE))
        result = guard.check_output("tool", {}, {"items": [1, 2, 3, 4, 5]})
        assert result.verdict == GuardVerdict.REPAIR

    def test_string_truncation(self):
        """Test long strings are truncated."""
        guard = OutputSizeGuard(config=OutputSizeConfig(max_bytes=50, truncation_mode=TruncationMode.TRUNCATE))
        result = guard.check_output("tool", {}, {"data": "x" * 20000})
        assert result.verdict == GuardVerdict.REPAIR
