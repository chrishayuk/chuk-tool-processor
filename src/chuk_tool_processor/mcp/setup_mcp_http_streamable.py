#!/usr/bin/env python
# chuk_tool_processor/mcp/setup_mcp_http_streamable.py
"""
Bootstrap helper for MCP over **HTTP Streamable** transport.

The HTTP Streamable transport is the modern replacement for SSE transport
as of MCP spec 2025-03-26, providing better infrastructure compatibility
and more flexible response handling.

It:

1. spins up :class:`~chuk_tool_processor.mcp.stream_manager.StreamManager`
   with the `"http_streamable"` transport,
2. discovers & registers the remote MCP tools locally, and
3. returns a ready-to-use :class:`~chuk_tool_processor.core.processor.ToolProcessor`.
"""

from __future__ import annotations

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager

logger = get_logger("chuk_tool_processor.mcp.setup_http_streamable")


# --------------------------------------------------------------------------- #
# public helper
# --------------------------------------------------------------------------- #
async def setup_mcp_http_streamable(
    *,
    servers: list[dict[str, str]],
    server_names: dict[int, str] | None = None,
    connection_timeout: float = 30.0,
    default_timeout: float = 30.0,
    max_concurrency: int | None = None,
    enable_caching: bool = True,
    cache_ttl: int = 300,
    enable_rate_limiting: bool = False,
    global_rate_limit: int | None = None,
    tool_rate_limits: dict[str, tuple] | None = None,
    enable_retries: bool = True,
    max_retries: int = 3,
    namespace: str = "http",
) -> tuple[ToolProcessor, StreamManager]:
    """
    Initialize HTTP Streamable transport MCP + a :class:`ToolProcessor`.

    This uses the modern HTTP Streamable transport (spec 2025-03-26) which
    provides better infrastructure compatibility and more flexible response
    handling compared to the deprecated SSE transport.

    Call with ``await`` from your async context.

    Args:
        servers: List of server configurations with 'name', 'url', and optionally 'api_key' keys
        server_names: Optional mapping of server indices to names
        connection_timeout: Timeout for initial HTTP connection setup
        default_timeout: Default timeout for tool execution
        max_concurrency: Maximum concurrent operations
        enable_caching: Whether to enable response caching
        cache_ttl: Cache time-to-live in seconds
        enable_rate_limiting: Whether to enable rate limiting
        global_rate_limit: Global rate limit (requests per minute)
        tool_rate_limits: Per-tool rate limits
        enable_retries: Whether to enable automatic retries
        max_retries: Maximum retry attempts
        namespace: Namespace for registered tools

    Returns:
        Tuple of (ToolProcessor, StreamManager)

    Example:
        >>> servers = [
        ...     {
        ...         "name": "my_server",
        ...         "url": "http://localhost:8000",
        ...         "api_key": "optional-api-key"
        ...     }
        ... ]
        >>> processor, stream_manager = await setup_mcp_http_streamable(
        ...     servers=servers,
        ...     namespace="mytools"
        ... )
    """
    # 1️⃣  create & connect the stream-manager with HTTP Streamable transport
    stream_manager = await StreamManager.create_with_http_streamable(
        servers=servers,
        server_names=server_names,
        connection_timeout=connection_timeout,
        default_timeout=default_timeout,
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

    logger.debug(
        "MCP (HTTP Streamable) initialised - %d tool%s registered into namespace '%s'",
        len(registered),
        "" if len(registered) == 1 else "s",
        namespace,
    )
    return processor, stream_manager
