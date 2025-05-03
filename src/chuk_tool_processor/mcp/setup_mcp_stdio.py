# chuk_tool_processor/mcp/setup_mcp_stdio.py
"""
Setup function for stdio transport MCP integration.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.mcp.setup_stdio")


async def setup_mcp_stdio(
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
    namespace: str = "mcp"
) -> tuple[ToolProcessor, StreamManager]:
    """
    Set up MCP with stdio transport and CHUK Tool Processor.
    
    Args:
        config_file: Path to the config file
        servers: List of server names to connect to
        server_names: Optional mapping of server indices to names
        default_timeout: Default timeout for tool execution
        max_concurrency: Maximum concurrent executions
        enable_caching: Whether to enable caching
        cache_ttl: Cache TTL in seconds
        enable_rate_limiting: Whether to enable rate limiting
        global_rate_limit: Global rate limit (requests per minute)
        tool_rate_limits: Per-tool rate limits
        enable_retries: Whether to enable retries
        max_retries: Maximum retry attempts
        namespace: Namespace for MCP tools
        
    Returns:
        Tuple of (processor, stream_manager)
    """
    # Create and initialize StreamManager with stdio transport
    stream_manager = await StreamManager.create(
        config_file=config_file,
        servers=servers,
        server_names=server_names,
        transport_type="stdio"
    )
    
    # Register MCP tools
    registered_tools = register_mcp_tools(stream_manager, namespace)
    
    # Create processor
    processor = ToolProcessor(
        default_timeout=default_timeout,
        max_concurrency=max_concurrency,
        enable_caching=enable_caching,
        cache_ttl=cache_ttl,
        enable_rate_limiting=enable_rate_limiting,
        global_rate_limit=global_rate_limit,
        tool_rate_limits=tool_rate_limits,
        enable_retries=enable_retries,
        max_retries=max_retries
    )
    
    logger.info(f"Set up MCP (stdio) with {len(registered_tools)} tools")
    return processor, stream_manager