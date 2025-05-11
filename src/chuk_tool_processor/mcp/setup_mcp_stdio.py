#!/usr/bin/env python
# chuk_tool_processor/mcp/setup_mcp_stdio.py
"""
Bootstrap helper for MCP over **stdio** transport.

It:

1. spins up :class:`~chuk_tool_processor.mcp.stream_manager.StreamManager`
   with the `"stdio"` transport,
2. discovers & registers the remote MCP tools locally, and
3. returns a ready-to-use :class:`~chuk_tool_processor.core.processor.ToolProcessor`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager

logger = get_logger("chuk_tool_processor.mcp.setup_stdio")


# --------------------------------------------------------------------------- #
# public helper
# --------------------------------------------------------------------------- #
async def setup_mcp_stdio(  # noqa: C901 – long but just a config facade
    *,
    config_file: str,
    servers: List[str],
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
    Initialise stdio-transport MCP + a :class:`ToolProcessor`.

    Call with ``await`` from your async context.
    """
    # 1️⃣  create & connect the stream-manager
    stream_manager = await StreamManager.create(
        config_file=config_file,
        servers=servers,
        server_names=server_names,
        transport_type="stdio",
    )

    # 2️⃣  pull the remote tool list and register each one locally
    registered = await register_mcp_tools(stream_manager, namespace=namespace)

    # 3️⃣  build a processor instance configured to your taste
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
        "MCP (stdio) initialised – %s tool%s registered into namespace '%s'",
        len(registered),
        "" if len(registered) == 1 else "s",
        namespace,
    )
    return processor, stream_manager
