# chuk_tool_processor/mcp/__init__.py
"""
MCP integration for CHUK Tool Processor.

Updated to support the latest MCP transports:
- STDIO (process-based)
- SSE (Server-Sent Events)
- HTTP Streamable (modern replacement for SSE, spec 2025-03-26)

Supports optional middleware for production-grade tool execution:
- Retry with exponential backoff
- Circuit breaker pattern
- Rate limiting
"""

from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.middleware import (
    # Defaults
    CircuitBreakerDefaults,
    # Configuration models
    CircuitBreakerSettings,
    # Status models
    CircuitBreakerStatus,
    CircuitBreakerToolState,
    MiddlewareConfig,
    # Enums
    MiddlewareLayer,
    # Stack
    MiddlewareStack,
    MiddlewareStatus,
    NonRetryableError,
    RateLimitingDefaults,
    RateLimitSettings,
    RateLimitStatus,
    RetryableError,
    RetryDefaults,
    RetrySettings,
    RetryStatus,
    StreamManagerExecutor,
    # Result model
    ToolExecutionResult,
)
from chuk_tool_processor.mcp.models import MCPConfig, MCPServerConfig, MCPTransport
from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport import HTTPStreamableTransport, MCPBaseTransport, SSETransport, StdioTransport

__all__ = [
    # Transports
    "MCPBaseTransport",
    "StdioTransport",
    "SSETransport",
    "HTTPStreamableTransport",
    # StreamManager
    "StreamManager",
    # Middleware - Enums
    "MiddlewareLayer",
    "RetryableError",
    "NonRetryableError",
    # Middleware - Defaults
    "RetryDefaults",
    "CircuitBreakerDefaults",
    "RateLimitingDefaults",
    # Middleware - Configuration
    "RetrySettings",
    "CircuitBreakerSettings",
    "RateLimitSettings",
    "MiddlewareConfig",
    # Middleware - Status
    "RetryStatus",
    "CircuitBreakerToolState",
    "CircuitBreakerStatus",
    "RateLimitStatus",
    "MiddlewareStatus",
    # Middleware - Result
    "ToolExecutionResult",
    # Middleware - Stack
    "MiddlewareStack",
    "StreamManagerExecutor",
    # Tools and models
    "MCPTool",
    "MCPConfig",
    "MCPServerConfig",
    "MCPTransport",
    # Setup helpers
    "register_mcp_tools",
    "setup_mcp_stdio",
    "setup_mcp_sse",
    "setup_mcp_http_streamable",
]
