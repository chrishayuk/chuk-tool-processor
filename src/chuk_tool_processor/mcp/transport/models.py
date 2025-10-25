# chuk_tool_processor/mcp/transport/models.py
"""
Pydantic models for MCP transport configuration and metrics.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TimeoutConfig(BaseModel):
    """
    Unified timeout configuration for all MCP operations.

    Just 4 simple, logical timeout categories:
    - connect: Connection establishment, initialization, session discovery (30s default)
    - operation: Normal operations like tool calls, listing resources (30s default)
    - quick: Fast health checks and pings (5s default)
    - shutdown: Cleanup and shutdown operations (2s default)
    """

    connect: float = Field(
        default=30.0, description="Timeout for connection establishment, initialization, and session discovery"
    )
    operation: float = Field(
        default=30.0, description="Timeout for normal operations (tool calls, listing tools/resources/prompts)"
    )
    quick: float = Field(default=5.0, description="Timeout for quick health checks and pings")
    shutdown: float = Field(default=2.0, description="Timeout for shutdown and cleanup operations")


class TransportMetrics(BaseModel):
    """Performance and connection metrics for transports."""

    model_config = {"validate_assignment": True}

    total_calls: int = Field(default=0, description="Total number of calls made")
    successful_calls: int = Field(default=0, description="Number of successful calls")
    failed_calls: int = Field(default=0, description="Number of failed calls")
    total_time: float = Field(default=0.0, description="Total time spent on calls")
    avg_response_time: float = Field(default=0.0, description="Average response time")
    last_ping_time: float | None = Field(default=None, description="Time taken for last ping")
    initialization_time: float | None = Field(default=None, description="Time taken for initialization")
    connection_resets: int = Field(default=0, description="Number of connection resets")
    stream_errors: int = Field(default=0, description="Number of stream errors")
    connection_errors: int = Field(default=0, description="Number of connection errors")
    recovery_attempts: int = Field(default=0, description="Number of recovery attempts")
    session_discoveries: int = Field(default=0, description="Number of session discoveries (SSE)")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return self.model_dump()

    def update_call_metrics(self, response_time: float, success: bool) -> None:
        """Update metrics after a call."""
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1

        self.total_time += response_time
        if self.total_calls > 0:
            self.avg_response_time = self.total_time / self.total_calls


class ServerInfo(BaseModel):
    """Information about a server in StreamManager."""

    id: int = Field(description="Server ID")
    name: str = Field(description="Server name")
    tools: int = Field(description="Number of tools available")
    status: str = Field(description="Server status (Up/Down)")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return self.model_dump()


class HeadersConfig(BaseModel):
    """Configuration for HTTP headers."""

    headers: dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")

    def get_headers(self) -> dict[str, str]:
        """Get headers as dict."""
        return self.headers.copy()

    def update_headers(self, new_headers: dict[str, str]) -> None:
        """Update headers with new values."""
        self.headers.update(new_headers)

    def has_authorization(self) -> bool:
        """Check if Authorization header is present."""
        return "Authorization" in self.headers

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return self.model_dump()
