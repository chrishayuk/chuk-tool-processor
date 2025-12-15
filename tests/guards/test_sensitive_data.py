# tests/guards/test_sensitive_data.py
"""Tests for SensitiveDataGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.sensitive_data import (
    RedactMode,
    SensitiveDataConfig,
    SensitiveDataGuard,
    SensitiveDataType,
)


class TestSensitiveDataGuard:
    """Tests for SensitiveDataGuard."""

    @pytest.fixture
    def guard(self) -> SensitiveDataGuard:
        """Default guard."""
        return SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK, redact_mode=RedactMode.BLOCK))

    def test_clean_args_allowed(self, guard: SensitiveDataGuard):
        """Test clean arguments are allowed."""
        result = guard.check("tool", {"name": "Alice", "count": 5})
        assert result.allowed

    def test_api_key_detected(self, guard: SensitiveDataGuard):
        """Test API key is detected."""
        result = guard.check("tool", {"config": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.blocked
        matches = result.details.get("matches", [])
        assert any(m.get("data_type") == SensitiveDataType.API_KEY.value for m in matches)

    def test_bearer_token_detected(self, guard: SensitiveDataGuard):
        """Test bearer token is detected."""
        result = guard.check("tool", {"auth": "Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"})
        assert result.blocked

    def test_aws_key_detected(self, guard: SensitiveDataGuard):
        """Test AWS key is detected."""
        result = guard.check("tool", {"key": "AKIAIOSFODNN7EXAMPLE"})
        assert result.blocked
        matches = result.details.get("matches", [])
        assert any(m.get("data_type") == SensitiveDataType.AWS_KEY.value for m in matches)

    def test_private_key_detected(self, guard: SensitiveDataGuard):
        """Test private key is detected."""
        result = guard.check(
            "tool", {"cert": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"}
        )
        assert result.blocked

    def test_password_in_url_detected(self, guard: SensitiveDataGuard):
        """Test password in URL is detected."""
        result = guard.check("tool", {"url": "postgres://user:secret123@localhost/db"})
        assert result.blocked

    def test_jwt_detected(self, guard: SensitiveDataGuard):
        """Test JWT is detected."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = guard.check("tool", {"token": jwt})
        assert result.blocked

    def test_nested_sensitive_data(self, guard: SensitiveDataGuard):
        """Test sensitive data in nested structures."""
        # Use api_key=value format which matches the API_KEY pattern
        result = guard.check("tool", {"config": {"secrets": {"key": "api_key=sk_test_abcdefghijklmnopqrstuvwxyz"}}})
        assert result.blocked

    def test_list_sensitive_data(self, guard: SensitiveDataGuard):
        """Test sensitive data in lists."""
        # Use api_key=value format which matches the API_KEY pattern
        result = guard.check("tool", {"keys": ["api_key=sk_test_abcdefghijklmnopqrstuvwxyz"]})
        assert result.blocked

    def test_allowlist(self):
        """Test allowlist prevents blocking."""
        guard = SensitiveDataGuard(
            config=SensitiveDataConfig(
                mode=EnforcementLevel.BLOCK,
                allowlist={"test_key_12345678901234567890"},
            )
        )
        result = guard.check("tool", {"key": "api_key=test_key_12345678901234567890"})
        assert result.allowed

    def test_output_check(self, guard: SensitiveDataGuard):
        """Test output checking."""
        result = guard.check_output("tool", {}, {"response": "api_key=secret_abcdefghijklmnopqrstuvwxyz"})
        assert result.blocked

    def test_redact_mode(self):
        """Test redact mode repairs instead of blocks."""
        guard = SensitiveDataGuard(
            config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK, redact_mode=RedactMode.REDACT)
        )
        result = guard.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.verdict == GuardVerdict.REPAIR

    def test_hash_mode(self):
        """Test hash mode produces hash in redaction."""
        guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK, redact_mode=RedactMode.HASH))
        result = guard.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.verdict == GuardVerdict.REPAIR

    def test_warn_mode(self):
        """Test warn mode."""
        guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.WARN))
        result = guard.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.verdict == GuardVerdict.WARN

    def test_off_mode(self):
        """Test off mode allows everything."""
        guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.OFF))
        result = guard.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.allowed

    def test_check_args_disabled(self):
        """Test disabling args checking."""
        guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK, check_args=False))
        result = guard.check("tool", {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.allowed

    def test_check_output_disabled(self):
        """Test disabling output checking."""
        guard = SensitiveDataGuard(config=SensitiveDataConfig(mode=EnforcementLevel.BLOCK, check_output=False))
        result = guard.check_output("tool", {}, {"key": "api_key=sk_fake_abcdefghijklmnopqrstuvwxyz"})
        assert result.allowed
