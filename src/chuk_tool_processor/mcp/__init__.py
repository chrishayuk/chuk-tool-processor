# chuk_tool_processor/mcp/__init__.py
"""
MCP integration for CHUK Tool Processor.

Updated to support the latest MCP transports:
- STDIO (process-based)
- SSE (Server-Sent Events)
- HTTP Streamable (modern replacement for SSE, spec 2025-03-26)
"""

from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.models import MCPConfig, MCPServerConfig, MCPTransport
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport import HTTPStreamableTransport, MCPBaseTransport, SSETransport, StdioTransport

__all__ = [
    "MCPBaseTransport",
    "StdioTransport",
    "SSETransport",
    "HTTPStreamableTransport",
    "StreamManager",
    "MCPTool",
    "MCPConfig",
    "MCPServerConfig",
    "MCPTransport",
    "register_mcp_tools",
    "setup_mcp_stdio",
    "setup_mcp_sse",
    "setup_mcp_http_streamable",
]
