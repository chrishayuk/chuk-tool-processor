# chuk_tool_processor/models/tool_result.py
"""
Model representing the result of a tool execution.
"""

from __future__ import annotations

import os
import platform
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo


class ToolResult(BaseModel):
    """
    Represents the result of executing a tool.

    Includes timing, host, and process metadata for diagnostics and tracing.

    For error handling, planners can use the structured `error_info` field:

        result = await processor.process(calls)
        for r in result:
            if r.error_info:
                from chuk_tool_processor.core.exceptions import ErrorCategory

                if r.error_info.category == ErrorCategory.RATE_LIMIT:
                    await asyncio.sleep(r.error_info.retry_after_ms / 1000)
                    return await retry()
                elif r.error_info.category == ErrorCategory.CIRCUIT_OPEN:
                    return await use_fallback_tool()
                elif not r.error_info.retryable:
                    return await report_permanent_failure()

    Attributes:
        id: Unique identifier for the result
        tool: Name of the tool that was executed
        result: Return value from the tool execution
        error: Error message if execution failed (string for backwards compat)
        error_info: Structured error information for planner decision-making
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
    call_id: str | None = Field(default=None, description="ID of the original ToolCall (for tracking submission order)")

    # Core fields
    tool: str = Field(..., min_length=1, description="Name of the tool; must be non-empty")
    result: Any = Field(None, description="Return value from the tool execution")
    error: str | None = Field(None, description="Error message if execution failed (for backwards compatibility)")

    # Structured error information (new)
    error_info: ErrorInfo | None = Field(
        default=None,
        description="Structured error information with category, retryability, and retry hints",
    )

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

    @model_validator(mode="after")
    def _sync_error_fields(self) -> ToolResult:
        """
        Ensure error and error_info are consistent.

        If error is set but error_info is not, parse error_info from the string.
        If error_info is set but error is not, populate error from the message.
        """
        # Import here to avoid circular imports
        from chuk_tool_processor.core.exceptions import ErrorInfo as EI

        if self.error is not None and self.error_info is None:
            # Parse error string into structured error info
            object.__setattr__(self, "error_info", EI.from_error_string(self.error, self.tool))
        elif self.error_info is not None and self.error is None:
            # Populate error string from error_info
            object.__setattr__(self, "error", self.error_info.message)

        return self

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

    @property
    def retryable(self) -> bool:
        """
        Check if this error is retryable.

        Convenience property that delegates to error_info.
        Returns True if no error (success case).
        """
        if self.error_info is None:
            return True  # No error = success, could be "retried" (though unnecessary)
        return self.error_info.retryable

    @property
    def retry_after_ms(self) -> int | None:
        """
        Get the suggested retry delay in milliseconds.

        Convenience property that delegates to error_info.
        Returns None if no error or no specific delay suggested.
        """
        if self.error_info is None:
            return None
        return self.error_info.retry_after_ms

    @property
    def error_category(self) -> ErrorCategory | None:
        """
        Get the error category for planner decision-making.

        Convenience property that delegates to error_info.
        Returns None if no error.
        """
        if self.error_info is None:
            return None
        return self.error_info.category

    @property
    def error_code(self) -> ErrorCode | None:
        """
        Get the machine-readable error code.

        Convenience property that delegates to error_info.
        Returns None if no error.
        """
        if self.error_info is None:
            return None
        return self.error_info.code

    async def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary for serialization."""
        result_dict: dict[str, Any] = {
            "id": self.id,
            "call_id": self.call_id,
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

        # Add structured error info if present
        if self.error_info is not None:
            result_dict["error_info"] = self.error_info.model_dump(mode="json")

        return result_dict

    @classmethod
    def create_stream_chunk(cls, tool: str, result: Any, stream_id: str | None = None) -> ToolResult:
        """Create a partial streaming result."""
        stream_id = stream_id or str(uuid.uuid4())
        return cls(tool=tool, result=result, error=None, stream_id=stream_id, is_partial=True)

    @classmethod
    async def from_dict(cls, data: dict[str, Any]) -> ToolResult:
        """Create a ToolResult from a dictionary."""
        # Import here to avoid circular imports
        from chuk_tool_processor.core.exceptions import ErrorInfo

        # Make a copy to avoid mutating the input
        data = dict(data)

        # Handle datetime fields
        if isinstance(data.get("start_time"), str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data.get("end_time"), str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])

        # Handle error_info deserialization
        if isinstance(data.get("error_info"), dict):
            data["error_info"] = ErrorInfo.model_validate(data["error_info"])

        return cls(**data)

    @classmethod
    def create_error(
        cls,
        tool: str,
        error: str | Exception,
        *,
        call_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        machine: str | None = None,
        pid: int | None = None,
        attempts: int = 1,
    ) -> ToolResult:
        """
        Create an error result with proper structured error info.

        This is the preferred way to create error results as it ensures
        proper error categorization and retry hints.

        Args:
            tool: Name of the tool
            error: Error string or exception
            call_id: Original call ID for tracking
            start_time: Execution start time
            end_time: Execution end time
            machine: Machine hostname
            pid: Process ID
            attempts: Number of attempts made

        Returns:
            ToolResult with structured error_info populated
        """
        from chuk_tool_processor.core.exceptions import ErrorInfo

        now = datetime.now(UTC)

        # Create error info from exception or string
        if isinstance(error, Exception):
            error_info = ErrorInfo.from_exception(error)
            error_str = str(error)
        else:
            error_info = ErrorInfo.from_error_string(error, tool)
            error_str = error

        return cls(
            tool=tool,
            result=None,
            error=error_str,
            error_info=error_info,
            call_id=call_id,
            start_time=start_time or now,
            end_time=end_time or now,
            machine=machine or platform.node(),
            pid=pid or os.getpid(),
            attempts=attempts,
        )

    def __str__(self) -> str:
        """String representation of the tool result."""
        status = "success" if self.is_success else f"error: {self.error}"
        return f"ToolResult({self.tool}, {status}, duration={self.duration:.3f}s)"


# Rebuild model to resolve forward references
def _rebuild_tool_result() -> None:
    """Rebuild ToolResult model to resolve ErrorInfo forward reference."""
    from chuk_tool_processor.core.exceptions import ErrorCategory, ErrorCode, ErrorInfo

    # Provide the forward reference types to model_rebuild
    ToolResult.model_rebuild(
        _types_namespace={"ErrorInfo": ErrorInfo, "ErrorCategory": ErrorCategory, "ErrorCode": ErrorCode}
    )


_rebuild_tool_result()
