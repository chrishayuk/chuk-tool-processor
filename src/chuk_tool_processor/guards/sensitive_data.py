# chuk_tool_processor/guards/sensitive_data.py
"""Sensitive data guard for redacting or blocking secrets.

Detects and handles API keys, tokens, passwords, and other sensitive data.
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class SensitiveDataType(str, Enum):
    """Types of sensitive data patterns."""

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    AWS_KEY = "aws_key"
    PRIVATE_KEY = "private_key"
    PASSWORD_IN_URL = "password_in_url"
    GENERIC_SECRET = "generic_secret"
    JWT_TOKEN = "jwt_token"
    BASIC_AUTH = "basic_auth"


class RedactMode(str, Enum):
    """How to handle detected secrets."""

    BLOCK = "block"  # Block execution entirely
    REDACT = "redact"  # Replace with [REDACTED]
    HASH = "hash"  # Replace with hash for debugging


class SensitiveMatch(BaseModel):
    """A detected sensitive data match."""

    data_type: SensitiveDataType
    field_path: str
    redacted_value: str | None = None


class SensitiveDataConfig(BaseModel):
    """Configuration for SensitiveDataGuard."""

    mode: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level",
    )
    redact_mode: RedactMode = Field(
        default=RedactMode.BLOCK,
        description="How to handle detected secrets",
    )
    check_args: bool = Field(
        default=True,
        description="Check tool arguments for secrets",
    )
    check_output: bool = Field(
        default=True,
        description="Check tool outputs for secrets",
    )
    allowlist: set[str] = Field(
        default_factory=set,
        description="Patterns explicitly allowed (e.g., test keys)",
    )
    custom_patterns: dict[str, str] = Field(
        default_factory=dict,
        description="Custom regex patterns to detect",
    )
    min_secret_length: int = Field(
        default=16,
        description="Minimum length for generic secret detection",
    )


class SensitiveDataGuard(BaseGuard):
    """Guard that detects and handles sensitive data.

    Detects:
    - API keys (various formats)
    - Bearer tokens
    - AWS access keys
    - Private keys (PEM format)
    - Passwords in URLs
    - JWTs
    - Basic auth headers

    Can block, redact, or hash detected secrets.
    """

    # Default patterns for sensitive data detection
    DEFAULT_PATTERNS: dict[SensitiveDataType, str] = {
        SensitiveDataType.API_KEY: r"(?:api[_-]?key|apikey|api_secret)[\"'\s:=]+[\"']?([a-zA-Z0-9_\-]{20,})",
        SensitiveDataType.BEARER_TOKEN: r"[Bb]earer\s+([a-zA-Z0-9_\-\.]+)",
        SensitiveDataType.AWS_KEY: r"(AKIA[0-9A-Z]{16})",
        SensitiveDataType.PRIVATE_KEY: r"(-----BEGIN[A-Z\s]+PRIVATE KEY-----)",
        SensitiveDataType.PASSWORD_IN_URL: r"://([^:]+):([^@]+)@",
        SensitiveDataType.JWT_TOKEN: r"(eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)",
        SensitiveDataType.BASIC_AUTH: r"[Bb]asic\s+([a-zA-Z0-9+/=]{20,})",
        SensitiveDataType.GENERIC_SECRET: r"(?:secret|password|passwd|token|credential)[\"'\s:=]+[\"']?([a-zA-Z0-9_\-]{16,})",
    }

    def __init__(self, config: SensitiveDataConfig | None = None) -> None:
        self.config = config or SensitiveDataConfig()
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[SensitiveDataType | str, re.Pattern[str]]:
        """Compile all regex patterns."""
        patterns: dict[SensitiveDataType | str, re.Pattern[str]] = {}

        for data_type, pattern in self.DEFAULT_PATTERNS.items():
            patterns[data_type] = re.compile(pattern, re.IGNORECASE)

        for name, pattern in self.config.custom_patterns.items():
            patterns[name] = re.compile(pattern, re.IGNORECASE)

        return patterns

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check arguments for sensitive data before execution."""
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        if not self.config.check_args:
            return self.allow()

        matches = self._scan_value(arguments, "args")

        if not matches:
            return self.allow()

        return self._handle_matches(matches, arguments, is_output=False)

    def check_output(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
        result: Any,
    ) -> GuardResult:
        """Check output for sensitive data after execution."""
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        if not self.config.check_output:
            return self.allow()

        matches = self._scan_value(result, "output")

        if not matches:
            return self.allow()

        return self._handle_matches(matches, result, is_output=True)

    def _scan_value(
        self,
        value: Any,
        path: str,
    ) -> list[SensitiveMatch]:
        """Recursively scan a value for sensitive data."""
        matches: list[SensitiveMatch] = []

        if isinstance(value, str):
            matches.extend(self._scan_string(value, path))

        elif isinstance(value, dict):
            for k, v in value.items():
                field_path = f"{path}.{k}" if path else k
                matches.extend(self._scan_value(v, field_path))

        elif isinstance(value, list):
            for i, item in enumerate(value):
                matches.extend(self._scan_value(item, f"{path}[{i}]"))

        return matches

    def _scan_string(
        self,
        value: str,
        path: str,
    ) -> list[SensitiveMatch]:
        """Scan a string for sensitive patterns."""
        matches: list[SensitiveMatch] = []

        for pattern_key, pattern in self._compiled_patterns.items():
            for match in pattern.finditer(value):
                matched_value = match.group(1) if match.groups() else match.group(0)

                # Check allowlist
                if self._is_allowed(matched_value):
                    continue

                data_type = (
                    pattern_key if isinstance(pattern_key, SensitiveDataType) else SensitiveDataType.GENERIC_SECRET
                )

                matches.append(
                    SensitiveMatch(
                        data_type=data_type,
                        field_path=path,
                        redacted_value=self._redact_value(matched_value),
                    )
                )

        return matches

    def _is_allowed(self, value: str) -> bool:
        """Check if a value is in the allowlist."""
        return any(allowed in value or value in allowed for allowed in self.config.allowlist)

    def _redact_value(self, value: str) -> str:
        """Create redacted version of sensitive value."""
        if self.config.redact_mode == RedactMode.HASH:
            hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
            return f"[HASH:{hash_val}]"
        return "[REDACTED]"

    def _handle_matches(
        self,
        matches: list[SensitiveMatch],
        original_value: Any,
        is_output: bool,
    ) -> GuardResult:
        """Handle detected sensitive data based on config."""
        context = "output" if is_output else "arguments"
        types_found = {m.data_type.value for m in matches}
        paths = [m.field_path for m in matches]

        message = f"Sensitive data detected in {context}: {', '.join(types_found)} at {', '.join(paths[:3])}"
        if len(paths) > 3:
            message += f" (+{len(paths) - 3} more)"

        if self.config.mode == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                matches=[m.model_dump() for m in matches],
            )

        if self.config.redact_mode == RedactMode.BLOCK:
            return self.block(
                reason=message,
                matches=[m.model_dump() for m in matches],
            )

        # Redact and continue
        redacted = self._apply_redaction(original_value, matches)
        return self.repair(
            reason=f"Sensitive data redacted in {context}",
            repaired_args=redacted if not is_output else None,
            fallback_response=str(redacted) if is_output else None,
        )

    def _apply_redaction(
        self,
        value: Any,
        matches: list[SensitiveMatch],
    ) -> Any:
        """Apply redaction to detected sensitive data."""
        if isinstance(value, str):
            result = value
            for _pattern_key, pattern in self._compiled_patterns.items():
                result = pattern.sub(
                    lambda m: self._redact_value(m.group(1) if m.groups() else m.group(0)),
                    result,
                )
            return result

        if isinstance(value, dict):
            return {k: self._apply_redaction(v, matches) for k, v in value.items()}

        if isinstance(value, list):
            return [self._apply_redaction(item, matches) for item in value]

        return value
