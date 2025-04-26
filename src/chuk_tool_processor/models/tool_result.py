# chuk_tool_processor/models/tool_result.py
import os
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional
from datetime import datetime, timezone

class ToolResult(BaseModel):
    """
    Represents the result of executing a tool.
    Includes timing, host, and process metadata for diagnostics.
    """
    # Configure Pydantic to ignore any extra fields
    model_config = ConfigDict(extra='ignore')

    # Flag indicating whether this result was retrieved from cache
    cached: bool = Field(
        default=False,
        description="True if this result was retrieved from cache"
    )

    tool: str = Field(
        ...,
        min_length=1,
        description="Name of the tool; must be non-empty"
    )
    result: Any = Field(
        None,
        description="Return value from the tool execution"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if execution failed"
    )
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when execution started"
    )
    end_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when execution finished"
    )
    machine: str = Field(
        default_factory=lambda: os.uname().nodename,
        description="Hostname where the tool ran"
    )
    pid: int = Field(
        default_factory=lambda: os.getpid(),
        description="Process ID of the worker"
    )
