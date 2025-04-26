# chuk_tool_processor/registry/metadata.py
"""
Tool metadata models for the registry.
"""
from typing import Any, Dict, Optional, Set
from pydantic import BaseModel, Field


class ToolMetadata(BaseModel):
    """
    Metadata for registered tools.
    
    Attributes:
        name: The name of the tool.
        namespace: The namespace the tool belongs to.
        description: Optional description of the tool's functionality.
        version: Version of the tool implementation.
        is_async: Whether the tool's execute method is asynchronous.
        argument_schema: Optional schema for the tool's arguments.
        result_schema: Optional schema for the tool's result.
        requires_auth: Whether the tool requires authentication.
        tags: Set of tags associated with the tool.
    """
    name: str = Field(..., description="Tool name")
    namespace: str = Field("default", description="Namespace the tool belongs to")
    description: Optional[str] = Field(None, description="Tool description")
    version: str = Field("1.0.0", description="Tool implementation version")
    is_async: bool = Field(False, description="Whether the tool's execute method is asynchronous")
    argument_schema: Optional[Dict[str, Any]] = Field(None, description="Schema for the tool's arguments")
    result_schema: Optional[Dict[str, Any]] = Field(None, description="Schema for the tool's result")
    requires_auth: bool = Field(False, description="Whether the tool requires authentication")
    tags: Set[str] = Field(default_factory=set, description="Tags associated with the tool")

    def __str__(self) -> str:
        """String representation of the tool metadata."""
        return f"{self.namespace}.{self.name} (v{self.version})"