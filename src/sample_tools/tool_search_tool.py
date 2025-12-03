# sample_tools/tool_search_tool.py
"""
Tool search system tool for dynamic tool discovery.

This tool enables the advanced tool use pattern where Claude can search
for and activate deferred tools on-demand, breaking the 128 function limit.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import get_default_registry, register_tool


@register_tool(namespace="system", tags=["search", "discovery", "meta"])
class ToolSearchTool(ValidatedTool):
    """
    Search and activate deferred tools on-demand.

    This tool enables dynamic tool binding by searching through deferred
    tools and automatically loading them when they match the query.
    Once loaded, tools become available for use in subsequent API calls.

    Use this when you need a tool that isn't currently available but might
    exist in the deferred tool registry.

    Example:
        If you need to work with CSV data, search for "csv pandas data":
        - Query: "csv pandas data"
        - Returns: pandas_read_csv, csv_parser, data_validator
        - These tools are now loaded and ready to use
    """

    class Arguments(BaseModel):
        """Arguments for tool search."""

        query: str = Field(
            ...,
            description=(
                "Natural language query describing the tools you need. "
                "Examples: 'postgres database query', 'pandas csv data', 'image processing'"
            ),
        )
        tags: list[str] | None = Field(
            None,
            description=("Optional list of tags to filter by. Examples: ['database', 'sql'], ['data', 'analysis']"),
        )
        max_results: int = Field(
            5,
            ge=1,
            le=20,
            description="Maximum number of tools to load (1-20). Default: 5",
        )

    class Result(BaseModel):
        """Results from tool search."""

        tools: list[dict[str, str]] = Field(
            ...,
            description="List of tools that were found and loaded",
        )
        count: int = Field(
            ...,
            description="Number of tools loaded",
        )
        message: str = Field(
            ...,
            description="Human-readable message about what was loaded",
        )

    async def _execute(
        self,
        query: str,
        tags: list[str] | None = None,
        max_results: int = 5,
    ) -> dict:
        """
        Search for and load deferred tools.

        Args:
            query: Natural language search query
            tags: Optional tags to filter by
            max_results: Maximum number of tools to load

        Returns:
            Dict with tools, count, and message
        """
        registry = await get_default_registry()

        # Search deferred tools
        matches = await registry.search_deferred_tools(
            query=query,
            tags=tags,
            limit=max_results,
        )

        if not matches:
            return {
                "tools": [],
                "count": 0,
                "message": f"No deferred tools found matching '{query}'",
            }

        # Load each matched tool
        loaded_tools = []
        for metadata in matches:
            try:
                # Load the tool (moves it from deferred to active)
                await registry.load_deferred_tool(metadata.name, metadata.namespace)

                # Build tool info
                tool_info = {
                    "name": metadata.name,
                    "namespace": metadata.namespace,
                    "description": metadata.description or "No description",
                    "full_name": f"{metadata.namespace}.{metadata.name}",
                }

                # Add example if available
                if hasattr(metadata, "examples") and metadata.execution_options.get("examples"):
                    tool_info["example"] = metadata.execution_options["examples"][0]

                loaded_tools.append(tool_info)

            except Exception as e:
                # Log error but continue with other tools
                print(f"Warning: Failed to load {metadata.namespace}.{metadata.name}: {e}")
                continue

        if not loaded_tools:
            return {
                "tools": [],
                "count": 0,
                "message": f"Found {len(matches)} matching tools but failed to load them",
            }

        # Build success message
        tool_names = [t["full_name"] for t in loaded_tools]
        message = (
            f"Successfully loaded {len(loaded_tools)} tool(s): {', '.join(tool_names)}. "
            f"These tools are now available for use."
        )

        return {
            "tools": loaded_tools,
            "count": len(loaded_tools),
            "message": message,
        }
