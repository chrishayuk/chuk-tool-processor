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
    initialization_timeout: float = 60.0,
    max_concurrency: int | None = None,
    enable_caching: bool = True,
    cache_ttl: int = 300,
    enable_rate_limiting: bool = False,
    global_rate_limit: int | None = None,
    tool_rate_limits: dict[str, tuple] | None = None,
    enable_retries: bool = True,  # CHANGED: Enabled with OAuth errors excluded
    max_retries: int = 2,  # Retry non-OAuth errors (OAuth handled at transport level)
    namespace: str = "http",
    oauth_refresh_callback: any | None = None,  # NEW: OAuth token refresh callback
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
        initialization_timeout: Timeout for complete initialization (default 60s, increase to 120s+ for slow servers like Notion)
        max_concurrency: Maximum concurrent operations
        enable_caching: Whether to enable response caching
        cache_ttl: Cache time-to-live in seconds
        enable_rate_limiting: Whether to enable rate limiting
        global_rate_limit: Global rate limit (requests per minute)
        tool_rate_limits: Per-tool rate limits
        enable_retries: Whether to enable automatic retries
        max_retries: Maximum retry attempts
        namespace: Namespace for registered tools
        oauth_refresh_callback: Optional async callback to refresh OAuth tokens (NEW)

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
        initialization_timeout=initialization_timeout,
        oauth_refresh_callback=oauth_refresh_callback,  # NEW: Pass OAuth callback
    )

    # 2️⃣  pull the remote tool list and register each one locally
    registered = await register_mcp_tools(stream_manager, namespace=namespace)

    # 3️⃣  build a processor instance configured to your taste
    # IMPORTANT: Retries are enabled but OAuth errors are excluded
    # OAuth refresh happens at transport level with automatic retry

    # Import RetryConfig to configure OAuth error exclusion
    from chuk_tool_processor.execution.wrappers.retry import RetryConfig

    # Define OAuth error patterns that should NOT be retried at this level
    # These will be handled by the transport layer's OAuth refresh mechanism
    # Based on RFC 6750 (Bearer Token Usage) and MCP OAuth spec
    oauth_error_patterns = [
        # RFC 6750 Section 3.1 - Standard Bearer token errors
        "invalid_token",  # Token expired, revoked, malformed, or invalid
        "insufficient_scope",  # Request requires higher privileges (403 Forbidden)
        # OAuth 2.1 token refresh errors
        "invalid_grant",  # Refresh token errors
        # MCP spec - OAuth validation failures (401 Unauthorized)
        "oauth validation",
        "unauthorized",
        # Common OAuth error descriptions
        "expired token",
        "token expired",
        "authentication failed",
        "invalid access token",
    ]

    # Create retry config that skips OAuth errors
    retry_config = (
        RetryConfig(
            max_retries=max_retries,
            skip_retry_on_error_substrings=oauth_error_patterns,
        )
        if enable_retries
        else None
    )

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
        retry_config=retry_config,  # NEW: Pass OAuth-aware retry config
    )

    logger.debug(
        "MCP (HTTP Streamable) initialised - %d tool%s registered into namespace '%s'",
        len(registered),
        "" if len(registered) == 1 else "s",
        namespace,
    )
    return processor, stream_manager
