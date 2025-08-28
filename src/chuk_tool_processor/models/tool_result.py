# chuk_tool_processor/models/tool_result.py
"""
Model representing the result of a tool execution.
"""

from __future__ import annotations

import os
import platform
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolResult(BaseModel):
    """
    Represents the result of executing a tool.

    Includes timing, host, and process metadata for diagnostics and tracing.

    Attributes:
        id: Unique identifier for the result
        tool: Name of the tool that was executed
        result: Return value from the tool execution
        error: Error message if execution failed
        start_time: UTC timestamp when execution started
        end_time: UTC timestamp when execution finished
        machine: Hostname where the tool ran
        pid: Process ID of the worker
        cached: Flag indicating if the result was retrieved from cache
        attempts: Number of execution attempts made
        stream_id: Optional identifier for streaming results
        is_partial: Whether this is a partial streaming result
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for this result")

    # Core fields
    tool: str = Field(..., min_length=1, description="Name of the tool; must be non-empty")
    result: Any = Field(None, description="Return value from the tool execution")
    error: str | None = Field(None, description="Error message if execution failed")

    # Execution metadata
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC timestamp when execution started"
    )
    end_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC timestamp when execution finished"
    )
    machine: str = Field(default_factory=lambda: platform.node(), description="Hostname where the tool ran")
    pid: int = Field(default_factory=lambda: os.getpid(), description="Process ID of the worker")

    # Extended features
    cached: bool = Field(default=False, description="True if this result was retrieved from cache")
    attempts: int = Field(default=1, description="Number of execution attempts made")

    # Streaming support
    stream_id: str | None = Field(
        default=None, description="Identifier for this stream of results (for streaming tools)"
    )
    is_partial: bool = Field(default=False, description="True if this is a partial result in a stream")

    @property
    def is_success(self) -> bool:
        """Check if the execution was successful (no error)."""
        return self.error is None

    @property
    def duration(self) -> float:
        """Calculate the execution duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()

    async def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "result": self.result,
            "error": self.error,
            "success": self.is_success,
            "duration": self.duration,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "machine": self.machine,
            "pid": self.pid,
            "cached": self.cached,
            "attempts": self.attempts,
            "stream_id": self.stream_id,
            "is_partial": self.is_partial,
        }

    @classmethod
    def create_stream_chunk(cls, tool: str, result: Any, stream_id: str | None = None) -> ToolResult:
        """Create a partial streaming result."""
        stream_id = stream_id or str(uuid.uuid4())
        return cls(tool=tool, result=result, error=None, stream_id=stream_id, is_partial=True)

    @classmethod
    async def from_dict(cls, data: dict[str, Any]) -> ToolResult:
        """Create a ToolResult from a dictionary."""
        # Handle datetime fields
        if isinstance(data.get("start_time"), str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data.get("end_time"), str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])

        return cls(**data)

    def __str__(self) -> str:
        """String representation of the tool result."""
        status = "success" if self.is_success else f"error: {self.error}"
        return f"ToolResult({self.tool}, {status}, duration={self.duration:.3f}s)"
