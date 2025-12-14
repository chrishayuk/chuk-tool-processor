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
    # Exceptions
    BulkheadFullError,
    # Error taxonomy
    ErrorCategory,
    ErrorCode,
    ErrorInfo,
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
    # Helper functions
    get_category_for_code,
    is_retryable_category,
)

__all__ = [
    # Context
    "ExecutionContext",
    "ContextHeader",
    "ContextKey",
    "execution_scope",
    "get_current_context",
    "set_current_context",
    # Error taxonomy
    "ErrorCode",
    "ErrorCategory",
    "ErrorInfo",
    "get_category_for_code",
    "is_retryable_category",
    # Exceptions
    "ToolProcessorError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolValidationError",
    "ParserError",
    "ToolRateLimitedError",
    "ToolCircuitOpenError",
    "BulkheadFullError",
    "MCPError",
    "MCPConnectionError",
    "MCPTimeoutError",
]
