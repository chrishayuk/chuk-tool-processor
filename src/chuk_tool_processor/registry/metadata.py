# chuk_tool_processor/registry/metadata.py
"""
Tool metadata models for the registry with async-native support.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Set, List, Union
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


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
        created_at: When the tool was first registered.
        updated_at: When the tool was last updated.
        source: Optional source information (e.g., "function", "class", "langchain").
        source_name: Optional source identifier.
        concurrency_limit: Optional maximum concurrent executions.
        timeout: Optional default timeout in seconds.
        rate_limit: Optional rate limiting configuration.
    """
    name: str = Field(..., description="Tool name")
    namespace: str = Field("default", description="Namespace the tool belongs to")
    description: Optional[str] = Field(None, description="Tool description")
    version: str = Field("1.0.0", description="Tool implementation version")
    is_async: bool = Field(True, description="Whether the tool's execute method is asynchronous")
    argument_schema: Optional[Dict[str, Any]] = Field(None, description="Schema for the tool's arguments")
    result_schema: Optional[Dict[str, Any]] = Field(None, description="Schema for the tool's result")
    requires_auth: bool = Field(False, description="Whether the tool requires authentication")
    tags: Set[str] = Field(default_factory=set, description="Tags associated with the tool")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When the tool was first registered")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When the tool was last updated")
    source: Optional[str] = Field(None, description="Source of the tool (e.g., 'function', 'class', 'langchain')")
    source_name: Optional[str] = Field(None, description="Source identifier (e.g., function name, class name)")
    concurrency_limit: Optional[int] = Field(None, description="Maximum concurrent executions (None = unlimited)")
    timeout: Optional[float] = Field(None, description="Default timeout in seconds (None = no timeout)")
    rate_limit: Optional[Dict[str, Any]] = Field(None, description="Rate limiting configuration")
    
    # Additional fields for async-native architecture
    supports_streaming: bool = Field(False, description="Whether the tool supports streaming responses")
    execution_options: Dict[str, Any] = Field(default_factory=dict, description="Additional execution options")
    dependencies: List[str] = Field(default_factory=list, description="Dependencies on other tools")
    
    @model_validator(mode='after')
    def ensure_async(self) -> 'ToolMetadata':
        """Ensure all tools are marked as async in the async-native architecture."""
        self.is_async = True
        return self
    
    def with_updated_timestamp(self) -> 'ToolMetadata':
        """Create a copy with updated timestamp."""
        return self.model_copy(update={"updated_at": datetime.utcnow()})
    
    def __str__(self) -> str:
        """String representation of the tool metadata."""
        return f"{self.namespace}.{self.name} (v{self.version})"


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for tools."""
    requests: int = Field(..., description="Maximum number of requests")
    period: float = Field(..., description="Time period in seconds")
    scope: str = Field("global", description="Scope of rate limiting: 'global', 'user', 'ip'")


class StreamingToolMetadata(ToolMetadata):
    """Extended metadata for tools that support streaming responses."""
    supports_streaming: bool = Field(True, description="Whether the tool supports streaming responses")
    chunk_size: Optional[int] = Field(None, description="Suggested chunk size for streaming")
    content_type: Optional[str] = Field(None, description="Content type for streaming responses")