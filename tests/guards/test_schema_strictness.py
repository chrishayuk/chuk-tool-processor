# tests/guards/test_schema_strictness.py
"""Tests for SchemaStrictnessGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.schema_strictness import (
    SchemaStrictnessConfig,
    SchemaStrictnessGuard,
    SchemaViolationType,
)


class TestSchemaStrictnessGuard:
    """Tests for SchemaStrictnessGuard."""

    @pytest.fixture
    def sample_schema(self) -> dict:
        """Sample JSON schema for testing."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"},
                "status": {"type": "string", "enum": ["active", "inactive", "pending"]},
            },
            "required": ["name", "age"],
        }

    @pytest.fixture
    def guard_with_schema(self, sample_schema: dict) -> SchemaStrictnessGuard:
        """Guard with schema getter."""
        schemas = {"test_tool": sample_schema}
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
            get_schema=lambda name: schemas.get(name),
        )
        # Pre-cache the schema
        guard._schema_cache["test_tool"] = sample_schema
        return guard

    def test_valid_arguments(self, guard_with_schema: SchemaStrictnessGuard):
        """Test valid arguments pass validation."""
        result = guard_with_schema.check("test_tool", {"name": "Alice", "age": 30})
        assert result.verdict == GuardVerdict.ALLOW

    def test_missing_required_field(self, guard_with_schema: SchemaStrictnessGuard):
        """Test missing required field is blocked."""
        result = guard_with_schema.check("test_tool", {"name": "Alice"})
        assert result.blocked
        assert "missing" in result.reason.lower()

    def test_wrong_type(self, guard_with_schema: SchemaStrictnessGuard):
        """Test wrong type is blocked."""
        result = guard_with_schema.check("test_tool", {"name": "Alice", "age": "thirty"})
        assert result.blocked
        # Error message contains "integer" or "type"
        assert "integer" in result.reason.lower() or "type" in result.reason.lower()

    def test_unknown_field_blocked(self, guard_with_schema: SchemaStrictnessGuard):
        """Test unknown field is blocked when not allowed."""
        result = guard_with_schema.check("test_tool", {"name": "Alice", "age": 30, "unknown_field": "value"})
        assert result.blocked
        assert "unknown" in result.reason.lower()

    def test_unknown_field_allowed(self, sample_schema: dict):
        """Test unknown field is allowed when configured."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK, allow_extra_fields=True),
            get_schema=lambda _: sample_schema,
        )
        guard._schema_cache["test_tool"] = sample_schema
        result = guard.check("test_tool", {"name": "Alice", "age": 30, "unknown_field": "value"})
        assert result.allowed

    def test_invalid_enum(self, guard_with_schema: SchemaStrictnessGuard):
        """Test invalid enum value is blocked."""
        result = guard_with_schema.check("test_tool", {"name": "Alice", "age": 30, "status": "invalid"})
        assert result.blocked
        assert "enum" in result.reason.lower()

    def test_valid_enum(self, guard_with_schema: SchemaStrictnessGuard):
        """Test valid enum value passes."""
        result = guard_with_schema.check("test_tool", {"name": "Alice", "age": 30, "status": "active"})
        assert result.allowed

    def test_empty_required_string(self, guard_with_schema: SchemaStrictnessGuard):
        """Test empty required string is blocked."""
        result = guard_with_schema.check("test_tool", {"name": "   ", "age": 30})
        assert result.blocked
        assert "empty" in result.reason.lower()

    def test_type_coercion(self, sample_schema: dict):
        """Test type coercion when enabled."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK, coerce_types=True),
            get_schema=lambda _: sample_schema,
        )
        guard._schema_cache["test_tool"] = sample_schema
        result = guard.check("test_tool", {"name": "Alice", "age": "30"})
        # Should repair with coerced value
        assert result.verdict == GuardVerdict.REPAIR
        assert result.repaired_args is not None
        assert result.repaired_args["age"] == 30
        # Message can contain "coerced" or "repair"

    def test_warn_mode(self, sample_schema: dict):
        """Test warn mode returns warning instead of block."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.WARN),
            get_schema=lambda _: sample_schema,
        )
        guard._schema_cache["test_tool"] = sample_schema
        result = guard.check("test_tool", {"name": "Alice"})  # Missing age
        assert result.verdict == GuardVerdict.WARN

    def test_off_mode(self, sample_schema: dict):
        """Test off mode allows everything."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.OFF),
            get_schema=lambda _: sample_schema,
        )
        result = guard.check("test_tool", {"invalid": "args"})
        assert result.allowed

    def test_no_schema_allows(self):
        """Test no schema available allows execution."""
        guard = SchemaStrictnessGuard()
        result = guard.check("unknown_tool", {"any": "args"})
        assert result.allowed

    def test_clear_cache(self, guard_with_schema: SchemaStrictnessGuard):
        """Test cache clearing."""
        assert "test_tool" in guard_with_schema._schema_cache
        guard_with_schema.clear_cache()
        assert "test_tool" not in guard_with_schema._schema_cache


class TestSchemaViolationTypes:
    """Tests for violation type detection."""

    @pytest.fixture
    def guard(self) -> SchemaStrictnessGuard:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
        )
        guard._schema_cache["tool"] = schema
        return guard

    def test_violation_type_missing_required(self, guard: SchemaStrictnessGuard):
        """Test MISSING_REQUIRED violation type."""
        result = guard.check("tool", {})
        assert result.blocked
        violations = result.details.get("violations", [])
        assert any(v.get("violation_type") == SchemaViolationType.MISSING_REQUIRED.value for v in violations)

    def test_violation_type_type_mismatch(self, guard: SchemaStrictnessGuard):
        """Test TYPE_MISMATCH violation type."""
        result = guard.check("tool", {"name": 123})
        assert result.blocked
        violations = result.details.get("violations", [])
        # Check for either the enum or its value
        assert any(
            v.get("violation_type") == SchemaViolationType.TYPE_MISMATCH.value
            or v.get("violation_type") == SchemaViolationType.TYPE_MISMATCH
            for v in violations
        )


class TestSchemaStrictnessGuardAsync:
    """Tests for async methods of SchemaStrictnessGuard."""

    @pytest.fixture
    def sample_schema(self) -> dict:
        """Sample JSON schema for testing."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }

    @pytest.mark.asyncio
    async def test_check_async_off_mode(self):
        """Test check_async returns allow when mode is OFF (line 131-132)."""
        guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(mode=EnforcementLevel.OFF))
        result = await guard.check_async("tool", {"invalid": "args"})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_async_with_sync_schema_getter(self, sample_schema: dict):
        """Test check_async with synchronous schema getter (line 148-149)."""
        schemas = {"test_tool": sample_schema}

        def sync_getter(name: str) -> dict | None:
            return schemas.get(name)

        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
            get_schema=sync_getter,
        )

        result = await guard.check_async("test_tool", {"name": "Alice"})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_async_with_async_schema_getter(self, sample_schema: dict):
        """Test check_async with async schema getter (line 149-150)."""
        schemas = {"test_tool": sample_schema}

        async def async_getter(name: str) -> dict | None:
            return schemas.get(name)

        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
            get_schema=async_getter,
        )

        result = await guard.check_async("test_tool", {"name": "Alice"})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_async_cached_schema(self, sample_schema: dict):
        """Test check_async uses cached schema (lines 142-143)."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
        )
        # Pre-populate cache
        guard._schema_cache["test_tool"] = sample_schema

        result = await guard.check_async("test_tool", {"name": "Alice"})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_async_no_schema(self):
        """Test check_async with no schema available (lines 135-136)."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
        )

        result = await guard.check_async("unknown_tool", {"any": "args"})
        assert result.allowed
        assert "no schema" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_async_validation_failure(self, sample_schema: dict):
        """Test check_async with validation failure (line 138)."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
        )
        guard._schema_cache["test_tool"] = sample_schema

        result = await guard.check_async("test_tool", {})
        assert result.blocked
        assert "missing" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_fetch_schema_caches_result(self, sample_schema: dict):
        """Test _fetch_schema caches the result (lines 152-153)."""
        call_count = 0

        async def counting_getter(name: str) -> dict | None:
            nonlocal call_count
            call_count += 1
            return sample_schema if name == "test_tool" else None

        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
            get_schema=counting_getter,
        )

        # First call should fetch
        await guard._fetch_schema("test_tool")
        assert call_count == 1

        # Second call should use cache
        await guard._fetch_schema("test_tool")
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_schema_no_getter(self):
        """Test _fetch_schema with no getter (lines 145-146)."""
        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
        )

        result = await guard._fetch_schema("any_tool")
        assert result is None


class TestSchemaTypeChecking:
    """Tests for type checking methods."""

    @pytest.fixture
    def guard(self) -> SchemaStrictnessGuard:
        return SchemaStrictnessGuard()

    def test_get_json_type_null(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for null (line 303)."""
        assert guard._get_json_type(None) == "null"

    def test_get_json_type_boolean(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for boolean (line 305)."""
        assert guard._get_json_type(True) == "boolean"
        assert guard._get_json_type(False) == "boolean"

    def test_get_json_type_integer(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for integer."""
        assert guard._get_json_type(42) == "integer"
        assert guard._get_json_type(-10) == "integer"

    def test_get_json_type_number(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for float (line 309)."""
        assert guard._get_json_type(3.14) == "number"

    def test_get_json_type_string(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for string."""
        assert guard._get_json_type("hello") == "string"

    def test_get_json_type_array(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for array (line 312)."""
        assert guard._get_json_type([1, 2, 3]) == "array"
        assert guard._get_json_type([]) == "array"

    def test_get_json_type_object(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for object (line 314)."""
        assert guard._get_json_type({"key": "value"}) == "object"
        assert guard._get_json_type({}) == "object"

    def test_get_json_type_unknown(self, guard: SchemaStrictnessGuard):
        """Test _get_json_type for unknown types (line 316)."""
        assert guard._get_json_type(object()) == "unknown"
        assert guard._get_json_type(lambda: None) == "unknown"


class TestSchemaTypeCoercion:
    """Tests for type coercion methods."""

    @pytest.fixture
    def guard(self) -> SchemaStrictnessGuard:
        return SchemaStrictnessGuard(config=SchemaStrictnessConfig(coerce_types=True))

    def test_coerce_string_to_integer(self, guard: SchemaStrictnessGuard):
        """Test coercing string to integer (lines 320-324)."""
        assert guard._try_coerce("42", "integer") == 42
        assert guard._try_coerce("-10", "integer") == -10
        assert guard._try_coerce("invalid", "integer") is None

    def test_coerce_string_to_number(self, guard: SchemaStrictnessGuard):
        """Test coercing string to number (lines 325-329)."""
        assert guard._try_coerce("3.14", "number") == 3.14
        assert guard._try_coerce("-2.5", "number") == -2.5
        assert guard._try_coerce("invalid", "number") is None

    def test_coerce_number_to_string(self, guard: SchemaStrictnessGuard):
        """Test coercing number to string (lines 330-331)."""
        assert guard._try_coerce(42, "string") == "42"
        assert guard._try_coerce(3.14, "string") == "3.14"

    def test_coerce_string_to_boolean(self, guard: SchemaStrictnessGuard):
        """Test coercing string to boolean (lines 332-336)."""
        assert guard._try_coerce("true", "boolean") is True
        assert guard._try_coerce("True", "boolean") is True
        assert guard._try_coerce("1", "boolean") is True
        assert guard._try_coerce("yes", "boolean") is True
        assert guard._try_coerce("false", "boolean") is False
        assert guard._try_coerce("False", "boolean") is False
        assert guard._try_coerce("0", "boolean") is False
        assert guard._try_coerce("no", "boolean") is False
        assert guard._try_coerce("invalid", "boolean") is None

    def test_coerce_integer_to_number(self, guard: SchemaStrictnessGuard):
        """Test coercing integer to number (lines 337-338)."""
        assert guard._try_coerce(42, "number") == 42.0
        assert guard._try_coerce(-10, "number") == -10.0

    def test_coerce_unsupported_returns_none(self, guard: SchemaStrictnessGuard):
        """Test unsupported coercion returns None (line 339)."""
        assert guard._try_coerce({"key": "value"}, "string") is None
        assert guard._try_coerce([1, 2, 3], "integer") is None


class TestCheckTypeMethod:
    """Tests for _check_type method."""

    def test_check_type_no_expected_type(self):
        """Test _check_type when no type is specified in schema (lines 274-276)."""
        guard = SchemaStrictnessGuard()
        result = guard._check_type("field", "value", {})
        assert result.violation is None
        assert result.coerced_value is None

    def test_check_type_matching_type(self):
        """Test _check_type when type matches (lines 280-281)."""
        guard = SchemaStrictnessGuard()
        result = guard._check_type("field", "hello", {"type": "string"})
        assert result.violation is None
        assert result.coerced_value is None

    def test_check_type_mismatch_no_coercion(self):
        """Test _check_type with mismatch and no coercion."""
        guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(coerce_types=False))
        result = guard._check_type("field", "42", {"type": "integer"})
        assert result.violation is not None
        assert result.violation.violation_type == SchemaViolationType.TYPE_MISMATCH

    def test_check_type_mismatch_with_coercion_success(self):
        """Test _check_type with mismatch and successful coercion (lines 284-287)."""
        guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(coerce_types=True))
        result = guard._check_type("field", "42", {"type": "integer"})
        assert result.violation is None
        assert result.coerced_value == 42

    def test_check_type_mismatch_with_coercion_failure(self):
        """Test _check_type with mismatch and failed coercion (lines 289-298)."""
        guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(coerce_types=True))
        result = guard._check_type("field", "not_a_number", {"type": "integer"})
        assert result.violation is not None
        assert result.violation.violation_type == SchemaViolationType.TYPE_MISMATCH


class TestSyncCheckEdgeCases:
    """Tests for edge cases in synchronous check method."""

    def test_check_schema_not_cached_no_getter(self):
        """Test check when schema not cached and no getter (lines 116-117)."""
        guard = SchemaStrictnessGuard(config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK))
        # No schema cached and no getter
        result = guard.check("unknown_tool", {"any": "args"})
        assert result.allowed
        assert "no schema" in result.reason.lower()

    def test_check_schema_not_cached_with_getter(self):
        """Test check when schema not cached but getter exists (line 121)."""

        def sync_getter(name: str) -> dict | None:
            return {"type": "object", "properties": {}} if name == "known_tool" else None

        guard = SchemaStrictnessGuard(
            config=SchemaStrictnessConfig(mode=EnforcementLevel.BLOCK),
            get_schema=sync_getter,
        )
        # Getter exists but schema not in cache yet
        result = guard.check("unknown_tool", {"any": "args"})
        assert result.allowed
        assert "not cached" in result.reason.lower()
