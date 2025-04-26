# chuk_tool_processor/models/tool_call.py
from pydantic import BaseModel, Field
from typing import Any, Dict

class ToolCall(BaseModel):
    tool: str = Field(..., min_length=1, description="Name of the tool to call; must be non‐empty")
    arguments: Dict[str, Any] = Field(default_factory=dict)