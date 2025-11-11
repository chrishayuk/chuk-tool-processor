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

from typing import TYPE_CHECKING, Any

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager

if TYPE_CHECKING:
    from chuk_tool_processor.mcp.models import MCPConfig, MCPServerConfig

logger = get_logger("chuk_tool_processor.mcp.setup_stdio")


# --------------------------------------------------------------------------- #
# public helper
# --------------------------------------------------------------------------- #
async def setup_mcp_stdio(  # noqa: C901 - long but just a config facade
    *,
    config: MCPConfig | None = None,  # NEW: Clean config object approach
    config_file: str | None = None,  # NOW OPTIONAL - for backward compatibility
    servers: list[str]
    | list[dict[str, Any]]
    | list[MCPServerConfig]
    | None = None,  # Can be server names, dicts, OR Pydantic models
    server_names: dict[int, str] | None = None,
    default_timeout: float = 10.0,
    initialization_timeout: float = 60.0,
    max_concurrency: int | None = None,
    enable_caching: bool = True,
    cache_ttl: int = 300,
    enable_rate_limiting: bool = False,
    global_rate_limit: int | None = None,
    tool_rate_limits: dict[str, tuple] | None = None,
    enable_retries: bool = True,
    max_retries: int = 3,
    namespace: str = "mcp",
) -> tuple[ToolProcessor, StreamManager]:
    """
    Initialise stdio-transport MCP + a :class:`ToolProcessor`.

    Call with ``await`` from your async context.

    Args:
        config: MCPConfig object with all settings (BEST DX - recommended!)
        config_file: Optional config file path (legacy mode)
        servers: Can be:
            - List of server names (legacy, requires config_file)
            - List of server config dicts (new DX)
            - List of MCPServerConfig Pydantic models (best DX)
        server_names: Optional server name mapping
        default_timeout: Default timeout for operations
        initialization_timeout: Timeout for initialization
        max_concurrency: Maximum concurrent operations
        enable_caching: Enable result caching
        cache_ttl: Cache time-to-live
        enable_rate_limiting: Enable rate limiting
        global_rate_limit: Global rate limit
        tool_rate_limits: Per-tool rate limits
        enable_retries: Enable retries
        max_retries: Maximum retry attempts
        namespace: Tool namespace

    Returns:
        Tuple of (ToolProcessor, StreamManager)

    Examples:
        # BEST DX (MCPConfig):
        from chuk_tool_processor.mcp import MCPConfig, MCPServerConfig

        processor, manager = await setup_mcp_stdio(
            config=MCPConfig(
                servers=[
                    MCPServerConfig(
                        name="echo",
                        command="uvx",
                        args=["chuk-mcp-echo", "stdio"],
                    ),
                ],
                namespace="tools",
                enable_caching=True,
            )
        )

        # Good DX (Pydantic models):
        from chuk_tool_processor.mcp import MCPServerConfig, MCPTransport

        processor, manager = await setup_mcp_stdio(
            servers=[
                MCPServerConfig(
                    name="echo",
                    transport=MCPTransport.STDIO,
                    command="uvx",
                    args=["chuk-mcp-echo", "stdio"],
                ),
            ],
            namespace="tools",
        )

        # Legacy (with config file):
        processor, manager = await setup_mcp_stdio(
            config_file="mcp_config.json",
            servers=["echo"],
            namespace="tools",
        )
    """
    # Import here to avoid circular dependency at module level
    from chuk_tool_processor.mcp.models import MCPConfig as MCPConfigModel
    from chuk_tool_processor.mcp.models import MCPServerConfig as MCPServerConfigModel

    # If MCPConfig is provided, use it to override all parameters
    if config is not None:
        if not isinstance(config, MCPConfigModel):
            raise TypeError("config must be an MCPConfig instance")

        config_file = config.config_file
        servers = config.servers
        server_names = config.server_names
        default_timeout = config.default_timeout
        initialization_timeout = config.initialization_timeout
        max_concurrency = config.max_concurrency
        enable_caching = config.enable_caching
        cache_ttl = config.cache_ttl
        enable_rate_limiting = config.enable_rate_limiting
        global_rate_limit = config.global_rate_limit
        tool_rate_limits = config.tool_rate_limits
        enable_retries = config.enable_retries
        max_retries = config.max_retries
        namespace = config.namespace

    # Ensure servers is provided
    if servers is None:
        raise ValueError("Either 'config' or 'servers' must be provided")

    # Check what format the servers are in
    if servers and isinstance(servers[0], str):
        # LEGACY: servers are names, config_file is required
        if config_file is None:
            raise ValueError("config_file is required when servers is a list of strings")

        stream_manager = await StreamManager.create(
            config_file=config_file,
            servers=servers,  # type: ignore[arg-type]
            server_names=server_names,
            transport_type="stdio",
            default_timeout=default_timeout,
            initialization_timeout=initialization_timeout,
        )
    else:
        # NEW DX: servers are config dicts or Pydantic models
        # Convert Pydantic models to dicts if needed
        server_dicts: list[dict[str, Any]]
        if servers and isinstance(servers[0], MCPServerConfigModel):
            server_dicts = [s.to_dict() for s in servers]  # type: ignore[union-attr]
        else:
            server_dicts = servers  # type: ignore[assignment]

        stream_manager = await StreamManager.create_with_stdio(
            servers=server_dicts,
            server_names=server_names,
            default_timeout=default_timeout,
            initialization_timeout=initialization_timeout,
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
        "MCP (stdio) initialised - %d tool%s registered into namespace '%s'",
        len(registered),
        "" if len(registered) == 1 else "s",
        namespace,
    )
    return processor, stream_manager
