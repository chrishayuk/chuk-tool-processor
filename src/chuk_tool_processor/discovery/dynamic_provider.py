# chuk_tool_processor/discovery/dynamic_provider.py
"""Base dynamic tool provider for on-demand tool discovery and binding.

This module provides a base class for dynamic tool providers that allow LLMs
to discover and load tool schemas on-demand, rather than loading all tools upfront.

The base provider handles:
- Tool listing and searching
- Schema retrieval with caching
- Name aliasing and resolution

Subclasses can customize:
- Tool execution (call_tool)
- Tool filtering/blocking logic
- State integration
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Generic, TypeVar

from chuk_tool_processor.discovery.search import (
    SearchResult,
    ToolSearchEngine,
    find_tool_by_alias,
)
from chuk_tool_processor.discovery.searchable import (
    get_tool_description,
    get_tool_parameters,
)

logger = logging.getLogger(__name__)


# Type variable for tools
T = TypeVar("T")


def _success_response(result: Any, **extra: Any) -> dict[str, Any]:
    """Create a standardized success response.

    Args:
        result: The result data
        **extra: Additional fields to include

    Returns:
        Dict with success=True and result data
    """
    response: dict[str, Any] = {"success": True, "result": result}
    response.update(extra)
    return response


def _error_response(
    error: str,
    suggestions: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Create a standardized error response.

    Args:
        error: Error message
        suggestions: Optional list of suggested corrections
        **extra: Additional fields to include

    Returns:
        Dict with success=False, error message, and optional suggestions
    """
    response: dict[str, Any] = {"success": False, "error": error}
    if suggestions:
        response["suggestions"] = suggestions
    response.update(extra)
    return response


class DynamicToolName(str, Enum):
    """Names of available dynamic tools - no magic strings!"""

    LIST_TOOLS = "list_tools"
    SEARCH_TOOLS = "search_tools"
    GET_TOOL_SCHEMA = "get_tool_schema"
    GET_TOOL_SCHEMAS = "get_tool_schemas"  # Batch fetch
    CALL_TOOL = "call_tool"


class BaseDynamicToolProvider(ABC, Generic[T]):
    """Base class for dynamic tool providers.

    Provides dynamic tools that allow the LLM to discover and load
    tool schemas on-demand, rather than loading all tools upfront.

    Generic over tool type T - works with any object that has name/namespace.

    ENHANCED: Uses intelligent search engine with:
    - Synonym expansion for natural language queries
    - Tokenized OR semantics (partial matches score)
    - Fuzzy matching fallback for typos
    - Namespace aliasing for flexible tool resolution
    - Always returns results (never empty)
    """

    def __init__(self) -> None:
        """Initialize the provider."""
        self._tool_cache: dict[str, dict[str, Any]] = {}
        self._search_engine: ToolSearchEngine[T] = ToolSearchEngine()
        self._tools_indexed = False
        # Track which tools have had their schema fetched
        self._schema_fetched: set[str] = set()

    # =========================================================================
    # Abstract methods - must be implemented by subclasses
    # =========================================================================

    @abstractmethod
    async def get_all_tools(self) -> list[T]:
        """Get all available tools.

        Returns:
            List of all tools
        """
        ...

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            Execution result dict with 'success' and 'result'/'error' keys
        """
        ...

    # =========================================================================
    # Optional hooks for customization
    # =========================================================================

    def filter_search_results(
        self,
        results: list[SearchResult[T]],
    ) -> list[SearchResult[T]]:
        """Optional hook to filter/modify search results.

        Override this to implement custom filtering logic, such as:
        - Blocking tools that require prerequisites
        - Hiding tools based on state
        - Modifying scores based on context

        Args:
            results: Search results from the engine

        Returns:
            Filtered/modified results
        """
        return results

    def get_tool_name(self, tool: T) -> str:
        """Get tool name from a tool object.

        Override if your tool type has a different attribute.

        Args:
            tool: Tool object

        Returns:
            Tool name
        """
        return getattr(tool, "name", "")

    def get_tool_namespace(self, tool: T) -> str:
        """Get tool namespace from a tool object.

        Override if your tool type has a different attribute.

        Args:
            tool: Tool object

        Returns:
            Tool namespace
        """
        return getattr(tool, "namespace", "")

    # =========================================================================
    # Dynamic tool definitions
    # =========================================================================

    def get_dynamic_tools(self) -> list[dict[str, Any]]:
        """Get the dynamic tool definitions for the LLM.

        Returns:
            List of dynamic tool definitions in OpenAI function format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": DynamicToolName.LIST_TOOLS.value,
                    "description": "List all available tools. Use this to see what tools you can use. Returns tool names and brief descriptions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of tools to return (default: 50)",
                                "default": 50,
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": DynamicToolName.SEARCH_TOOLS.value,
                    "description": "Search for available tools by name or description. Use this to discover what tools are available before using them.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (searches in tool names and descriptions)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return",
                                "default": 10,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": DynamicToolName.GET_TOOL_SCHEMA.value,
                    "description": "Get the full schema for a specific tool. Call this after search_tools to get detailed parameter information before using a tool.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_name": {
                                "type": "string",
                                "description": "Name of the tool to get schema for",
                            },
                        },
                        "required": ["tool_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": DynamicToolName.GET_TOOL_SCHEMAS.value,
                    "description": "Get schemas for multiple tools in a single call. More efficient than calling get_tool_schema multiple times.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of tool names to get schemas for",
                            },
                        },
                        "required": ["tool_names"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": DynamicToolName.CALL_TOOL.value,
                    "description": 'Execute any discovered tool with the specified arguments. First use search_tools or list_tools to find tools, then get_tool_schema to see what parameters are needed, then call_tool to execute it. Pass tool parameters as individual properties (e.g., for tool \'add\' with params \'a\' and \'b\', use: {"tool_name": "add", "a": 1, "b": 2}).',
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_name": {
                                "type": "string",
                                "description": "Name of the tool to execute",
                            },
                        },
                        "required": ["tool_name"],
                        "additionalProperties": True,
                    },
                },
            },
        ]

    # =========================================================================
    # Core operations
    # =========================================================================

    async def list_tools(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all available tools with brief descriptions.

        Args:
            limit: Maximum number of tools to return

        Returns:
            List of tools with name and brief description
        """
        try:
            all_tools = await self.get_all_tools()
            limited_tools = all_tools[:limit]

            results = []
            for tool in limited_tools:
                desc = get_tool_description(tool) or "No description"
                if len(desc) > 200:
                    desc = desc[:197] + "..."

                results.append(
                    {
                        "name": self.get_tool_name(tool),
                        "description": desc,
                        "namespace": self.get_tool_namespace(tool),
                    }
                )

            logger.info(f"list_tools() returned {len(results)} tools (total available: {len(all_tools)})")
            return results

        except Exception as e:
            logger.error(f"Error in list_tools: {e}")
            return []

    async def _ensure_tools_indexed(self) -> None:
        """Ensure tools are indexed for efficient searching."""
        if not self._tools_indexed:
            all_tools = await self.get_all_tools()
            self._search_engine.set_tools(all_tools)
            self._tools_indexed = True
            logger.info(f"Indexed {len(all_tools)} tools for search")

    async def search_tools(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for tools matching the query.

        ENHANCED: Uses intelligent search with:
        - Tokenized OR semantics (any keyword match scores)
        - Synonym expansion ("gaussian" finds "normal", "cdf" finds "cumulative")
        - Fuzzy matching fallback for typos and close matches
        - Always returns results (fallback to popular/short-named tools)

        Args:
            query: Search query string (natural language or keywords)
            limit: Maximum number of results

        Returns:
            List of matching tools with name, description, namespace, and score
        """
        try:
            all_tools = await self.get_all_tools()

            # Update search index if tools changed
            if not self._tools_indexed or len(all_tools) != len(self._search_engine._tool_cache or []):
                self._search_engine.set_tools(all_tools)
                self._tools_indexed = True

            # Use intelligent search engine
            search_results = self._search_engine.search(
                query=query,
                tools=all_tools,
                limit=limit * 2,  # Fetch extra to allow filtering
            )

            # Apply custom filtering
            search_results = self.filter_search_results(search_results)

            # Convert to dict format
            results = []
            for sr in search_results[:limit]:
                desc = get_tool_description(sr.tool) or "No description"
                if len(desc) > 200:
                    desc = desc[:197] + "..."

                results.append(
                    {
                        "name": self.get_tool_name(sr.tool),
                        "description": desc,
                        "namespace": self.get_tool_namespace(sr.tool),
                        "score": sr.score,
                        "match_reasons": sr.match_reasons,
                    }
                )

            logger.info(
                f"search_tools('{query}') found {len(results)} matches "
                f"(top score: {results[0]['score'] if results else 0})"
            )
            return results

        except Exception as e:
            logger.error(f"Error in search_tools: {e}")
            return []

    async def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        """Get full schema for a specific tool.

        ENHANCED: Supports namespace aliasing and normalized name variants.

        Args:
            tool_name: Name of the tool (exact, with namespace, or variant)

        Returns:
            Full tool schema in OpenAI function format
        """
        try:
            # Check cache first
            if tool_name in self._tool_cache:
                logger.debug(f"Returning cached schema for {tool_name}")
                return self._tool_cache[tool_name]

            all_tools = await self.get_all_tools()

            # Try exact match first
            tool = None
            for t in all_tools:
                if self.get_tool_name(t) == tool_name:
                    tool = t
                    break

            # If not found, try alias resolution
            if tool is None:
                tool = find_tool_by_alias(tool_name, all_tools)
                if tool:
                    logger.info(f"Resolved '{tool_name}' to '{self.get_tool_name(tool)}' via alias")

            if tool:
                actual_name = self.get_tool_name(tool)
                desc = get_tool_description(tool) or "No description provided"
                params = get_tool_parameters(tool) or {
                    "type": "object",
                    "properties": {},
                }

                schema = {
                    "type": "function",
                    "function": {
                        "name": actual_name,
                        "description": desc,
                        "parameters": params,
                    },
                }

                # Cache it under both names
                self._tool_cache[tool_name] = schema
                if actual_name != tool_name:
                    self._tool_cache[actual_name] = schema

                # Mark this tool as having its schema fetched
                self._schema_fetched.add(actual_name)
                self._schema_fetched.add(tool_name)
                # Also add without namespace prefix
                base_name = actual_name.split(".")[-1] if "." in actual_name else actual_name
                self._schema_fetched.add(base_name)

                logger.info(f"get_tool_schema('{tool_name}') returned {len(json.dumps(schema))} chars")
                return schema

            # Not found - try to suggest similar tools
            similar = self._search_engine.search(tool_name, all_tools, limit=3)
            suggestions = [self.get_tool_name(s.tool) for s in similar if s.score > 0]

            error_msg = f"Tool '{tool_name}' not found"
            if suggestions:
                error_msg += f". Did you mean: {', '.join(suggestions)}?"

            logger.warning(error_msg)
            return _error_response(error_msg, suggestions=suggestions)

        except Exception as e:
            logger.error(f"Error in get_tool_schema: {e}")
            return _error_response(str(e))

    async def get_tool_schemas(self, tool_names: list[str]) -> dict[str, Any]:
        """Get schemas for multiple tools in a single call.

        More efficient than calling get_tool_schema multiple times when you
        need schemas for several tools (e.g., after a search).

        Args:
            tool_names: List of tool names to get schemas for

        Returns:
            Dict with success=True/False, 'schemas' (list), 'errors' (list),
            and 'count' (number of successful schemas)
        """
        schemas: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for name in tool_names:
            schema = await self.get_tool_schema(name)
            # Check for error using the unified format (success=False)
            if schema.get("success") is False or "error" in schema:
                error_msg = schema.get("error", "Unknown error")
                errors.append({"tool_name": name, "error": error_msg})
            else:
                schemas.append(schema)

        logger.info(f"get_tool_schemas() returned {len(schemas)} schemas, {len(errors)} errors")

        return {
            "success": len(errors) == 0,
            "schemas": schemas,
            "errors": errors,
            "count": len(schemas),
        }

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with given arguments.

        ENHANCED: Supports namespace aliasing for tool resolution.
        If exact name not found, tries alias variants.

        IMPLICIT SCHEMA WARMUP: If schema hasn't been fetched yet, it's
        automatically fetched before execution.

        Args:
            tool_name: Name of the tool to execute (exact or alias)
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result
        """
        try:
            # Auto-fetch schema if not already known (implicit warmup)
            base_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
            schema_known = tool_name in self._schema_fetched or base_name in self._schema_fetched

            if not schema_known:
                logger.info(f"Auto-fetching schema for '{tool_name}' before execution")
                schema_result = await self.get_tool_schema(tool_name)
                if schema_result.get("success") is False or "error" in schema_result:
                    return _error_response(
                        f"Tool '{tool_name}' not found. Use search_tools to discover available tools."
                    )

            # Resolve tool name via alias if needed
            resolved_name = tool_name
            all_tools = await self.get_all_tools()

            # Check if exact name exists
            exact_match = any(self.get_tool_name(t) == tool_name for t in all_tools)

            if not exact_match:
                resolved_tool = find_tool_by_alias(tool_name, all_tools)
                if resolved_tool:
                    resolved_name = self.get_tool_name(resolved_tool)
                    logger.info(f"Resolved tool '{tool_name}' to '{resolved_name}' via alias")

            # Delegate to subclass implementation
            return await self.execute_tool(resolved_name, arguments)

        except Exception as e:
            logger.error(f"Error in call_tool('{tool_name}'): {e}", exc_info=True)
            return _error_response(str(e))

    async def execute_dynamic_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a dynamic tool.

        Args:
            tool_name: Name of the dynamic tool
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if tool_name == DynamicToolName.LIST_TOOLS.value:
            limit = arguments.get("limit", 50)
            results = await self.list_tools(limit)
            return _success_response(
                results,
                count=len(results),
                total_available=len(await self.get_all_tools()),
            )

        elif tool_name == DynamicToolName.SEARCH_TOOLS.value:
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            results = await self.search_tools(query, limit)
            return _success_response(results, count=len(results))

        elif tool_name == DynamicToolName.GET_TOOL_SCHEMA.value:
            tool_name_arg = arguments.get("tool_name", "")
            schema = await self.get_tool_schema(tool_name_arg)
            return schema

        elif tool_name == DynamicToolName.GET_TOOL_SCHEMAS.value:
            tool_names_arg = arguments.get("tool_names", [])
            return await self.get_tool_schemas(tool_names_arg)

        elif tool_name == DynamicToolName.CALL_TOOL.value:
            tool_name_arg = arguments.get("tool_name", "")
            tool_arguments = {k: v for k, v in arguments.items() if k != "tool_name"}
            result = await self.call_tool(tool_name_arg, tool_arguments)
            return result

        else:
            return _error_response(f"Unknown dynamic tool: {tool_name}")

    def is_dynamic_tool(self, tool_name: str) -> bool:
        """Check if a tool name is a dynamic tool.

        Args:
            tool_name: Tool name to check

        Returns:
            True if it's a dynamic tool
        """
        return tool_name in {m.value for m in DynamicToolName}

    def invalidate_cache(self) -> None:
        """Invalidate the tool cache and search index.

        Call this when tools may have changed.
        """
        self._tool_cache.clear()
        self._tools_indexed = False
        self._schema_fetched.clear()
        logger.debug("Tool cache invalidated")
