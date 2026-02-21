# tests/discovery/test_searchable_coverage.py
"""Coverage tests for discovery.searchable module.

Covers abstract protocol method bodies (lines 34, 39, 44, 49),
protocol compliance checks, and the helper functions.
"""

from __future__ import annotations

from typing import Any

from chuk_tool_processor.discovery.searchable import (
    SearchableTool,
    get_tool_description,
    get_tool_parameters,
    is_searchable,
)


# ------------------------------------------------------------------ #
# Concrete implementations for testing
# ------------------------------------------------------------------ #
class FullTool:
    """A tool with all SearchableTool attributes."""

    @property
    def name(self) -> str:
        return "full_tool"

    @property
    def namespace(self) -> str:
        return "testing"

    @property
    def description(self) -> str | None:
        return "A full tool"

    @property
    def parameters(self) -> dict[str, Any] | None:
        return {"type": "object", "properties": {"x": {"type": "integer"}}}


class MinimalTool:
    """A tool with only name and namespace (required attributes)."""

    @property
    def name(self) -> str:
        return "minimal_tool"

    @property
    def namespace(self) -> str:
        return "test"


class ToolWithNoneDescription:
    """A tool where description returns None."""

    @property
    def name(self) -> str:
        return "none_desc"

    @property
    def namespace(self) -> str:
        return "test"

    @property
    def description(self) -> str | None:
        return None


class ToolWithNonDictParams:
    """A tool where parameters is not a dict."""

    @property
    def name(self) -> str:
        return "bad_params"

    @property
    def namespace(self) -> str:
        return "test"

    @property
    def parameters(self) -> Any:
        return "not_a_dict"


class ToolWithArgumentSchema:
    """A tool that uses argument_schema instead of parameters."""

    @property
    def name(self) -> str:
        return "arg_schema"

    @property
    def namespace(self) -> str:
        return "test"

    @property
    def argument_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"q": {"type": "string"}}}


class ToolWithBothSchemas:
    """A tool with non-dict parameters but valid argument_schema."""

    @property
    def name(self) -> str:
        return "both"

    @property
    def namespace(self) -> str:
        return "test"

    @property
    def parameters(self) -> Any:
        return None  # Not a dict

    @property
    def argument_schema(self) -> dict[str, Any]:
        return {"type": "object"}


class NotATool:
    """An object that does NOT implement SearchableTool."""

    pass


# ------------------------------------------------------------------ #
# Protocol compliance
# ------------------------------------------------------------------ #
class TestProtocolCompliance:
    """Verify isinstance checks against SearchableTool protocol."""

    def test_full_tool_is_searchable_protocol(self):
        assert isinstance(FullTool(), SearchableTool)

    def test_minimal_tool_not_full_protocol(self):
        """MinimalTool lacks description/parameters, so runtime_checkable fails."""
        # runtime_checkable checks all protocol members; MinimalTool is missing
        # description and parameters, so isinstance returns False.
        assert not isinstance(MinimalTool(), SearchableTool)

    def test_not_a_tool_is_not_searchable(self):
        assert not isinstance(NotATool(), SearchableTool)

    def test_plain_object_is_not_searchable(self):
        assert not isinstance(object(), SearchableTool)


class TestProtocolAbstractBodies:
    """Exercise the Ellipsis bodies in the Protocol property methods (lines 34, 39, 44, 49).

    Protocol classes can be instantiated directly to call their default
    method bodies. We access the property descriptors from the class
    to invoke the underlying fget functions.
    """

    def test_name_body(self):
        # Access the property fget from the Protocol class and call it directly
        # With `from __future__ import annotations`, the `...` body is an
        # expression statement that evaluates and returns None.
        fget = SearchableTool.__dict__["name"].fget
        result = fget(None)
        assert result is None

    def test_namespace_body(self):
        fget = SearchableTool.__dict__["namespace"].fget
        result = fget(None)
        assert result is None

    def test_description_body(self):
        fget = SearchableTool.__dict__["description"].fget
        result = fget(None)
        assert result is None

    def test_parameters_body(self):
        fget = SearchableTool.__dict__["parameters"].fget
        result = fget(None)
        assert result is None


# ------------------------------------------------------------------ #
# is_searchable helper
# ------------------------------------------------------------------ #
class TestIsSearchable:
    """Tests for is_searchable() function."""

    def test_full_tool(self):
        assert is_searchable(FullTool()) is True

    def test_minimal_tool(self):
        assert is_searchable(MinimalTool()) is True

    def test_not_a_tool(self):
        assert is_searchable(NotATool()) is False

    def test_plain_object(self):
        assert is_searchable(object()) is False

    def test_has_only_name(self):
        class OnlyName:
            name = "foo"

        assert is_searchable(OnlyName()) is False

    def test_has_only_namespace(self):
        class OnlyNamespace:
            namespace = "bar"

        assert is_searchable(OnlyNamespace()) is False


# ------------------------------------------------------------------ #
# get_tool_description helper
# ------------------------------------------------------------------ #
class TestGetToolDescription:
    """Tests for get_tool_description() function."""

    def test_with_description(self):
        assert get_tool_description(FullTool()) == "A full tool"

    def test_with_none_description(self):
        assert get_tool_description(ToolWithNoneDescription()) is None

    def test_without_description_attr(self):
        assert get_tool_description(MinimalTool()) is None

    def test_plain_object(self):
        assert get_tool_description(object()) is None


# ------------------------------------------------------------------ #
# get_tool_parameters helper
# ------------------------------------------------------------------ #
class TestGetToolParameters:
    """Tests for get_tool_parameters() function."""

    def test_with_dict_parameters(self):
        result = get_tool_parameters(FullTool())
        assert isinstance(result, dict)
        assert result["type"] == "object"

    def test_without_parameters_attr(self):
        """MinimalTool has no parameters, no argument_schema -> None."""
        assert get_tool_parameters(MinimalTool()) is None

    def test_non_dict_parameters_falls_through(self):
        """Non-dict parameters should not be returned."""
        assert get_tool_parameters(ToolWithNonDictParams()) is None

    def test_argument_schema_fallback(self):
        """Falls back to argument_schema when parameters is absent."""
        result = get_tool_parameters(ToolWithArgumentSchema())
        assert isinstance(result, dict)
        assert result["type"] == "object"

    def test_non_dict_parameters_uses_argument_schema(self):
        """When parameters is not a dict, falls back to argument_schema."""
        result = get_tool_parameters(ToolWithBothSchemas())
        assert isinstance(result, dict)
        assert result["type"] == "object"

    def test_plain_object(self):
        assert get_tool_parameters(object()) is None
