# chuk_tool_processor/models/tool_spec.py
"""
Formal tool specification with JSON Schema export, versioning, and capability discovery.

This module provides a unified way to describe tools with their:
- Input/output schemas (JSON Schema)
- Versioning information
- Capabilities (streaming, cancellable, idempotent, etc.)
- Export to various formats (OpenAI, MCP, Anthropic)
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolCapability(str, Enum):
    """Capabilities that a tool can support."""

    STREAMING = "streaming"  # Tool supports streaming responses
    CANCELLABLE = "cancellable"  # Tool supports cancellation
    IDEMPOTENT = "idempotent"  # Tool is safe to retry (same result)
    CACHEABLE = "cacheable"  # Results can be cached
    RATE_LIMITED = "rate_limited"  # Tool has rate limits
    REQUIRES_AUTH = "requires_auth"  # Tool requires authentication
    LONG_RUNNING = "long_running"  # Tool may take >30s
    STATEFUL = "stateful"  # Tool maintains state across calls


class ToolSpec(BaseModel):
    """
    Formal tool specification with JSON Schema export and versioning.

    This provides a complete description of a tool's interface, capabilities,
    and metadata for discovery and validation.
    """

    # Core metadata
    name: str = Field(..., description="Tool name (must be unique within namespace)")
    version: str = Field(default="1.0.0", description="Semantic version (e.g., '1.2.3')")
    description: str = Field(..., description="Human-readable description of what the tool does")
    namespace: str = Field(default="default", description="Namespace for organizing tools")

    # Schema definitions
    parameters: dict[str, Any] = Field(
        ...,
        description="JSON Schema for tool parameters (input)",
    )
    returns: dict[str, Any] | None = Field(
        None,
        description="JSON Schema for return value (output). None if unstructured.",
    )

    # Capabilities and metadata
    capabilities: list[ToolCapability] = Field(
        default_factory=list,
        description="List of capabilities this tool supports",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization (e.g., ['search', 'web'])",
    )
    examples: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Example input/output pairs for documentation",
    )

    # Optional metadata
    author: str | None = Field(None, description="Tool author/maintainer")
    license: str | None = Field(None, description="License (e.g., 'MIT', 'Apache-2.0')")
    documentation_url: str | None = Field(None, description="Link to full documentation")
    source_url: str | None = Field(None, description="Link to source code")

    # Execution hints
    estimated_duration_seconds: float | None = Field(
        None,
        description="Typical execution time in seconds (for timeout planning)",
    )
    max_retries: int | None = Field(
        None,
        description="Maximum recommended retries (None = use default)",
    )

    # ------------------------------------------------------------------ #
    # Capability checks
    # ------------------------------------------------------------------ #
    def has_capability(self, capability: ToolCapability) -> bool:
        """Check if tool has a specific capability."""
        return capability in self.capabilities

    def is_streaming(self) -> bool:
        """Check if tool supports streaming."""
        return self.has_capability(ToolCapability.STREAMING)

    def is_idempotent(self) -> bool:
        """Check if tool is safe to retry."""
        return self.has_capability(ToolCapability.IDEMPOTENT)

    def is_cacheable(self) -> bool:
        """Check if results can be cached."""
        return self.has_capability(ToolCapability.CACHEABLE)

    # ------------------------------------------------------------------ #
    # Export formats
    # ------------------------------------------------------------------ #
    def to_openai(self) -> dict[str, Any]:
        """
        Export as OpenAI function calling format.

        Returns:
            Dict compatible with OpenAI's tools=[...] parameter
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic(self) -> dict[str, Any]:
        """
        Export as Anthropic tool format.

        Returns:
            Dict compatible with Anthropic's tools parameter
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_mcp(self) -> dict[str, Any]:
        """
        Export as MCP tool format.

        Returns:
            Dict compatible with MCP tool schema
        """
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }

        # Add optional fields if present
        if self.returns:
            result["outputSchema"] = self.returns

        return result

    def to_json_schema(self) -> dict[str, Any]:
        """
        Export as pure JSON Schema (parameters only).

        Returns:
            JSON Schema dict for tool parameters
        """
        return self.parameters

    def to_dict(self) -> dict[str, Any]:
        """
        Export complete spec as dict.

        Returns:
            Full tool specification as dictionary
        """
        return self.model_dump(exclude_none=True)

    # ------------------------------------------------------------------ #
    # Factory methods
    # ------------------------------------------------------------------ #
    @classmethod
    def from_validated_tool(
        cls,
        tool_cls: type,
        name: str | None = None,
        namespace: str = "default",
    ) -> ToolSpec:
        """
        Create ToolSpec from a ValidatedTool class.

        Args:
            tool_cls: ValidatedTool subclass
            name: Override tool name (default: class name)
            namespace: Tool namespace

        Returns:
            ToolSpec instance
        """
        from chuk_tool_processor.models.validated_tool import ValidatedTool

        if not issubclass(tool_cls, ValidatedTool):
            raise TypeError(f"{tool_cls.__name__} must be a ValidatedTool subclass")

        # Extract metadata
        tool_name = name or tool_cls.__name__
        description = (tool_cls.__doc__ or f"{tool_name} tool").strip()

        # Extract schemas
        parameters = tool_cls.Arguments.model_json_schema()
        returns = tool_cls.Result.model_json_schema() if hasattr(tool_cls, "Result") else None

        # Detect capabilities
        capabilities = []

        # Check if tool is marked cacheable
        if hasattr(tool_cls, "_cacheable") and tool_cls._cacheable:
            capabilities.append(ToolCapability.CACHEABLE)

        # Check if idempotent (common pattern: GET-like operations)
        if "get" in tool_name.lower() or "read" in tool_name.lower():
            capabilities.append(ToolCapability.IDEMPOTENT)

        # Check if streaming
        from chuk_tool_processor.models.streaming_tool import StreamingTool

        if issubclass(tool_cls, StreamingTool):
            capabilities.append(ToolCapability.STREAMING)

        return cls(  # type: ignore[call-arg]
            name=tool_name,
            description=description,
            namespace=namespace,
            parameters=parameters,
            returns=returns,
            capabilities=capabilities,
        )

    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        namespace: str = "default",
    ) -> ToolSpec:
        """
        Create ToolSpec from a plain function.

        Args:
            func: Function to wrap
            name: Tool name (default: function name)
            description: Tool description (default: function docstring)
            namespace: Tool namespace

        Returns:
            ToolSpec instance
        """
        # Extract metadata
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or f"{tool_name} function").strip()

        # Build parameter schema from function signature
        sig = inspect.signature(func)
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Build property schema
            prop: dict[str, Any] = {}

            # Try to infer type from annotation
            if param.annotation != inspect.Parameter.empty:
                annotation = param.annotation
                # Handle basic types
                if annotation is str:
                    prop["type"] = "string"
                elif annotation is int:
                    prop["type"] = "integer"
                elif annotation is float:
                    prop["type"] = "number"
                elif annotation is bool:
                    prop["type"] = "boolean"
                elif annotation is list:
                    prop["type"] = "array"
                elif annotation is dict:
                    prop["type"] = "object"

            # Add to schema
            parameters["properties"][param_name] = prop

            # Mark as required if no default
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)

        return cls(  # type: ignore[call-arg]
            name=tool_name,
            description=tool_description,
            namespace=namespace,
            parameters=parameters,
            returns=None,  # Can't infer return type from plain function
            capabilities=[],
        )


# ------------------------------------------------------------------ #
# Convenience decorators
# ------------------------------------------------------------------ #
def tool_spec(
    *,
    version: str = "1.0.0",
    capabilities: list[ToolCapability] | None = None,
    tags: list[str] | None = None,
    estimated_duration_seconds: float | None = None,
) -> Callable:
    """
    Decorator to attach tool specification metadata to a tool class.

    Example:
        @tool_spec(
            version="2.1.0",
            capabilities=[ToolCapability.CACHEABLE, ToolCapability.IDEMPOTENT],
            tags=["search", "web"],
            estimated_duration_seconds=2.0,
        )
        class SearchTool(ValidatedTool):
            ...

    Args:
        version: Semantic version
        capabilities: List of capabilities
        tags: List of tags
        estimated_duration_seconds: Estimated execution time

    Returns:
        Decorator function
    """

    def decorator(cls):
        cls._tool_spec_version = version
        cls._tool_spec_capabilities = capabilities or []
        cls._tool_spec_tags = tags or []
        cls._tool_spec_estimated_duration = estimated_duration_seconds
        return cls

    return decorator
