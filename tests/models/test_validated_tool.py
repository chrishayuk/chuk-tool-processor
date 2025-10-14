# tests/models/test_validated_tool.py
"""Tests for the ValidatedTool model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from chuk_tool_processor.models.validated_tool import ValidatedTool


class TestParameters(BaseModel):
    """Test parameter model."""

    name: str = Field(..., description="Name parameter")
    age: int = Field(..., ge=0, le=120, description="Age parameter")
    optional: str | None = Field(None, description="Optional parameter")


class MockValidatedTool(ValidatedTool):
    """Mock validated tool for testing."""

    class Arguments(BaseModel):
        """Tool arguments."""

        name: str = Field(..., description="Name parameter")
        age: int = Field(..., ge=0, le=120, description="Age parameter")
        optional: str | None = Field(None, description="Optional parameter")

    class Result(BaseModel):
        """Tool result."""

        message: str

    async def _execute(self, name: str, age: int, optional: str | None = None) -> Result:
        """Execute the tool with validated parameters."""
        msg = f"Hello {name}, age {age}" + (f", {optional}" if optional else "")
        return self.Result(message=msg)


class TestValidatedTool:
    """Test cases for ValidatedTool."""

    @pytest.mark.asyncio
    async def test_execute_with_valid_parameters(self):
        """Test execution with valid parameters."""
        tool = MockValidatedTool()
        result = await tool.execute(name="Alice", age=30)
        assert result.message == "Hello Alice, age 30"

    @pytest.mark.asyncio
    async def test_execute_with_optional_parameter(self):
        """Test execution with optional parameter."""
        tool = MockValidatedTool()
        result = await tool.execute(name="Bob", age=25, optional="extra")
        assert result.message == "Hello Bob, age 25, extra"

    @pytest.mark.asyncio
    async def test_execute_with_invalid_type(self):
        """Test execution with invalid type raises ValidationError."""
        tool = MockValidatedTool()

        from chuk_tool_processor.core.exceptions import ToolValidationError

        with pytest.raises(ToolValidationError):
            await tool.execute(name="David", age="not_a_number")

    @pytest.mark.asyncio
    async def test_execute_out_of_range(self):
        """Test execution with out of range value."""
        tool = MockValidatedTool()

        from chuk_tool_processor.core.exceptions import ToolValidationError

        with pytest.raises(ToolValidationError):
            await tool.execute(name="Eve", age=150)

    @pytest.mark.asyncio
    async def test_execute_missing_required(self):
        """Test execution with missing required field."""
        tool = MockValidatedTool()

        from chuk_tool_processor.core.exceptions import ToolValidationError

        with pytest.raises(ToolValidationError):
            await tool.execute(age=30)

    def test_to_openai(self):
        """Test OpenAI export format."""
        export = MockValidatedTool.to_openai()

        assert export["type"] == "function"
        assert "function" in export
        assert export["function"]["name"] == "MockValidatedTool"
        assert "description" in export["function"]
        assert "parameters" in export["function"]

    def test_to_openai_with_registry_name(self):
        """Test OpenAI export with custom registry name."""
        export = MockValidatedTool.to_openai(registry_name="custom_tool")

        assert export["function"]["name"] == "custom_tool"

    def test_to_json_schema(self):
        """Test JSON schema export."""
        schema = MockValidatedTool.to_json_schema()

        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]
        assert "optional" in schema["properties"]

    def test_to_xml_tag(self):
        """Test XML tag generation."""
        xml = MockValidatedTool.to_xml_tag(name="Alice", age=30)

        assert "MockValidatedTool" in xml
        assert "Alice" in xml
        assert "30" in xml

    @pytest.mark.asyncio
    async def test_simple_tool(self):
        """Test a simple tool without custom models."""

        class SimpleTool(ValidatedTool):
            class Arguments(BaseModel):
                x: int
                y: int

            class Result(BaseModel):
                sum: int

            async def _execute(self, x: int, y: int) -> Result:
                return self.Result(sum=x + y)

        tool = SimpleTool()
        result = await tool.execute(x=5, y=3)
        assert result.sum == 8

    @pytest.mark.asyncio
    async def test_complex_parameter_types(self):
        """Test with complex parameter types."""

        class ComplexTool(ValidatedTool):
            class Arguments(BaseModel):
                items: list[str] = Field(..., min_length=1)
                mapping: dict[str, int] = Field(default_factory=dict)
                nested: dict[str, Any] = Field(default_factory=dict)

            class Result(BaseModel):
                summary: str

            async def _execute(self, items: list, mapping: dict, nested: dict) -> Result:
                return self.Result(summary=f"Items: {len(items)}, Mapping: {len(mapping)}, Nested: {len(nested)}")

        tool = ComplexTool()

        # Valid complex parameters
        result = await tool.execute(items=["a", "b", "c"], mapping={"x": 1, "y": 2}, nested={"deep": {"value": 42}})
        assert result.summary == "Items: 3, Mapping: 2, Nested: 1"

        # Invalid - empty items list
        from chuk_tool_processor.core.exceptions import ToolValidationError

        with pytest.raises(ToolValidationError):
            await tool.execute(items=[], mapping={})

    def test_inheritance_chain(self):
        """Test that ValidatedTool properly inherits."""
        tool = MockValidatedTool()

        # Should have execute method
        assert hasattr(tool, "execute")
        assert hasattr(tool, "_execute")

        # Should have export methods
        assert hasattr(tool, "to_openai")
        assert hasattr(tool, "to_json_schema")
        assert hasattr(tool, "to_xml_tag")

    @pytest.mark.asyncio
    async def test_result_conversion(self):
        """Test automatic result conversion."""

        class AutoConvertTool(ValidatedTool):
            class Arguments(BaseModel):
                value: int

            class Result(BaseModel):
                value: int

            async def _execute(self, value: int) -> dict:
                # Return dict instead of Result instance
                return {"value": value * 2}

        tool = AutoConvertTool()
        result = await tool.execute(value=5)
        assert isinstance(result, tool.Result)
        assert result.value == 10

    @pytest.mark.asyncio
    async def test_not_implemented_execute(self):
        """Test that base _execute raises NotImplementedError."""

        class EmptyTool(ValidatedTool):
            class Arguments(BaseModel):
                pass

            class Result(BaseModel):
                pass

        tool = EmptyTool()
        with pytest.raises(NotImplementedError, match="Tool must implement async _execute"):
            await tool.execute()

    @pytest.mark.asyncio
    async def test_result_conversion_non_dict_non_result(self):
        """Test result conversion for non-dict, non-Result values."""

        class RawValueTool(ValidatedTool):
            class Arguments(BaseModel):
                x: int

            class Result(BaseModel):
                value: int

            async def _execute(self, x: int):
                # Return raw value instead of Result or dict
                return x * 3

        tool = RawValueTool()
        result = await tool.execute(x=4)
        assert isinstance(result, tool.Result)
        assert result.value == 12


class TestWithValidation:
    """Test cases for with_validation decorator."""

    @pytest.mark.asyncio
    async def test_with_validation_basic(self):
        """Test with_validation decorator on a basic tool."""
        from chuk_tool_processor.models.validated_tool import with_validation

        @with_validation
        class SimpleTool:
            async def execute(self, x: int, y: int) -> int:
                return x + y

        tool = SimpleTool()
        result = await tool.execute(x=5, y=3)
        assert result == 8

    @pytest.mark.asyncio
    async def test_with_validation_invalid_args(self):
        """Test with_validation catches invalid arguments."""
        from chuk_tool_processor.models.validated_tool import with_validation
        from chuk_tool_processor.core.exceptions import ToolValidationError

        @with_validation
        class TypedTool:
            async def execute(self, value: int) -> int:
                return value * 2

        tool = TypedTool()
        with pytest.raises(ToolValidationError):
            await tool.execute(value="not_an_int")

    @pytest.mark.asyncio
    async def test_with_validation_invalid_result(self):
        """Test with_validation catches invalid return values."""
        from chuk_tool_processor.models.validated_tool import with_validation
        from chuk_tool_processor.core.exceptions import ToolValidationError

        @with_validation
        class StrictReturnTool:
            async def execute(self, x: int) -> int:
                return "not_an_int"  # Wrong return type

        tool = StrictReturnTool()
        with pytest.raises(ToolValidationError):
            await tool.execute(x=5)

    def test_with_validation_non_async(self):
        """Test with_validation raises TypeError for non-async execute."""
        from chuk_tool_processor.models.validated_tool import with_validation

        with pytest.raises(TypeError, match="must have an async execute method"):

            @with_validation
            class SyncTool:
                def execute(self, x: int) -> int:
                    return x * 2
