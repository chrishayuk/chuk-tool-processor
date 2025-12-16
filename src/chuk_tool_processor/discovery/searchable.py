# chuk_tool_processor/discovery/searchable.py
"""Protocol for searchable tools.

This module defines the interface that tools must implement to be searchable.
Both chuk-tool-processor's ToolMetadata and external ToolInfo classes can
implement this protocol.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SearchableTool(Protocol):
    """Protocol for tools that can be searched.

    Any class with these attributes can be used with the search engine.
    This allows flexibility for different tool representations across
    projects (e.g., ToolInfo, ToolMetadata, etc.)

    Required attributes:
        name: Tool name (e.g., "normal_cdf")
        namespace: Tool namespace (e.g., "math")

    Optional attributes:
        description: Tool description for search matching
        parameters: JSON schema for tool parameters (used for param name matching)
    """

    @property
    def name(self) -> str:
        """Tool name."""
        ...

    @property
    def namespace(self) -> str:
        """Tool namespace."""
        ...

    @property
    def description(self) -> str | None:
        """Tool description (optional, but recommended for search)."""
        ...

    @property
    def parameters(self) -> dict[str, Any] | None:
        """Tool parameters schema (optional, for parameter name matching)."""
        ...


def is_searchable(obj: Any) -> bool:
    """Check if an object implements the SearchableTool protocol.

    Args:
        obj: Object to check

    Returns:
        True if obj has name and namespace attributes
    """
    return hasattr(obj, "name") and hasattr(obj, "namespace")


def get_tool_description(tool: Any) -> str | None:
    """Safely get tool description.

    Args:
        tool: Tool object (may or may not have description)

    Returns:
        Description string or None
    """
    if hasattr(tool, "description"):
        desc = tool.description
        return str(desc) if desc is not None else None
    return None


def get_tool_parameters(tool: Any) -> dict[str, Any] | None:
    """Safely get tool parameters.

    Args:
        tool: Tool object (may or may not have parameters)

    Returns:
        Parameters dict or None
    """
    if hasattr(tool, "parameters"):
        params = tool.parameters
        if isinstance(params, dict):
            return params
    # Also check argument_schema (used in ToolMetadata)
    if hasattr(tool, "argument_schema"):
        schema = tool.argument_schema
        if isinstance(schema, dict):
            return schema
    return None
