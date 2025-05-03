# chuk_tool_processor/mcp/__init__.py
"""
MCP integration for CHUK Tool Processor.
"""
from chuk_tool_processor.mcp.transport import MCPBaseTransport, StdioTransport, SSETransport
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

__all__ = [
    "MCPBaseTransport",
    "StdioTransport",
    "SSETransport",
    "StreamManager",
    "MCPTool",
    "register_mcp_tools",
    "setup_mcp_stdio",
    "setup_mcp_sse"
]