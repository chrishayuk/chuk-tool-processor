#!/usr/bin/env python
# chuk_tool_processor/mcp/register_mcp_tools.py
"""
Discover the remote MCP tools exposed by a :class:`~chuk_tool_processor.mcp.stream_manager.StreamManager`
instance and register them in the local CHUK registry.

The helper is now **async-native** – call it with ``await``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry.provider import ToolRegistryProvider

logger = get_logger("chuk_tool_processor.mcp.register")


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
async def register_mcp_tools(
    stream_manager: StreamManager,
    namespace: str = "mcp",
) -> List[str]:
    """
    Pull the *remote* tool catalogue from *stream_manager* and create a local
    async wrapper (:class:`MCPTool`) for each entry.

    Parameters
    ----------
    stream_manager
        An **initialised** :class:`~chuk_tool_processor.mcp.stream_manager.StreamManager`.
    namespace
        All tools are registered twice:

        * under their original name in *namespace* (e.g. ``"mcp.echo"``), and
        * mirrored into the ``"default"`` namespace as ``"{namespace}.{name}"``
          so that parsers may reference them unambiguously.

    Returns
    -------
    list[str]
        The *plain* tool names that were registered (duplicates are ignored).
    """
    registry = await ToolRegistryProvider.get_registry()
    registered: List[str] = []

    # 1️⃣  ask the stream-manager for its catalogue
    mcp_tools: List[Dict[str, Any]] = stream_manager.get_all_tools()

    for tool_def in mcp_tools:
        tool_name = tool_def.get("name")
        if not tool_name:
            logger.warning("Remote tool definition without a 'name' field – skipped")
            continue

        description = tool_def.get("description") or f"MCP tool • {tool_name}"
        meta: Dict[str, Any] = {
            "description": description,
            "is_async": True,
            "tags": {"mcp", "remote"},
            "argument_schema": tool_def.get("inputSchema", {}),
        }

        try:
            wrapper = MCPTool(tool_name, stream_manager)

            # ── primary registration ──────────────────────────────────────
            await registry.register_tool(
                wrapper,
                name=tool_name,
                namespace=namespace,
                metadata=meta,
            )

            # ── mirror into "default" namespace with dotted name ──────────
            dotted_name = f"{namespace}.{tool_name}"
            await registry.register_tool(
                wrapper,
                name=dotted_name,
                namespace="default",
                metadata={**meta, "tags": meta["tags"] | {"namespaced"}},
            )

            registered.append(tool_name)
            logger.debug(
                "MCP tool '%s' registered (as '%s' & '%s')",
                tool_name,
                f"{namespace}:{tool_name}",
                f"default:{dotted_name}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to register MCP tool '%s': %s", tool_name, exc)

    logger.info("MCP registration complete – %d tool(s) available", len(registered))
    return registered
