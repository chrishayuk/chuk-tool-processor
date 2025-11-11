# chuk_tool_processor/registry/tool_export.py
"""
Async helpers that expose all registered tools in various formats and
translate an OpenAI `function.name` back to the matching tool.
"""

from __future__ import annotations

import asyncio
from typing import Any

# registry
from .provider import ToolRegistryProvider

# --------------------------------------------------------------------------- #
# internal cache so tool-name lookup is O(1) with async protection
# --------------------------------------------------------------------------- #
_OPENAI_NAME_CACHE: dict[str, Any] | None = None
_CACHE_LOCK = asyncio.Lock()


async def _build_openai_name_cache() -> None:
    """
    Populate the global reverse-lookup table once asynchronously.

    This function is thread-safe and will only build the cache once,
    even with concurrent calls.
    """
    global _OPENAI_NAME_CACHE

    # Build the cache with proper locking
    async with _CACHE_LOCK:
        if _OPENAI_NAME_CACHE is not None:
            return

        # Initialize an empty cache
        _OPENAI_NAME_CACHE = {}

        # Get the registry
        reg = await ToolRegistryProvider.get_registry()

        # Get all tools and their names
        tools_list = await reg.list_tools()

        for tool_info in tools_list:
            # Get the tool
            tool = await reg.get_tool(tool_info.name, tool_info.namespace)
            if tool is None:
                continue

            # ▸ registry key -> tool
            _OPENAI_NAME_CACHE[tool_info.name] = tool

            # ▸ class name -> tool (legacy)
            _OPENAI_NAME_CACHE[tool.__class__.__name__] = tool

            # ▸ OpenAI name -> tool (may differ from both above)
            try:
                openai_spec = tool.to_openai()
                openai_name = openai_spec["function"]["name"]
                _OPENAI_NAME_CACHE[openai_name] = tool
            except (AttributeError, KeyError, TypeError):
                # Skip tools that don't have proper OpenAI specs
                pass


# --------------------------------------------------------------------------- #
# public helpers
# --------------------------------------------------------------------------- #
async def openai_functions() -> list[dict]:
    """
    Return **all** registered tools in the exact schema the Chat-Completions
    API expects in its ``tools=[ … ]`` parameter.

    The ``function.name`` is always the *registry key* so that the round-trip
    (export → model → parser) stays consistent even when the class name and
    the registered key differ.

    Returns:
        List of OpenAI function specifications
    """
    # Get the registry
    reg = await ToolRegistryProvider.get_registry()
    specs: list[dict[str, Any]] = []

    # List all tools
    tools_list = await reg.list_tools()

    for tool_info in tools_list:
        # Get each tool
        tool = await reg.get_tool(tool_info.name, tool_info.namespace)
        if tool is None:
            continue

        try:
            # Get the OpenAI spec
            spec = tool.to_openai()
            # Override the name to ensure round-trip consistency
            spec["function"]["name"] = tool_info.name
            specs.append(spec)
        except (AttributeError, TypeError):
            # Skip tools that don't support OpenAI format
            pass

    # Ensure the cache is built
    await _build_openai_name_cache()
    return specs


async def tool_by_openai_name(name: str) -> Any:
    """
    Map an OpenAI ``function.name`` back to the registered tool asynchronously.

    Args:
        name: The OpenAI function name

    Returns:
        The tool implementation

    Raises:
        KeyError: If the name is unknown
    """
    # Ensure the cache is built
    await _build_openai_name_cache()

    # Look up the tool
    try:
        if _OPENAI_NAME_CACHE is None:
            raise KeyError("Tool cache not initialized")

        return _OPENAI_NAME_CACHE[name]
    except (KeyError, TypeError):
        raise KeyError(f"No tool registered for OpenAI name {name!r}") from None


async def clear_name_cache() -> None:
    """
    Clear the OpenAI name cache.

    This is useful in tests or when the registry changes significantly.
    """
    global _OPENAI_NAME_CACHE
    async with _CACHE_LOCK:
        _OPENAI_NAME_CACHE = None


async def export_tools_as_openapi(
    title: str = "Tool API",
    version: str = "1.0.0",
    description: str = "API for registered tools",
) -> dict[str, Any]:
    """
    Export all registered tools as an OpenAPI specification.

    Args:
        title: API title
        version: API version
        description: API description

    Returns:
        OpenAPI specification as a dictionary
    """
    # Get the registry
    reg = await ToolRegistryProvider.get_registry()

    # Build paths and components
    paths: dict[str, Any] = {}
    schemas: dict[str, Any] = {}

    # List all tools
    tools_list = await reg.list_tools()

    for tool_info in tools_list:
        # Get tool and metadata
        tool = await reg.get_tool(tool_info.name, tool_info.namespace)
        metadata = await reg.get_metadata(tool_info.name, tool_info.namespace)

        if tool is None or metadata is None:
            continue

        # Create path
        path = f"/{tool_info.namespace}/{tool_info.name}"

        # Get schemas from tool if available
        arg_schema = None
        result_schema = None

        if hasattr(tool, "Arguments") and hasattr(tool.Arguments, "model_json_schema"):
            arg_schema = tool.Arguments.model_json_schema()
            schemas[f"{tool_info.name}Args"] = arg_schema

        if hasattr(tool, "Result") and hasattr(tool.Result, "model_json_schema"):
            result_schema = tool.Result.model_json_schema()
            schemas[f"{tool_info.name}Result"] = result_schema

        # Add path
        paths[path] = {
            "post": {
                "summary": metadata.description or f"Execute {tool_info.name}",
                "operationId": f"execute_{tool_info.namespace}_{tool_info.name}",
                "tags": [tool_info.namespace],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{tool_info.name}Args"} if arg_schema else {}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Successful operation",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{tool_info.name}Result"}
                                if result_schema
                                else {}
                            }
                        },
                    },
                    "400": {"description": "Bad request"},
                    "500": {"description": "Internal server error"},
                },
            }
        }

    # Build the OpenAPI spec
    return {
        "openapi": "3.0.0",
        "info": {"title": title, "version": version, "description": description},
        "paths": paths,
        "components": {"schemas": schemas},
    }
