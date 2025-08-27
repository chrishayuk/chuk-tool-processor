#!/usr/bin/env python
# chuk_tool_processor/mcp/register_mcp_tools.py
"""
Discover the remote MCP tools exposed by a StreamManager and register them locally.

CLEAN & SIMPLE: Just the essentials - create MCPTool wrappers for remote tools.
"""

from __future__ import annotations

from typing import Any

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.mcp_tool import MCPTool, RecoveryConfig
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("chuk_tool_processor.mcp.register")


async def register_mcp_tools(
    stream_manager: StreamManager,
    namespace: str = "mcp",
    *,
    # Optional resilience configuration
    default_timeout: float = 30.0,
    enable_resilience: bool = True,
    recovery_config: RecoveryConfig | None = None,
) -> list[str]:
    """
    Pull the remote tool catalogue and create local MCPTool wrappers.

    Parameters
    ----------
    stream_manager
        An initialised StreamManager.
    namespace
        Tools are registered under their original name in the specified namespace.
    default_timeout
        Default timeout for tool execution
    enable_resilience
        Whether to enable resilience features (circuit breaker, retries)
    recovery_config
        Optional custom recovery configuration

    Returns
    -------
    list[str]
        The tool names that were registered.
    """
    registry = await ToolRegistryProvider.get_registry()
    registered: list[str] = []

    # Get the remote tool catalogue
    mcp_tools: list[dict[str, Any]] = stream_manager.get_all_tools()

    for tool_def in mcp_tools:
        tool_name = tool_def.get("name")
        if not tool_name:
            logger.warning("Remote tool definition without a 'name' field - skipped")
            continue

        description = tool_def.get("description") or f"MCP tool • {tool_name}"
        meta: dict[str, Any] = {
            "description": description,
            "is_async": True,
            "tags": {"mcp", "remote"},
            "argument_schema": tool_def.get("inputSchema", {}),
        }

        try:
            # Create MCPTool wrapper with optional resilience configuration
            wrapper = MCPTool(
                tool_name=tool_name,
                stream_manager=stream_manager,
                default_timeout=default_timeout,
                enable_resilience=enable_resilience,
                recovery_config=recovery_config,
            )

            await registry.register_tool(
                wrapper,
                name=tool_name,
                namespace=namespace,
                metadata=meta,
            )

            registered.append(tool_name)
            logger.debug(
                "MCP tool '%s' registered as '%s:%s'",
                tool_name,
                namespace,
                tool_name,
            )
        except Exception as exc:
            logger.error("Failed to register MCP tool '%s': %s", tool_name, exc)

    logger.debug("MCP registration complete - %d tool(s) available", len(registered))
    return registered


async def update_mcp_tools_stream_manager(
    namespace: str,
    new_stream_manager: StreamManager | None,
) -> int:
    """
    Update the StreamManager reference for all MCP tools in a namespace.

    Useful for reconnecting tools after StreamManager recovery at the service level.

    Parameters
    ----------
    namespace
        The namespace containing MCP tools to update
    new_stream_manager
        The new StreamManager to use, or None to disconnect

    Returns
    -------
    int
        Number of tools updated
    """
    registry = await ToolRegistryProvider.get_registry()
    updated_count = 0

    try:
        # List all tools in the namespace
        all_tools = await registry.list_tools()
        namespace_tools = [name for ns, name in all_tools if ns == namespace]

        for tool_name in namespace_tools:
            try:
                tool = await registry.get_tool(tool_name, namespace)
                if tool and hasattr(tool, "set_stream_manager"):
                    tool.set_stream_manager(new_stream_manager)
                    updated_count += 1
                    logger.debug("Updated StreamManager for tool '%s:%s'", namespace, tool_name)
            except Exception as e:
                logger.warning("Failed to update StreamManager for tool '%s:%s': %s", namespace, tool_name, e)

        action = "connected" if new_stream_manager else "disconnected"
        logger.debug("StreamManager %s for %d tools in namespace '%s'", action, updated_count, namespace)

    except Exception as e:
        logger.error("Failed to update tools in namespace '%s': %s", namespace, e)

    return updated_count
