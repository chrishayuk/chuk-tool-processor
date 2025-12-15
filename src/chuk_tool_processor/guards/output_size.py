# chuk_tool_processor/guards/output_size.py
"""Output size guard to prevent pathological payloads.

Caps bytes, tokens, array lengths, and nesting depth.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class TruncationMode(str, Enum):
    """How to handle oversized outputs."""

    ERROR = "error"  # Block with error
    TRUNCATE = "truncate"  # Truncate and return partial
    PAGINATE = "paginate"  # Return with pagination info


class SizeViolationType(str, Enum):
    """Types of size violations."""

    BYTES_EXCEEDED = "bytes_exceeded"
    TOKENS_EXCEEDED = "tokens_exceeded"
    ARRAY_LENGTH_EXCEEDED = "array_length_exceeded"
    DEPTH_EXCEEDED = "depth_exceeded"


class SizeViolation(BaseModel):
    """A size limit violation."""

    violation_type: SizeViolationType
    limit: int
    actual: int
    path: str = ""


class TruncatedResult(BaseModel):
    """Envelope for truncated results."""

    partial: bool = True
    truncated_at: str
    original_size: int
    returned_size: int
    data: Any
    continuation_hint: str | None = None


class OutputSizeConfig(BaseModel):
    """Configuration for OutputSizeGuard."""

    max_bytes: int = Field(
        default=100_000,
        description="Maximum size in bytes (default 100KB)",
    )
    max_tokens: int | None = Field(
        default=None,
        description="Maximum estimated tokens (chars/4 heuristic)",
    )
    max_array_length: int = Field(
        default=1000,
        description="Maximum length of any array in output",
    )
    max_depth: int = Field(
        default=20,
        description="Maximum nesting depth",
    )
    max_string_length: int = Field(
        default=10_000,
        description="Maximum length for individual strings before truncation",
    )
    truncation_mode: TruncationMode = Field(
        default=TruncationMode.ERROR,
        description="How to handle oversized outputs",
    )
    chars_per_token: int = Field(
        default=4,
        description="Characters per token estimate",
    )


class OutputSizeGuard(BaseGuard):
    """Guard that limits output size to prevent context/storage blowup.

    Checks:
    - Total byte size
    - Estimated token count
    - Array/list lengths
    - Nesting depth

    Can error, truncate, or paginate based on configuration.
    """

    def __init__(self, config: OutputSizeConfig | None = None) -> None:
        self.config = config or OutputSizeConfig()

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Pre-execution check - always allows (size is post-execution)."""
        return self.allow()

    def check_output(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],
        result: Any,
    ) -> GuardResult:
        """Check output size after execution."""
        violations = self._check_violations(result)

        if not violations:
            return self.allow()

        if self.config.truncation_mode == TruncationMode.ERROR:
            messages = [self._format_violation(v) for v in violations]
            return self.block(
                reason=f"Output size limits exceeded: {'; '.join(messages)}",
                violations=[v.model_dump() for v in violations],
            )

        # Truncate or paginate
        truncated = self._truncate_result(result, violations)
        return self.repair(
            reason="Output truncated due to size limits",
            repaired_args=arguments,
            fallback_response=json.dumps(truncated.model_dump()),
        )

    def _check_violations(self, result: Any) -> list[SizeViolation]:
        """Check for all size violations."""
        violations: list[SizeViolation] = []

        # Check byte size
        try:
            serialized = json.dumps(result, default=str)
            byte_size = len(serialized.encode("utf-8"))

            if byte_size > self.config.max_bytes:
                violations.append(
                    SizeViolation(
                        violation_type=SizeViolationType.BYTES_EXCEEDED,
                        limit=self.config.max_bytes,
                        actual=byte_size,
                    )
                )

            # Check token estimate
            if self.config.max_tokens is not None:
                token_estimate = len(serialized) // self.config.chars_per_token
                if token_estimate > self.config.max_tokens:
                    violations.append(
                        SizeViolation(
                            violation_type=SizeViolationType.TOKENS_EXCEEDED,
                            limit=self.config.max_tokens,
                            actual=token_estimate,
                        )
                    )
        except (TypeError, ValueError):
            pass

        # Check array lengths and depth
        array_violation = self._check_array_length(result, "")
        if array_violation:
            violations.append(array_violation)

        depth_violation = self._check_depth(result, 0, "")
        if depth_violation:
            violations.append(depth_violation)

        return violations

    def _check_array_length(
        self,
        value: Any,
        path: str,
    ) -> SizeViolation | None:
        """Recursively check array lengths."""
        if isinstance(value, list):
            if len(value) > self.config.max_array_length:
                return SizeViolation(
                    violation_type=SizeViolationType.ARRAY_LENGTH_EXCEEDED,
                    limit=self.config.max_array_length,
                    actual=len(value),
                    path=path or "root",
                )
            for i, item in enumerate(value):
                violation = self._check_array_length(item, f"{path}[{i}]")
                if violation:
                    return violation

        elif isinstance(value, dict):
            for k, v in value.items():
                violation = self._check_array_length(v, f"{path}.{k}" if path else k)
                if violation:
                    return violation

        return None

    def _check_depth(
        self,
        value: Any,
        current_depth: int,
        path: str,
    ) -> SizeViolation | None:
        """Check nesting depth."""
        if current_depth > self.config.max_depth:
            return SizeViolation(
                violation_type=SizeViolationType.DEPTH_EXCEEDED,
                limit=self.config.max_depth,
                actual=current_depth,
                path=path or "root",
            )

        if isinstance(value, dict):
            for k, v in value.items():
                violation = self._check_depth(v, current_depth + 1, f"{path}.{k}" if path else k)
                if violation:
                    return violation

        elif isinstance(value, list):
            for i, item in enumerate(value):
                violation = self._check_depth(item, current_depth + 1, f"{path}[{i}]")
                if violation:
                    return violation

        return None

    def _truncate_result(
        self,
        result: Any,
        violations: list[SizeViolation],
    ) -> TruncatedResult:
        """Truncate result to fit within limits."""
        try:
            original_size = len(json.dumps(result, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            original_size = 0

        truncated_data = self._truncate_value(result, 0)

        try:
            returned_size = len(json.dumps(truncated_data, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            returned_size = 0

        truncation_reason = violations[0].violation_type.value if violations else "unknown"

        return TruncatedResult(
            truncated_at=truncation_reason,
            original_size=original_size,
            returned_size=returned_size,
            data=truncated_data,
            continuation_hint="Use pagination or request smaller scope"
            if self.config.truncation_mode == TruncationMode.PAGINATE
            else None,
        )

    def _truncate_value(self, value: Any, depth: int) -> Any:
        """Recursively truncate a value."""
        if depth > self.config.max_depth:
            return "... (depth limit reached)"

        if isinstance(value, list):
            if len(value) > self.config.max_array_length:
                truncated = [self._truncate_value(v, depth + 1) for v in value[: self.config.max_array_length]]
                truncated.append(f"... ({len(value) - self.config.max_array_length} more items)")
                return truncated
            return [self._truncate_value(v, depth + 1) for v in value]

        if isinstance(value, dict):
            return {k: self._truncate_value(v, depth + 1) for k, v in value.items()}

        if isinstance(value, str) and len(value) > self.config.max_string_length:
            return value[: self.config.max_string_length] + "... (truncated)"

        return value

    def _format_violation(self, violation: SizeViolation) -> str:
        """Format a violation for error message."""
        path_info = f" at {violation.path}" if violation.path else ""
        return f"{violation.violation_type.value}: {violation.actual} > {violation.limit}{path_info}"
