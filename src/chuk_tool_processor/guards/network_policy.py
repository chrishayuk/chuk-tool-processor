# chuk_tool_processor/guards/network_policy.py
"""Network policy guard for SSRF defense and network access control.

Enforces allowed domains, blocks private IPs, requires HTTPS.
"""

from __future__ import annotations

import ipaddress
import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class NetworkViolationType(str, Enum):
    """Types of network policy violations."""

    DOMAIN_NOT_ALLOWED = "domain_not_allowed"
    DOMAIN_BLOCKED = "domain_blocked"
    PRIVATE_IP = "private_ip"
    METADATA_IP = "metadata_ip"
    LOCALHOST = "localhost"
    HTTPS_REQUIRED = "https_required"
    INVALID_URL = "invalid_url"
    IP_NOT_ALLOWED = "ip_not_allowed"


class NetworkViolation(BaseModel):
    """A network policy violation."""

    violation_type: NetworkViolationType
    url: str
    detail: str


# Default cloud metadata IP addresses to block
DEFAULT_METADATA_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS, GCP, Azure
        "metadata.google.internal",
        "metadata.gke.internal",
        "100.100.100.200",  # Alibaba Cloud
        "192.0.0.192",  # Oracle Cloud
    }
)

# Default localhost variations to block (patterns, not bind addresses)
DEFAULT_LOCALHOST_PATTERNS: frozenset[str] = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "[::1]",
        "0.0.0.0",  # nosec B104 - Pattern to block, not a bind address
    }
)

# Default URL argument names to scan
DEFAULT_URL_ARGUMENT_NAMES: frozenset[str] = frozenset(
    {
        "url",
        "endpoint",
        "host",
        "target",
        "destination",
        "uri",
        "href",
        "link",
        "address",
        "server",
    }
)


class NetworkPolicyConfig(BaseModel):
    """Configuration for NetworkPolicyGuard."""

    mode: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level",
    )
    allowed_domains: set[str] | None = Field(
        default=None,
        description="Whitelist of allowed domains (None = all allowed)",
    )
    blocked_domains: set[str] = Field(
        default_factory=set,
        description="Blacklist of blocked domains",
    )
    block_private_ips: bool = Field(
        default=True,
        description="Block RFC1918, localhost, link-local IPs",
    )
    block_localhost: bool = Field(
        default=True,
        description="Block localhost addresses",
    )
    block_metadata_ips: bool = Field(
        default=True,
        description="Block cloud metadata IPs (169.254.169.254, etc.)",
    )
    require_https: bool = Field(
        default=False,
        description="Require HTTPS for all URLs",
    )
    url_argument_names: set[str] = Field(
        default_factory=lambda: set(DEFAULT_URL_ARGUMENT_NAMES),
        description="Argument names that may contain URLs",
    )
    metadata_ips: set[str] = Field(
        default_factory=lambda: set(DEFAULT_METADATA_IPS),
        description="Cloud metadata IP addresses to block",
    )
    localhost_patterns: set[str] = Field(
        default_factory=lambda: set(DEFAULT_LOCALHOST_PATTERNS),
        description="Localhost patterns to block",
    )


class NetworkPolicyGuard(BaseGuard):
    """Guard that enforces network access policies.

    Provides SSRF defense by:
    - Whitelisting allowed domains
    - Blacklisting specific domains
    - Blocking private/internal IPs
    - Blocking cloud metadata endpoints
    - Requiring HTTPS

    All patterns (metadata IPs, localhost patterns, URL argument names)
    are configurable via NetworkPolicyConfig.
    """

    def __init__(self, config: NetworkPolicyConfig | None = None) -> None:
        self.config = config or NetworkPolicyConfig()

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check arguments for network policy violations."""
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        violations = self._scan_arguments(arguments)

        if not violations:
            return self.allow()

        messages = [f"{v.violation_type.value}: {v.detail}" for v in violations]
        message = f"Network policy violation: {'; '.join(messages)}"

        if self.config.mode == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                violations=[v.model_dump() for v in violations],
            )

        return self.block(
            reason=message,
            violations=[v.model_dump() for v in violations],
        )

    def check_url(self, url: str) -> NetworkViolation | None:
        """Check a single URL against policy."""
        try:
            parsed = urlparse(url)
        except Exception:
            return NetworkViolation(
                violation_type=NetworkViolationType.INVALID_URL,
                url=url,
                detail=f"Could not parse URL: {url}",
            )

        host = parsed.hostname or ""
        scheme = parsed.scheme.lower()

        # Check HTTPS requirement
        if self.config.require_https and scheme not in ("https", "wss"):
            return NetworkViolation(
                violation_type=NetworkViolationType.HTTPS_REQUIRED,
                url=url,
                detail=f"HTTPS required, got {scheme}",
            )

        # Check localhost
        if self.config.block_localhost and self._is_localhost(host):
            return NetworkViolation(
                violation_type=NetworkViolationType.LOCALHOST,
                url=url,
                detail=f"Localhost access blocked: {host}",
            )

        # Check metadata IPs
        if self.config.block_metadata_ips and self._is_metadata_ip(host):
            return NetworkViolation(
                violation_type=NetworkViolationType.METADATA_IP,
                url=url,
                detail=f"Cloud metadata endpoint blocked: {host}",
            )

        # Check private IPs
        if self.config.block_private_ips and self._is_private_ip(host):
            return NetworkViolation(
                violation_type=NetworkViolationType.PRIVATE_IP,
                url=url,
                detail=f"Private IP blocked: {host}",
            )

        # Check domain blacklist
        if self._is_blocked_domain(host):
            return NetworkViolation(
                violation_type=NetworkViolationType.DOMAIN_BLOCKED,
                url=url,
                detail=f"Domain is blocked: {host}",
            )

        # Check domain whitelist
        if self.config.allowed_domains is not None and not self._is_allowed_domain(host):
            return NetworkViolation(
                violation_type=NetworkViolationType.DOMAIN_NOT_ALLOWED,
                url=url,
                detail=f"Domain not in allowlist: {host}",
            )

        return None

    def _scan_arguments(self, arguments: dict[str, Any]) -> list[NetworkViolation]:
        """Scan arguments for URLs and check them."""
        violations: list[NetworkViolation] = []

        for key, value in arguments.items():
            violations.extend(self._scan_value(key, value))

        return violations

    def _scan_value(self, key: str, value: Any) -> list[NetworkViolation]:
        """Recursively scan a value for URLs."""
        violations: list[NetworkViolation] = []

        if isinstance(value, str):
            # Check if key suggests this is a URL
            if key.lower() in self.config.url_argument_names or self._looks_like_url(value):
                violation = self.check_url(value)
                if violation:
                    violations.append(violation)

        elif isinstance(value, dict):
            for k, v in value.items():
                violations.extend(self._scan_value(k, v))

        elif isinstance(value, list):
            for item in value:
                violations.extend(self._scan_value(key, item))

        return violations

    def _looks_like_url(self, value: str) -> bool:
        """Check if a string looks like a URL."""
        return bool(re.match(r"^https?://", value, re.IGNORECASE))

    def _is_localhost(self, host: str) -> bool:
        """Check if host is localhost."""
        host_lower = host.lower()
        return host_lower in self.config.localhost_patterns or host_lower.startswith("127.")

    def _is_metadata_ip(self, host: str) -> bool:
        """Check if host is a cloud metadata endpoint."""
        return host.lower() in self.config.metadata_ips

    def _is_private_ip(self, host: str) -> bool:
        """Check if host is a private IP address."""
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        except ValueError:
            # Not an IP address, it's a hostname
            return False

    def _is_blocked_domain(self, host: str) -> bool:
        """Check if host matches blocked domains."""
        host_lower = host.lower()
        for blocked in self.config.blocked_domains:
            blocked_lower = blocked.lower()
            if host_lower == blocked_lower or host_lower.endswith(f".{blocked_lower}"):
                return True
        return False

    def _is_allowed_domain(self, host: str) -> bool:
        """Check if host matches allowed domains."""
        if self.config.allowed_domains is None:
            return True

        host_lower = host.lower()
        for allowed in self.config.allowed_domains:
            allowed_lower = allowed.lower()
            if host_lower == allowed_lower or host_lower.endswith(f".{allowed_lower}"):
                return True
        return False
