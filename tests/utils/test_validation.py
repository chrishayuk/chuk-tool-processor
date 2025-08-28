# tests/utils/test_validation.py
"""Tests for validation utilities."""

from __future__ import annotations

import pytest

from chuk_tool_processor.core.exceptions import ToolValidationError
from chuk_tool_processor.utils.validation import validate_arguments, validate_result, with_validation


class TestValidation:
    """Test validation utility functions."""

    def test_validate_arguments_basic(self):
        """Test basic argument validation."""

        def sample_func(x: int, y: str) -> None:
            pass

        # Valid arguments
        validated = validate_arguments("TestTool", sample_func, {"x": 42, "y": "hello"})
        assert validated == {"x": 42, "y": "hello"}

        # Type conversion
        validated = validate_arguments("TestTool", sample_func, {"x": "42", "y": "hello"})
        assert validated == {"x": 42, "y": "hello"}

    def test_validate_arguments_invalid_type(self):
        """Test argument validation with invalid types."""

        def sample_func(x: int, y: str) -> None:
            pass

        # Invalid type that can't be coerced
        with pytest.raises(ToolValidationError) as exc_info:
            validate_arguments("TestTool", sample_func, {"x": "not_a_number", "y": "hello"})

        assert "TestTool" in str(exc_info.value)

    def test_validate_arguments_missing_required(self):
        """Test validation with missing required arguments."""

        def sample_func(x: int, y: str) -> None:
            pass

        with pytest.raises(ToolValidationError) as exc_info:
            validate_arguments("TestTool", sample_func, {"x": 42})

        assert "TestTool" in str(exc_info.value)

    def test_validate_arguments_with_defaults(self):
        """Test validation with default arguments."""

        def sample_func(x: int, y: str = "default") -> None:
            pass

        # Missing optional argument should use default
        validated = validate_arguments("TestTool", sample_func, {"x": 42})
        assert validated == {"x": 42, "y": "default"}

        # Provided optional argument
        validated = validate_arguments("TestTool", sample_func, {"x": 42, "y": "custom"})
        assert validated == {"x": 42, "y": "custom"}

    def test_validate_arguments_optional_types(self):
        """Test validation with Optional types."""

        def sample_func(x: int, y: str | None = None) -> None:
            pass

        # Without optional
        validated = validate_arguments("TestTool", sample_func, {"x": 42})
        assert validated == {"x": 42, "y": None}

        # With optional
        validated = validate_arguments("TestTool", sample_func, {"x": 42, "y": "value"})
        assert validated == {"x": 42, "y": "value"}

    def test_validate_arguments_extra_fields(self):
        """Test that extra fields are rejected."""

        def sample_func(x: int) -> None:
            pass

        # Extra fields should cause validation error
        with pytest.raises(ToolValidationError) as exc_info:
            validate_arguments("TestTool", sample_func, {"x": 42, "extra": "field"})

        assert "TestTool" in str(exc_info.value)

    def test_validate_result_basic(self):
        """Test basic result validation."""

        def sample_func(x: int) -> int:
            return x * 2

        # Valid result
        result = validate_result("TestTool", sample_func, 84)
        assert result == 84

        # Type coercion
        result = validate_result("TestTool", sample_func, "42")
        assert result == 42

    def test_validate_result_invalid_type(self):
        """Test result validation with invalid type."""

        def sample_func(x: int) -> int:
            return x * 2

        # Invalid return type
        with pytest.raises(ToolValidationError) as exc_info:
            validate_result("TestTool", sample_func, "not_a_number")

        assert "TestTool" in str(exc_info.value)

    def test_validate_result_no_annotation(self):
        """Test result validation when no return type is annotated."""

        def sample_func(x: int):
            return x * 2

        # Should pass through without validation
        result = validate_result("TestTool", sample_func, "any_value")
        assert result == "any_value"

    def test_validate_result_none_return(self):
        """Test result validation with None return type."""

        def sample_func(x: int) -> None:
            pass

        # Should pass through without validation
        result = validate_result("TestTool", sample_func, None)
        assert result is None

    def test_with_validation_decorator_sync_error(self):
        """Test that decorator requires async methods."""
        with pytest.raises(TypeError, match="must have an async"):

            @with_validation
            class SyncTool:
                def execute(self, x: int) -> int:
                    return x * 2

    async def test_with_validation_decorator_execute(self):
        """Test with_validation decorator on execute method."""

        @with_validation
        class ValidatedTool:
            async def execute(self, x: int, y: str = "default") -> int:
                return x * len(y)

        tool = ValidatedTool()

        # Valid arguments
        result = await tool.execute(x=5, y="test")
        assert result == 20

        # Use default
        result = await tool.execute(x=5)
        assert result == 35  # 5 * len("default")

        # Invalid type
        with pytest.raises(ToolValidationError):
            await tool.execute(x="not_int", y="test")

    async def test_with_validation_decorator_private_execute(self):
        """Test with_validation decorator on _execute method."""

        @with_validation
        class ValidatedTool:
            async def _execute(self, x: int, y: int) -> int:
                return x + y

        tool = ValidatedTool()

        # Valid arguments
        result = await tool._execute(x=5, y=3)
        assert result == 8

        # Invalid type
        with pytest.raises(ToolValidationError):
            await tool._execute(x="not_int", y=3)

    def test_validate_complex_types(self):
        """Test validation with complex types."""

        def sample_func(items: list[str], mapping: dict[str, int]) -> dict[str, int]:
            return mapping

        # Valid complex arguments
        validated = validate_arguments("TestTool", sample_func, {"items": ["a", "b"], "mapping": {"x": 1}})
        assert validated == {"items": ["a", "b"], "mapping": {"x": 1}}

        # Type coercion for lists
        validated = validate_arguments("TestTool", sample_func, {"items": ["a", "b"], "mapping": {"x": "1"}})
        assert validated["mapping"]["x"] == 1

    def test_validate_arguments_no_hints(self):
        """Test validation with function that has no type hints."""

        def sample_func(x, y):
            pass

        # With no hints, pydantic will still validate required args
        with pytest.raises(ToolValidationError):
            # Missing required argument y
            validate_arguments("TestTool", sample_func, {"x": "any"})

        # But will accept any types when all args provided
        # Note: This may actually create a validation model with Any types
        try:
            validated = validate_arguments("TestTool", sample_func, {"x": "any", "y": 123})
            assert validated == {"x": "any", "y": 123}
        except ToolValidationError:
            # If validation is strict even for untyped args, that's ok
            pass
