# tests/guards/test_retry_safety.py
"""Tests for RetrySafetyGuard."""

import time

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.retry_safety import (
    ErrorClass,
    RetrySafetyConfig,
    RetrySafetyGuard,
)


class TestRetrySafetyGuard:
    """Tests for RetrySafetyGuard."""

    @pytest.fixture
    def guard(self) -> RetrySafetyGuard:
        """Default guard."""
        return RetrySafetyGuard(
            config=RetrySafetyConfig(
                max_same_signature_retries=3,
                enforce_backoff=False,  # Disable for easier testing
            )
        )

    def test_first_attempt_allowed(self, guard: RetrySafetyGuard):
        """Test first attempt is always allowed."""
        result = guard.check("tool", {"arg": "value"})
        assert result.allowed

    def test_retry_count_tracked(self, guard: RetrySafetyGuard):
        """Test retry count is tracked."""
        args = {"arg": "value"}

        guard.record_attempt("tool", args)
        assert guard.get_retry_count("tool", args) == 1

        guard.record_attempt("tool", args)
        assert guard.get_retry_count("tool", args) == 2

    def test_max_retries_blocks(self, guard: RetrySafetyGuard):
        """Test max retries blocks further attempts."""
        args = {"arg": "value"}

        for _ in range(3):
            guard.record_attempt("tool", args)

        result = guard.check("tool", args)
        assert result.blocked
        assert "maximum retries" in result.reason.lower()

    def test_different_args_separate_counts(self, guard: RetrySafetyGuard):
        """Test different arguments have separate counts."""
        guard.record_attempt("tool", {"arg": "value1"})
        guard.record_attempt("tool", {"arg": "value1"})
        guard.record_attempt("tool", {"arg": "value1"})

        # Different args should be allowed
        result = guard.check("tool", {"arg": "value2"})
        assert result.allowed

    def test_non_retryable_error_blocks(self, guard: RetrySafetyGuard):
        """Test non-retryable errors block retries."""
        args = {"arg": "value"}
        guard.record_attempt("tool", args, error_class=ErrorClass.VALIDATION)

        result = guard.check_retry_after_error("tool", args, ErrorClass.VALIDATION)
        assert result.blocked
        assert "non-retryable" in result.reason.lower()

    def test_retryable_error_allowed(self, guard: RetrySafetyGuard):
        """Test retryable errors allow retries."""
        args = {"arg": "value"}
        guard.record_attempt("tool", args, error_class=ErrorClass.TIMEOUT)

        result = guard.check_retry_after_error("tool", args, ErrorClass.TIMEOUT)
        assert result.allowed

    def test_success_clears_state(self, guard: RetrySafetyGuard):
        """Test successful execution clears retry state."""
        args = {"arg": "value"}
        guard.record_attempt("tool", args)
        guard.record_attempt("tool", args)

        guard.record_success("tool", args)

        assert guard.get_retry_count("tool", args) == 0
        result = guard.check("tool", args)
        assert result.allowed

    def test_backoff_enforcement(self):
        """Test backoff enforcement."""
        guard = RetrySafetyGuard(
            config=RetrySafetyConfig(
                max_same_signature_retries=10,
                enforce_backoff=True,
                min_backoff_ms=100,
            )
        )
        args = {"arg": "value"}

        guard.record_attempt("tool", args)
        guard.record_attempt("tool", args)

        # Immediate retry should warn about backoff
        result = guard.check("tool", args)
        assert result.verdict == GuardVerdict.WARN
        assert "backoff" in result.reason.lower()

    def test_backoff_after_delay(self):
        """Test backoff is satisfied after delay."""
        guard = RetrySafetyGuard(
            config=RetrySafetyConfig(
                max_same_signature_retries=10,
                enforce_backoff=True,
                min_backoff_ms=10,  # 10ms for testing
            )
        )
        args = {"arg": "value"}

        guard.record_attempt("tool", args)
        guard.record_attempt("tool", args)

        time.sleep(0.02)  # Wait 20ms

        result = guard.check("tool", args)
        assert result.allowed

    def test_idempotency_key_required(self):
        """Test idempotency key requirement."""
        guard = RetrySafetyGuard(
            config=RetrySafetyConfig(
                require_idempotency_key=True,
                non_idempotent_tools={"create_order"},
            )
        )

        # Non-idempotent tool without key should be blocked on retry
        guard.record_attempt("create_order", {"item": "product"})
        result = guard.check("create_order", {"item": "product"})
        assert result.blocked
        assert "idempotency key" in result.reason.lower()

        # With key should work
        result = guard.check("create_order", {"item": "product", "_idempotency_key": "key123"})
        assert result.allowed

    def test_idempotent_tool_skip_key(self):
        """Test idempotent tools skip key requirement."""
        guard = RetrySafetyGuard(
            config=RetrySafetyConfig(
                require_idempotency_key=True,
                idempotent_tools={"get_user"},
            )
        )

        guard.record_attempt("get_user", {"id": 123})
        result = guard.check("get_user", {"id": 123})
        assert result.allowed

    def test_get_required_backoff(self, guard: RetrySafetyGuard):
        """Test getting required backoff time."""
        args = {"arg": "value"}

        # First attempt - no backoff
        assert guard.get_required_backoff_ms("tool", args) == 0

        guard.record_attempt("tool", args)
        # After first attempt - still no backoff
        assert guard.get_required_backoff_ms("tool", args) == 0

        guard.record_attempt("tool", args)
        # After second attempt - should have backoff
        backoff = guard.get_required_backoff_ms("tool", args)
        assert backoff > 0

    def test_reset(self, guard: RetrySafetyGuard):
        """Test reset clears all state."""
        guard.record_attempt("tool", {"arg": "value"})
        guard.record_attempt("tool2", {"arg": "value2"})

        guard.reset()

        assert guard.get_retry_count("tool", {"arg": "value"}) == 0
        assert guard.get_retry_count("tool2", {"arg": "value2"}) == 0

    def test_reset_tool(self, guard: RetrySafetyGuard):
        """Test resetting specific tool."""
        guard.record_attempt("tool", {"arg": "value"})
        guard.record_attempt("tool2", {"arg": "value2"})

        guard.reset_tool("tool", {"arg": "value"})

        assert guard.get_retry_count("tool", {"arg": "value"}) == 0
        assert guard.get_retry_count("tool2", {"arg": "value2"}) == 1

    def test_warn_enforcement_level(self):
        """Test warn enforcement level."""
        guard = RetrySafetyGuard(
            config=RetrySafetyConfig(
                max_same_signature_retries=2,
                enforcement_level=EnforcementLevel.WARN,
            )
        )
        args = {"arg": "value"}

        guard.record_attempt("tool", args)
        guard.record_attempt("tool", args)

        result = guard.check("tool", args)
        assert result.verdict == GuardVerdict.WARN
