# tests/models/test_tool_export_mixin_proper.py
"""Tests for tool export mixin that match actual implementation."""

from __future__ import annotations

from pydantic import BaseModel

from chuk_tool_processor.models.tool_export_mixin import ToolExportMixin


class TestToolExportMixinProper:
    """Test ToolExportMixin with proper structure."""

    def test_to_openai_basic(self):
        """Test basic OpenAI export."""

        class SimpleTestTool(ToolExportMixin):
            """A simple test tool."""

            class Arguments(BaseModel):
                text: str
                count: int = 5

        result = SimpleTestTool.to_openai()

        assert result["type"] == "function"
        assert "function" in result
        assert result["function"]["name"] == "simpletest"  # Removes 'Tool' suffix and lowercases
        assert result["function"]["description"] == "A simple test tool."

        # Check parameters from Arguments schema
        params = result["function"]["parameters"]
        assert "properties" in params
        assert "text" in params["properties"]
        assert "count" in params["properties"]
        assert params["properties"]["count"].get("default") == 5

    def test_to_openai_removes_tool_suffix(self):
        """Test that 'Tool' suffix is removed from name."""

        class MyCustomTool(ToolExportMixin):
            """Custom tool."""

            class Arguments(BaseModel):
                value: str

        result = MyCustomTool.to_openai()
        assert result["function"]["name"] == "mycustom"

        class NoSuffixClass(ToolExportMixin):
            """No Tool suffix."""

            class Arguments(BaseModel):
                pass

        result = NoSuffixClass.to_openai()
        assert result["function"]["name"] == "nosuffixclass"

    def test_to_openai_no_docstring(self):
        """Test export when class has no docstring."""

        class NoDocTool(ToolExportMixin):
            class Arguments(BaseModel):
                pass

        result = NoDocTool.to_openai()
        assert result["function"]["description"] == ""

    def test_to_json_schema(self):
        """Test JSON schema export."""

        class SchemaTool(ToolExportMixin):
            """Tool with schema."""

            class Arguments(BaseModel):
                required_field: str
                optional_field: int = 10
                list_field: list[str] = []

        schema = SchemaTool.to_json_schema()

        assert "properties" in schema
        assert "required_field" in schema["properties"]
        assert "optional_field" in schema["properties"]
        assert "list_field" in schema["properties"]
        assert schema["properties"]["optional_field"].get("default") == 10

    def test_to_xml(self):
        """Test XML export."""

        class XmlTool(ToolExportMixin):
            """XML exportable tool."""

            class Arguments(BaseModel):
                arg1: str
                arg2: int
                arg3: bool = True

        xml = XmlTool.to_xml()

        assert '<tool name="xml"' in xml
        assert "args=" in xml
        assert "arg1" in xml
        assert "arg2" in xml
        assert "arg3" in xml

    def test_complex_arguments_schema(self):
        """Test export with complex argument types."""

        class ComplexTool(ToolExportMixin):
            """Complex tool."""

            class Arguments(BaseModel):
                nested_dict: dict[str, list[int]]
                optional_list: list[str] | None = None
                enum_field: str = "option1"

        result = ComplexTool.to_openai()
        schema = result["function"]["parameters"]

        assert "nested_dict" in schema["properties"]
        assert "optional_list" in schema["properties"]
        assert "enum_field" in schema["properties"]

        # to_json_schema should return the same schema
        json_schema = ComplexTool.to_json_schema()
        assert json_schema == schema

    def test_empty_arguments(self):
        """Test tool with no arguments."""

        class NoArgsTool(ToolExportMixin):
            """Tool with no arguments."""

            class Arguments(BaseModel):
                pass

        result = NoArgsTool.to_openai()
        schema = result["function"]["parameters"]

        # Should still have properties dict, but empty
        assert "properties" in schema
        assert len(schema["properties"]) == 0

    def test_inheritance_with_mixin(self):
        """Test that mixin works with inheritance."""

        class BaseTool(ToolExportMixin):
            """Base tool."""

            class Arguments(BaseModel):
                base_field: str

        class DerivedTool(BaseTool):
            """Derived tool."""

            class Arguments(BaseModel):
                derived_field: str
                another_field: int = 42

        # Base tool export
        base_result = BaseTool.to_openai()
        assert base_result["function"]["name"] == "base"
        assert "base_field" in base_result["function"]["parameters"]["properties"]

        # Derived tool export - uses its own Arguments
        derived_result = DerivedTool.to_openai()
        assert derived_result["function"]["name"] == "derived"
        assert "derived_field" in derived_result["function"]["parameters"]["properties"]
        assert "another_field" in derived_result["function"]["parameters"]["properties"]
        # Should not have base_field since Arguments was overridden
        assert "base_field" not in derived_result["function"]["parameters"]["properties"]
