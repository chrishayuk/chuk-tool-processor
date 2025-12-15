# tests/guards/test_network_policy.py
"""Tests for NetworkPolicyGuard."""

import pytest

from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.network_policy import (
    NetworkPolicyConfig,
    NetworkPolicyGuard,
    NetworkViolationType,
)


class TestNetworkPolicyGuard:
    """Tests for NetworkPolicyGuard."""

    @pytest.fixture
    def guard(self) -> NetworkPolicyGuard:
        """Default guard with all protections enabled."""
        return NetworkPolicyGuard(
            config=NetworkPolicyConfig(
                mode=EnforcementLevel.BLOCK,
                block_private_ips=True,
                block_metadata_ips=True,
            )
        )

    def test_public_url_allowed(self, guard: NetworkPolicyGuard):
        """Test public URLs are allowed."""
        result = guard.check("tool", {"url": "https://api.example.com/v1"})
        assert result.allowed

    def test_localhost_blocked(self, guard: NetworkPolicyGuard):
        """Test localhost is blocked."""
        result = guard.check("tool", {"url": "http://localhost:8080/api"})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == NetworkViolationType.LOCALHOST.value for v in violations)

    def test_127_ip_blocked(self, guard: NetworkPolicyGuard):
        """Test 127.x.x.x is blocked."""
        result = guard.check("tool", {"url": "http://127.0.0.1:8080"})
        assert result.blocked

    def test_private_ip_blocked(self, guard: NetworkPolicyGuard):
        """Test private IPs are blocked."""
        for ip in ["192.168.1.1", "10.0.0.1", "172.16.0.1"]:
            result = guard.check("tool", {"url": f"http://{ip}/api"})
            assert result.blocked, f"Should block {ip}"
            violations = result.details.get("violations", [])
            assert any(v.get("violation_type") == NetworkViolationType.PRIVATE_IP.value for v in violations)

    def test_metadata_ip_blocked(self, guard: NetworkPolicyGuard):
        """Test cloud metadata IPs are blocked."""
        result = guard.check("tool", {"url": "http://169.254.169.254/latest/meta-data"})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == NetworkViolationType.METADATA_IP.value for v in violations)

    def test_https_required(self):
        """Test HTTPS requirement."""
        guard = NetworkPolicyGuard(config=NetworkPolicyConfig(mode=EnforcementLevel.BLOCK, require_https=True))
        result = guard.check("tool", {"url": "http://api.example.com"})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == NetworkViolationType.HTTPS_REQUIRED.value for v in violations)

        # HTTPS should work
        result = guard.check("tool", {"url": "https://api.example.com"})
        assert result.allowed

    def test_domain_whitelist(self):
        """Test domain whitelist."""
        guard = NetworkPolicyGuard(
            config=NetworkPolicyConfig(
                mode=EnforcementLevel.BLOCK,
                allowed_domains={"api.allowed.com", "trusted.org"},
            )
        )

        result = guard.check("tool", {"url": "https://api.allowed.com/v1"})
        assert result.allowed

        result = guard.check("tool", {"url": "https://subdomain.api.allowed.com/v1"})
        assert result.allowed

        result = guard.check("tool", {"url": "https://other.com/api"})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == NetworkViolationType.DOMAIN_NOT_ALLOWED.value for v in violations)

    def test_domain_blacklist(self):
        """Test domain blacklist."""
        guard = NetworkPolicyGuard(
            config=NetworkPolicyConfig(mode=EnforcementLevel.BLOCK, blocked_domains={"evil.com", "malware.org"})
        )

        result = guard.check("tool", {"url": "https://evil.com/api"})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == NetworkViolationType.DOMAIN_BLOCKED.value for v in violations)

        result = guard.check("tool", {"url": "https://good.com/api"})
        assert result.allowed

    def test_subdomain_blocking(self):
        """Test subdomain blocking matches parent domain."""
        guard = NetworkPolicyGuard(
            config=NetworkPolicyConfig(mode=EnforcementLevel.BLOCK, blocked_domains={"evil.com"})
        )

        result = guard.check("tool", {"url": "https://sub.evil.com/api"})
        assert result.blocked

    def test_nested_url_detection(self, guard: NetworkPolicyGuard):
        """Test URLs in nested structures are found."""
        result = guard.check("tool", {"config": {"endpoints": {"primary": "http://localhost:8080"}}})
        assert result.blocked

    def test_multiple_url_args(self, guard: NetworkPolicyGuard):
        """Test multiple URL arguments are all checked."""
        result = guard.check(
            "tool",
            {
                "url": "https://api.example.com",
                "endpoint": "http://localhost:9090",
            },
        )
        assert result.blocked

    def test_warn_mode(self):
        """Test warn mode."""
        guard = NetworkPolicyGuard(config=NetworkPolicyConfig(mode=EnforcementLevel.WARN))
        result = guard.check("tool", {"url": "http://localhost:8080"})
        assert result.verdict.value == "warn"

    def test_off_mode(self):
        """Test off mode allows everything."""
        guard = NetworkPolicyGuard(config=NetworkPolicyConfig(mode=EnforcementLevel.OFF))
        result = guard.check("tool", {"url": "http://localhost:8080"})
        assert result.allowed

    def test_check_url_method(self, guard: NetworkPolicyGuard):
        """Test direct URL checking method."""
        violation = guard.check_url("http://localhost:8080")
        assert violation is not None
        assert violation.violation_type == NetworkViolationType.LOCALHOST

        violation = guard.check_url("https://api.example.com")
        assert violation is None

    def test_private_ip_disabled(self):
        """Test disabling private IP blocking."""
        guard = NetworkPolicyGuard(config=NetworkPolicyConfig(mode=EnforcementLevel.BLOCK, block_private_ips=False))
        result = guard.check("tool", {"url": "http://192.168.1.1/api"})
        # Localhost is still blocked
        result = guard.check("tool", {"url": "http://10.0.0.1/api"})
        assert result.allowed
