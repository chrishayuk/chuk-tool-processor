# chuk_tool_processor/mcp/transport/__init__.py
"""
MCP Transport module providing multiple transport implementations.
"""

from .base_transport import MCPBaseTransport

# Always available transports
try:
    from .stdio_transport import StdioTransport
    HAS_STDIO_TRANSPORT = True
except ImportError:
    StdioTransport = None
    HAS_STDIO_TRANSPORT = False

# Conditionally available transports
try:
    from .sse_transport import SSETransport
    HAS_SSE_TRANSPORT = True
except ImportError:
    SSETransport = None
    HAS_SSE_TRANSPORT = False

try:
    from .http_streamable_transport import HTTPStreamableTransport
    HAS_HTTP_STREAMABLE_TRANSPORT = True
except ImportError:
    HTTPStreamableTransport = None
    HAS_HTTP_STREAMABLE_TRANSPORT = False

__all__ = [
    "MCPBaseTransport",
    "StdioTransport",
    "SSETransport", 
    "HTTPStreamableTransport",
    "HAS_STDIO_TRANSPORT",
    "HAS_SSE_TRANSPORT",
    "HAS_HTTP_STREAMABLE_TRANSPORT"
]