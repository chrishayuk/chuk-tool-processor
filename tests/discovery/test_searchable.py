# tests/discovery/test_searchable.py
"""Tests for the SearchableTool protocol and helper functions."""

from dataclasses import dataclass
from typing import Any

from chuk_tool_processor.discovery.searchable import (
    SearchableTool,
    get_tool_description,
    get_tool_parameters,
    is_searchable,
)

# ============================================================================
# Test Models
# ============================================================================


@dataclass
class FullTool:
    """Tool with all SearchableTool attributes."""

    name: str
    namespace: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


@dataclass
class MinimalTool:
    """Tool with only required attributes."""

    name: str
    namespace: str


@dataclass
class ToolWithArgumentSchema:
    """Tool with argument_schema instead of parameters."""

    name: str
    namespace: str
    argument_schema: dict[str, Any] | None = None


class NotATool:
    """Object that is not a tool."""

    def __init__(self):
        self.foo = "bar"


# ============================================================================
# is_searchable Tests
# ============================================================================


class TestIsSearchable:
    """Tests for is_searchable function."""

    def test_full_tool_is_searchable(self):
        """Test that a full tool is searchable."""
        tool = FullTool(name="test", namespace="ns", description="Test")
        assert is_searchable(tool) is True

    def test_minimal_tool_is_searchable(self):
        """Test that minimal tool with just name/namespace is searchable."""
        tool = MinimalTool(name="test", namespace="ns")
        assert is_searchable(tool) is True

    def test_dict_is_not_searchable(self):
        """Test that a plain dict is not searchable."""
        obj = {"name": "test", "namespace": "ns"}
        # dicts have keys but not attributes
        assert is_searchable(obj) is False

    def test_object_without_name_is_not_searchable(self):
        """Test that object without name attribute is not searchable."""
        obj = NotATool()
        assert is_searchable(obj) is False

    def test_none_is_not_searchable(self):
        """Test that None is not searchable."""
        assert is_searchable(None) is False


# ============================================================================
# get_tool_description Tests
# ============================================================================


class TestGetToolDescription:
    """Tests for get_tool_description function."""

    def test_returns_description_string(self):
        """Test getting description from tool with string description."""
        tool = FullTool(name="test", namespace="ns", description="A test tool")
        assert get_tool_description(tool) == "A test tool"

    def test_returns_none_for_none_description(self):
        """Test getting None when description is None."""
        tool = FullTool(name="test", namespace="ns", description=None)
        assert get_tool_description(tool) is None

    def test_returns_none_for_missing_description(self):
        """Test getting None when tool has no description attribute."""
        tool = MinimalTool(name="test", namespace="ns")
        assert get_tool_description(tool) is None

    def test_converts_non_string_to_string(self):
        """Test that non-string descriptions are converted."""

        @dataclass
        class ToolWithIntDesc:
            name: str
            namespace: str
            description: int

        tool = ToolWithIntDesc(name="test", namespace="ns", description=42)
        assert get_tool_description(tool) == "42"

    def test_empty_string_description(self):
        """Test that empty string is returned as-is."""
        tool = FullTool(name="test", namespace="ns", description="")
        assert get_tool_description(tool) == ""


# ============================================================================
# get_tool_parameters Tests
# ============================================================================


class TestGetToolParameters:
    """Tests for get_tool_parameters function."""

    def test_returns_parameters_dict(self):
        """Test getting parameters from tool with parameters."""
        params = {"type": "object", "properties": {"x": {"type": "number"}}}
        tool = FullTool(name="test", namespace="ns", parameters=params)
        assert get_tool_parameters(tool) == params

    def test_returns_none_for_none_parameters(self):
        """Test getting None when parameters is None."""
        tool = FullTool(name="test", namespace="ns", parameters=None)
        assert get_tool_parameters(tool) is None

    def test_returns_none_for_missing_parameters(self):
        """Test getting None when tool has no parameters attribute."""
        tool = MinimalTool(name="test", namespace="ns")
        assert get_tool_parameters(tool) is None

    def test_returns_argument_schema_as_fallback(self):
        """Test that argument_schema is used when parameters is missing."""
        schema = {"type": "object", "properties": {"y": {"type": "string"}}}
        tool = ToolWithArgumentSchema(name="test", namespace="ns", argument_schema=schema)
        assert get_tool_parameters(tool) == schema

    def test_returns_none_for_non_dict_parameters(self):
        """Test that non-dict parameters return None."""

        @dataclass
        class ToolWithBadParams:
            name: str
            namespace: str
            parameters: str

        tool = ToolWithBadParams(name="test", namespace="ns", parameters="not a dict")
        assert get_tool_parameters(tool) is None

    def test_returns_none_for_non_dict_argument_schema(self):
        """Test that non-dict argument_schema returns None."""

        @dataclass
        class ToolWithBadSchema:
            name: str
            namespace: str
            argument_schema: list

        tool = ToolWithBadSchema(name="test", namespace="ns", argument_schema=[1, 2, 3])
        assert get_tool_parameters(tool) is None


# ============================================================================
# SearchableTool Protocol Tests
# ============================================================================


class TestSearchableToolProtocol:
    """Tests for SearchableTool protocol compliance."""

    def test_full_tool_implements_protocol(self):
        """Test that FullTool implements SearchableTool."""
        tool = FullTool(name="test", namespace="ns", description="Test")
        assert isinstance(tool, SearchableTool)

    def test_minimal_tool_does_not_implement_protocol(self):
        """Test that MinimalTool does not implement full SearchableTool protocol.

        The protocol requires description and parameters properties,
        which MinimalTool doesn't have.
        """
        tool = MinimalTool(name="test", namespace="ns")
        # MinimalTool only has name and namespace, not description/parameters
        # So it doesn't fully implement the protocol
        assert not isinstance(tool, SearchableTool)

    def test_not_a_tool_does_not_implement(self):
        """Test that NotATool does not implement SearchableTool."""
        obj = NotATool()
        assert not isinstance(obj, SearchableTool)
