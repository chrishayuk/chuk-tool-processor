#!/usr/bin/env python
# chuk_tool_processor/mcp/setup_mcp_sse.py
"""
Utility that wires up:

1. A :class:`~chuk_tool_processor.mcp.stream_manager.StreamManager`
   using the SSE transport.
2. The remote MCP tools exposed by that manager (via
   :pyfunc:`~chuk_tool_processor.mcp.register_mcp_tools.register_mcp_tools`).
3. A fully-featured :class:`~chuk_tool_processor.core.processor.ToolProcessor`
   instance that can execute those tools – with optional caching,
   rate-limiting, retries, etc.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager

logger = get_logger("chuk_tool_processor.mcp.setup_sse")


# --------------------------------------------------------------------------- #
# public helper
# --------------------------------------------------------------------------- #
async def setup_mcp_sse(  # noqa: C901 – long, but just a config wrapper
    *,
    servers: List[Dict[str, str]],
    server_names: Optional[Dict[int, str]] = None,
    default_timeout: float = 10.0,
    max_concurrency: Optional[int] = None,
    enable_caching: bool = True,
    cache_ttl: int = 300,
    enable_rate_limiting: bool = False,
    global_rate_limit: Optional[int] = None,
    tool_rate_limits: Optional[Dict[str, tuple]] = None,
    enable_retries: bool = True,
    max_retries: int = 3,
    namespace: str = "mcp",
) -> Tuple[ToolProcessor, StreamManager]:
    """
    Spin up an SSE-backed *StreamManager*, register all its remote tools,
    and return a ready-to-go :class:`ToolProcessor`.

    Everything is **async-native** – call with ``await``.
    
    NEW: Automatically detects and adds bearer token from MCP_BEARER_TOKEN
    environment variable if not explicitly provided in server config.
    """
    
    # NEW: Auto-detect and add bearer token to servers if available
    bearer_token = os.getenv("MCP_BEARER_TOKEN")
    if bearer_token:
        logger.info("Found MCP_BEARER_TOKEN environment variable, adding to server configs")
        
        # Add api_key to servers that don't already have it
        enhanced_servers = []
        for server in servers:
            enhanced_server = dict(server)  # Make a copy
            if "api_key" not in enhanced_server and bearer_token:
                enhanced_server["api_key"] = bearer_token
                logger.info("Added bearer token to server: %s", enhanced_server.get("name", "unnamed"))
            enhanced_servers.append(enhanced_server)
        servers = enhanced_servers
    
    # 1️⃣  connect to the remote MCP servers
    stream_manager = await StreamManager.create_with_sse(
        servers=servers,
        server_names=server_names,
    )

    # 2️⃣  introspect & register their tools in the local registry
    registered = await register_mcp_tools(stream_manager, namespace=namespace)

    # 3️⃣  build a processor configured to your liking
    processor = ToolProcessor(
        default_timeout=default_timeout,
        max_concurrency=max_concurrency,
        enable_caching=enable_caching,
        cache_ttl=cache_ttl,
        enable_rate_limiting=enable_rate_limiting,
        global_rate_limit=global_rate_limit,
        tool_rate_limits=tool_rate_limits,
        enable_retries=enable_retries,
        max_retries=max_retries,
    )

    logger.info(
        "MCP (SSE) initialised – %s tool%s registered into namespace '%s'",
        len(registered),
        "" if len(registered) == 1 else "s",
        namespace,
    )
    return processor, stream_manager