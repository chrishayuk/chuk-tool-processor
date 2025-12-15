# tests/guards/test_base.py
"""Tests for base guard classes and GuardResult."""

import pytest

from chuk_tool_processor.guards.base import BaseGuard, GuardResult, GuardVerdict


class TestGuardVerdict:
    """Tests for GuardVerdict enum."""

    def test_all_verdicts_exist(self):
        """Test all verdict values exist."""
        assert GuardVerdict.ALLOW.value == "allow"
        assert GuardVerdict.WARN.value == "warn"
        assert GuardVerdict.BLOCK.value == "block"
        assert GuardVerdict.REPAIR.value == "repair"


class TestGuardResult:
    """Tests for GuardResult model."""

    def test_default_result(self):
        """Test default guard result."""
        result = GuardResult()
        assert result.verdict == GuardVerdict.ALLOW
        assert result.reason == ""
        assert result.allowed is True
        assert result.blocked is False

    def test_allowed_property_with_warn(self):
        """Test allowed property includes WARN."""
        result = GuardResult(verdict=GuardVerdict.WARN, reason="warning")
        assert result.allowed is True
        assert result.blocked is False

    def test_blocked_property(self):
        """Test blocked property."""
        result = GuardResult(verdict=GuardVerdict.BLOCK, reason="blocked")
        assert result.allowed is False
        assert result.blocked is True

    def test_format_message_allow(self):
        """Test format_message returns empty for ALLOW."""
        result = GuardResult(verdict=GuardVerdict.ALLOW)
        message = result.format_message()
        assert message == ""

    def test_format_message_warn(self):
        """Test format_message for WARN."""
        result = GuardResult(verdict=GuardVerdict.WARN, reason="test warning")
        message = result.format_message()
        assert "Warning" in message
        assert "test warning" in message

    def test_format_message_block(self):
        """Test format_message for BLOCK."""
        result = GuardResult(verdict=GuardVerdict.BLOCK, reason="test block")
        message = result.format_message()
        assert "Blocked" in message
        assert "test block" in message

    def test_format_message_repair(self):
        """Test format_message for REPAIR."""
        result = GuardResult(verdict=GuardVerdict.REPAIR, reason="test repair")
        message = result.format_message()
        assert "Repairing" in message
        assert "test repair" in message

    def test_format_message_no_reason(self):
        """Test format_message with empty reason."""
        result = GuardResult(verdict=GuardVerdict.WARN, reason="")
        message = result.format_message()
        assert "Warning" in message


class ConcreteGuard(BaseGuard):
    """Concrete implementation for testing."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.allow()


class TestBaseGuard:
    """Tests for BaseGuard helper methods."""

    @pytest.fixture
    def guard(self):
        return ConcreteGuard()

    def test_allow_helper(self, guard):
        """Test allow helper."""
        result = guard.allow("reason")
        assert result.verdict == GuardVerdict.ALLOW
        assert result.reason == "reason"

    def test_warn_helper(self, guard):
        """Test warn helper."""
        result = guard.warn("warning reason", extra="data")
        assert result.verdict == GuardVerdict.WARN
        assert result.reason == "warning reason"
        assert result.details["extra"] == "data"

    def test_block_helper(self, guard):
        """Test block helper."""
        result = guard.block("block reason", count=5)
        assert result.verdict == GuardVerdict.BLOCK
        assert result.reason == "block reason"
        assert result.details["count"] == 5

    def test_repair_helper(self, guard):
        """Test repair helper."""
        result = guard.repair(
            reason="repair reason",
            repaired_args={"x": "$v1"},
            fallback_response="Use this instead",
        )
        assert result.verdict == GuardVerdict.REPAIR
        assert result.reason == "repair reason"
        assert result.repaired_args == {"x": "$v1"}
        assert result.fallback_response == "Use this instead"

    def test_repair_helper_no_args(self, guard):
        """Test repair helper without optional args."""
        result = guard.repair(reason="repair")
        assert result.verdict == GuardVerdict.REPAIR
        assert result.repaired_args is None
        assert result.fallback_response is None
