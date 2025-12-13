# chuk_tool_processor/core/__init__.py
"""Core functionality for the tool processor."""

from chuk_tool_processor.core.context import (
    ContextHeader,
    ContextKey,
    ExecutionContext,
    execution_scope,
    get_current_context,
    set_current_context,
)
from chuk_tool_processor.core.exceptions import (
    ErrorCode,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    ParserError,
    ToolCircuitOpenError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolProcessorError,
    ToolRateLimitedError,
    ToolTimeoutError,
    ToolValidationError,
)

__all__ = [
    # Context
    "ExecutionContext",
    "ContextHeader",
    "ContextKey",
    "execution_scope",
    "get_current_context",
    "set_current_context",
    # Errors
    "ErrorCode",
    "ToolProcessorError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolValidationError",
    "ParserError",
    "ToolRateLimitedError",
    "ToolCircuitOpenError",
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
]
