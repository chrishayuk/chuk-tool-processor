# chuk_tool_processor/models/tool_call.py
"""
Model representing a tool call with arguments.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

class ToolCall(BaseModel):
    """
    Represents a call to a tool with arguments.
    
    Attributes:
        id: Unique identifier for the tool call
        tool: Name of the tool to call
        namespace: Namespace the tool belongs to
        arguments: Arguments to pass to the tool
    """
    model_config = ConfigDict(extra='ignore')
    
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the tool call"
    )
    tool: str = Field(
        ..., 
        min_length=1,
        description="Name of the tool to call; must be non-empty"
    )
    namespace: str = Field(
        default="default",
        description="Namespace the tool belongs to"
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool"
    )
    
    async def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {
            "id": self.id,
            "tool": self.tool,
            "namespace": self.namespace,
            "arguments": self.arguments
        }
    
    @classmethod
    async def from_dict(cls, data: Dict[str, Any]) -> ToolCall:
        """Create a ToolCall from a dictionary."""
        return cls(**data)
    
    def __str__(self) -> str:
        """String representation of the tool call."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"ToolCall({self.tool}, {args_str})"