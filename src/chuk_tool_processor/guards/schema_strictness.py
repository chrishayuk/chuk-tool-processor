# chuk_tool_processor/guards/schema_strictness.py
"""Schema strictness guard for validating tool arguments against JSON schemas.

Blocks or auto-fixes calls that don't conform to tool JSON schemas.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class SchemaViolationType(str, Enum):
    """Types of schema violations."""

    MISSING_REQUIRED = "missing_required"
    UNKNOWN_FIELD = "unknown_field"
    TYPE_MISMATCH = "type_mismatch"
    ENUM_INVALID = "enum_invalid"
    EMPTY_REQUIRED = "empty_required"
    CONSTRAINT_VIOLATED = "constraint_violated"


class SchemaViolation(BaseModel):
    """A single schema violation."""

    violation_type: SchemaViolationType
    field: str
    message: str
    expected: Any = None
    actual: Any = None


class SchemaValidationResult(BaseModel):
    """Result of schema validation."""

    valid: bool
    violations: list[SchemaViolation] = Field(default_factory=list)
    coerced_args: dict[str, Any] | None = None


class SchemaStrictnessConfig(BaseModel):
    """Configuration for SchemaStrictnessGuard."""

    mode: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level for schema violations",
    )
    coerce_types: bool = Field(
        default=False,
        description="Auto-coerce compatible types (e.g., '18' -> 18)",
    )
    allow_extra_fields: bool = Field(
        default=False,
        description="Allow fields not defined in schema",
    )
    require_all_required: bool = Field(
        default=True,
        description="Require all required fields to be present",
    )
    reject_empty_strings: bool = Field(
        default=True,
        description="Reject empty/whitespace strings for required fields",
    )


# Type alias for schema getter callback
SchemaGetter = Callable[[str], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]


class SchemaStrictnessGuard(BaseGuard):
    """Guard that validates tool arguments against JSON schemas.

    Validates:
    - Required fields are present
    - Field types match schema
    - Enum values are valid
    - No unknown fields (configurable)
    - Required strings are non-empty (configurable)

    Optionally coerces compatible types in lenient mode.
    """

    def __init__(
        self,
        config: SchemaStrictnessConfig | None = None,
        get_schema: SchemaGetter | None = None,
    ) -> None:
        """Initialize the guard.

        Args:
            config: Guard configuration
            get_schema: Async or sync callback to fetch schema for a tool name.
                       Returns JSON Schema dict or None if no schema available.
        """
        self.config = config or SchemaStrictnessConfig()
        self._get_schema = get_schema
        self._schema_cache: dict[str, dict[str, Any] | None] = {}

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Synchronous check - delegates to cached schema if available."""
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        schema = self._schema_cache.get(tool_name)
        if schema is None and self._get_schema is None:
            return self.allow(reason="No schema available for validation")

        if schema is None:
            # Schema not cached - need async fetch
            return self.allow(reason="Schema not cached, use async check")

        return self._validate_against_schema(tool_name, arguments, schema)

    async def check_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Async check with schema fetching."""
        if self.config.mode == EnforcementLevel.OFF:
            return self.allow()

        schema = await self._fetch_schema(tool_name)
        if schema is None:
            return self.allow(reason="No schema available for validation")

        return self._validate_against_schema(tool_name, arguments, schema)

    async def _fetch_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Fetch and cache schema for a tool."""
        if tool_name in self._schema_cache:
            return self._schema_cache[tool_name]

        if self._get_schema is None:
            return None

        result = self._get_schema(tool_name)
        if isinstance(result, Awaitable):
            result = await result

        self._schema_cache[tool_name] = result
        return result

    def _validate_against_schema(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> GuardResult:
        """Validate arguments against a JSON schema."""
        validation = self._perform_validation(arguments, schema)

        if validation.valid:
            if validation.coerced_args and self.config.coerce_types:
                return self.repair(
                    reason="Arguments coerced to match schema",
                    repaired_args=validation.coerced_args,
                )
            return self.allow()

        violation_messages = [v.message for v in validation.violations]
        message = f"Schema validation failed for {tool_name}: {'; '.join(violation_messages)}"

        if self.config.mode == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                violations=[v.model_dump() for v in validation.violations],
            )

        return self.block(
            reason=message,
            violations=[v.model_dump() for v in validation.violations],
        )

    def _perform_validation(
        self,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> SchemaValidationResult:
        """Perform the actual validation logic."""
        violations: list[SchemaViolation] = []
        coerced: dict[str, Any] = dict(arguments)
        did_coerce = False

        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        # Check required fields
        if self.config.require_all_required:
            for field in required:
                if field not in arguments:
                    violations.append(
                        SchemaViolation(
                            violation_type=SchemaViolationType.MISSING_REQUIRED,
                            field=field,
                            message=f"Missing required field: {field}",
                        )
                    )
                elif self.config.reject_empty_strings:
                    value = arguments[field]
                    if isinstance(value, str) and not value.strip():
                        violations.append(
                            SchemaViolation(
                                violation_type=SchemaViolationType.EMPTY_REQUIRED,
                                field=field,
                                message=f"Required field '{field}' is empty or whitespace",
                                actual=value,
                            )
                        )

        # Check unknown fields
        if not self.config.allow_extra_fields:
            for field in arguments:
                if field not in properties:
                    violations.append(
                        SchemaViolation(
                            violation_type=SchemaViolationType.UNKNOWN_FIELD,
                            field=field,
                            message=f"Unknown field: {field}",
                        )
                    )

        # Validate types and enums
        for field, value in arguments.items():
            if field not in properties:
                continue

            field_schema = properties[field]
            type_result = self._check_type(field, value, field_schema)

            if type_result.violation:
                violations.append(type_result.violation)
            elif type_result.coerced_value is not None:
                # Type was coerced successfully
                coerced[field] = type_result.coerced_value
                did_coerce = True

            # Check enum
            if "enum" in field_schema and value not in field_schema["enum"]:
                violations.append(
                    SchemaViolation(
                        violation_type=SchemaViolationType.ENUM_INVALID,
                        field=field,
                        message=f"Value '{value}' not in allowed enum values for {field}",
                        expected=field_schema["enum"],
                        actual=value,
                    )
                )

        return SchemaValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            coerced_args=coerced if did_coerce else None,
        )

    def _check_type(
        self,
        field: str,
        value: Any,
        field_schema: dict[str, Any],
    ) -> _TypeCheckResult:
        """Check if value matches expected type, with optional coercion."""
        expected_type = field_schema.get("type")
        if expected_type is None:
            return _TypeCheckResult()

        actual_type = self._get_json_type(value)

        if actual_type == expected_type:
            return _TypeCheckResult()

        # Try coercion only if configured
        if self.config.coerce_types:
            coerced = self._try_coerce(value, expected_type)
            if coerced is not None:
                return _TypeCheckResult(coerced_value=coerced)

        # Type mismatch - record violation
        return _TypeCheckResult(
            violation=SchemaViolation(
                violation_type=SchemaViolationType.TYPE_MISMATCH,
                field=field,
                message=f"Field '{field}' expected {expected_type}, got {actual_type}",
                expected=expected_type,
                actual=actual_type,
            )
        )

    def _get_json_type(self, value: Any) -> str:
        """Get JSON Schema type for a Python value."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "unknown"

    def _try_coerce(self, value: Any, target_type: str) -> Any | None:
        """Try to coerce a value to target type."""
        if target_type == "integer" and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        if target_type == "number" and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        if target_type == "string" and isinstance(value, (int, float)):
            return str(value)
        if target_type == "boolean" and isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True
            if value.lower() in ("false", "0", "no"):
                return False
        if target_type == "number" and isinstance(value, int):
            return float(value)
        return None

    def clear_cache(self) -> None:
        """Clear the schema cache."""
        self._schema_cache.clear()


class _TypeCheckResult(BaseModel):
    """Result of a type check."""

    violation: SchemaViolation | None = None
    coerced_value: Any = None
