#!/usr/bin/env python
# chuk_tool_processor/mcp/models.py
"""
Pydantic models for MCP server configurations.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class MCPTransport(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class MCPServerConfig(BaseModel):
    """Unified configuration for MCP servers (all transport types)."""

    name: str = Field(description="Server identifier name")
    transport: MCPTransport = Field(default=MCPTransport.STDIO, description="Transport protocol")

    # STDIO fields
    command: str | None = Field(default=None, description="Command to execute (stdio only)")
    args: list[str] = Field(default_factory=list, description="Command arguments (stdio only)")
    env: dict[str, str] | None = Field(default=None, description="Environment variables (stdio only)")

    # SSE/HTTP fields
    url: str | None = Field(default=None, description="Server URL (sse/http)")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers (sse/http)")
    timeout: float = Field(default=10.0, description="Connection timeout in seconds")
    sse_read_timeout: float = Field(default=300.0, description="SSE read timeout in seconds (sse only)")
    api_key: str | None = Field(default=None, description="API key extracted from Authorization header")
    session_id: str | None = Field(default=None, description="Session ID for HTTP transport")

    @model_validator(mode="after")
    def validate_transport_fields(self) -> MCPServerConfig:
        """Validate required fields based on transport type."""
        if self.transport == MCPTransport.STDIO:
            if not self.command:
                raise ValueError("command is required for stdio transport")
        else:
            # SSE/HTTP
            if not self.url:
                raise ValueError(f"url is required for {self.transport} transport")
            # Extract API key from Authorization header if present
            if not self.api_key and self.headers:
                auth_header = self.headers.get("Authorization", "")
                if "Bearer " in auth_header:
                    self.api_key = auth_header.split("Bearer ")[-1]
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for internal use."""
        if self.transport == MCPTransport.STDIO:
            result = {
                "name": self.name,
                "command": self.command,
                "args": self.args,
            }
            if self.env:
                result["env"] = self.env
            return result
        else:
            # SSE/HTTP
            result = {
                "name": self.name,
                "url": self.url,
                "headers": self.headers,
                "timeout": self.timeout,
            }
            if self.transport == MCPTransport.SSE:
                result["sse_read_timeout"] = self.sse_read_timeout
            if self.api_key:
                result["api_key"] = self.api_key
            if self.session_id:
                result["session_id"] = self.session_id
            return result


class MCPConfig(BaseModel):
    """
    Configuration for MCP setup with sensible defaults.

    This model provides a cleaner, type-safe way to configure MCP connections
    instead of passing many individual parameters.

    Example:
        >>> from chuk_tool_processor.mcp import MCPConfig, MCPServerConfig
        >>>
        >>> # Simple configuration
        >>> config = MCPConfig(
        ...     servers=[
        ...         MCPServerConfig(
        ...             name="echo",
        ...             command="uvx",
        ...             args=["chuk-mcp-echo", "stdio"],
        ...         )
        ...     ],
        ...     namespace="tools",
        ... )
        >>>
        >>> # Advanced configuration
        >>> config = MCPConfig(
        ...     servers=[...],
        ...     namespace="mcp",
        ...     enable_caching=True,
        ...     cache_ttl=600,
        ...     enable_retries=True,
        ...     max_retries=5,
        ... )
    """

    # Server configuration
    servers: list[MCPServerConfig] = Field(description="List of MCP server configurations")
    server_names: dict[int, str] | None = Field(
        default=None, description="Optional server name mapping (for legacy compatibility)"
    )

    # Basic settings
    namespace: str = Field(default="mcp", description="Namespace for registered tools")
    default_timeout: float = Field(default=10.0, description="Default timeout for operations in seconds")
    initialization_timeout: float = Field(default=60.0, description="Timeout for initialization in seconds")
    max_concurrency: int | None = Field(default=None, description="Maximum concurrent operations (None = unlimited)")

    # Caching
    enable_caching: bool = Field(default=True, description="Enable result caching")
    cache_ttl: int = Field(default=300, description="Cache time-to-live in seconds")

    # Rate limiting
    enable_rate_limiting: bool = Field(default=False, description="Enable rate limiting")
    global_rate_limit: int | None = Field(default=None, description="Global rate limit (requests per period)")
    tool_rate_limits: dict[str, tuple] | None = Field(
        default=None, description="Per-tool rate limits {tool_name: (requests, period)}"
    )

    # Retry configuration
    enable_retries: bool = Field(default=True, description="Enable automatic retries on failure")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")

    # Legacy config file support
    config_file: str | None = Field(default=None, description="Optional config file path (for backward compatibility)")


__all__ = ["MCPServerConfig", "MCPTransport", "MCPConfig"]
