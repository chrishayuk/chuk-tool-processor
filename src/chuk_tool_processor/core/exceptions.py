# chuk_tool_processor/exceptions.py
from difflib import get_close_matches
from enum import Enum
from typing import Any, cast


class ErrorCode(str, Enum):
    """Machine-readable error codes for tool processor errors."""

    # Tool registry errors
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_REGISTRATION_FAILED = "TOOL_REGISTRATION_FAILED"

    # Execution errors
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_CANCELLED = "TOOL_CANCELLED"

    # Validation errors
    TOOL_VALIDATION_ERROR = "TOOL_VALIDATION_ERROR"
    TOOL_ARGUMENT_ERROR = "TOOL_ARGUMENT_ERROR"
    TOOL_RESULT_ERROR = "TOOL_RESULT_ERROR"

    # Rate limiting and circuit breaker
    TOOL_RATE_LIMITED = "TOOL_RATE_LIMITED"
    TOOL_CIRCUIT_OPEN = "TOOL_CIRCUIT_OPEN"

    # Parser errors
    PARSER_ERROR = "PARSER_ERROR"
    PARSER_INVALID_FORMAT = "PARSER_INVALID_FORMAT"

    # MCP errors
    MCP_CONNECTION_FAILED = "MCP_CONNECTION_FAILED"
    MCP_TRANSPORT_ERROR = "MCP_TRANSPORT_ERROR"
    MCP_SERVER_ERROR = "MCP_SERVER_ERROR"
    MCP_TIMEOUT = "MCP_TIMEOUT"

    # System errors
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class ToolProcessorError(Exception):
    """Base exception for all tool processor errors with machine-readable codes."""

    def __init__(
        self,
        message: str,
        code: ErrorCode | None = None,
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.code = code or ErrorCode.TOOL_EXECUTION_FAILED
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to a structured dictionary for logging/monitoring."""
        result = {
            "error": self.__class__.__name__,
            "code": self.code.value,
            "message": str(self),
            "details": self.details,
        }
        if self.original_error:
            result["original_error"] = {
                "type": type(self.original_error).__name__,
                "message": str(self.original_error),
            }
        return result


class ToolNotFoundError(ToolProcessorError):
    """Raised when a requested tool is not found in the registry."""

    def __init__(
        self,
        tool_name: str,
        namespace: str = "default",
        available_tools: list[tuple[str, str]] | list[str] | None = None,
        available_namespaces: list[str] | None = None,
    ):
        self.tool_name = tool_name
        self.namespace = namespace

        # Build helpful error message
        message_parts = [f"Tool '{tool_name}' not found in namespace '{namespace}'"]

        # Find similar tool names using fuzzy matching
        similar_tools: list[str] = []
        if available_tools:
            # Handle both tuple format (namespace, name) and string format
            if isinstance(available_tools[0], tuple):
                # Type narrowing: cast to the expected type
                tuple_tools = cast(list[tuple[str, str]], available_tools)
                all_tool_names = [name for _, name in tuple_tools]
                # Also check for namespace:name format
                full_names = [f"{ns}:{name}" for ns, name in tuple_tools]
                similar_in_namespace = get_close_matches(tool_name, all_tool_names, n=3, cutoff=0.6)
                similar_full = get_close_matches(f"{namespace}:{tool_name}", full_names, n=3, cutoff=0.6)
                similar_tools = list(similar_in_namespace) + list(similar_full)
            else:
                # Type narrowing: cast to the expected type
                str_tools = cast(list[str], available_tools)
                similar_tools = list(get_close_matches(tool_name, str_tools, n=3, cutoff=0.6))

        if similar_tools:
            message_parts.append(f"\n\nDid you mean: {', '.join(similar_tools)}?")

        # Add available namespaces
        if available_namespaces:
            message_parts.append(f"\n\nAvailable namespaces: {', '.join(available_namespaces)}")

        # Add helpful tip
        message_parts.append(
            "\n\nTip: Use `await registry.list_tools()` to see all registered tools, "
            "or `await registry.list_namespaces()` to see available namespaces."
        )

        message = "".join(message_parts)

        # Store details
        details: dict[str, Any] = {"tool_name": tool_name, "namespace": namespace}
        if available_tools:
            details["available_tools"] = available_tools
        if available_namespaces:
            details["available_namespaces"] = available_namespaces
        if similar_tools:
            details["suggestions"] = similar_tools

        super().__init__(
            message,
            code=ErrorCode.TOOL_NOT_FOUND,
            details=details,
        )


class ToolExecutionError(ToolProcessorError):
    """Raised when a tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        original_error: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.tool_name = tool_name
        message = f"Tool '{tool_name}' execution failed"
        if original_error:
            message += f": {str(original_error)}"

        error_details = {"tool_name": tool_name}
        if details:
            error_details.update(details)

        super().__init__(
            message,
            code=ErrorCode.TOOL_EXECUTION_FAILED,
            details=error_details,
            original_error=original_error,
        )


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool execution times out."""

    def __init__(self, tool_name: str, timeout: float, attempts: int = 1):
        self.timeout = timeout
        self.attempts = attempts
        # Call ToolProcessorError.__init__ directly to set the right code
        ToolProcessorError.__init__(
            self,
            f"Tool '{tool_name}' timed out after {timeout}s (attempts: {attempts})",
            code=ErrorCode.TOOL_TIMEOUT,
            details={"tool_name": tool_name, "timeout": timeout, "attempts": attempts},
        )
        self.tool_name = tool_name


class ToolValidationError(ToolProcessorError):
    """Raised when tool arguments or results fail validation."""

    def __init__(
        self,
        tool_name: str,
        errors: dict[str, Any],
        validation_type: str = "arguments",
    ):
        self.tool_name = tool_name
        self.errors = errors
        self.validation_type = validation_type
        super().__init__(
            f"Validation failed for tool '{tool_name}' {validation_type}: {errors}",
            code=ErrorCode.TOOL_VALIDATION_ERROR,
            details={"tool_name": tool_name, "validation_type": validation_type, "errors": errors},
        )


class ParserError(ToolProcessorError):
    """Raised when parsing tool calls from raw input fails."""

    def __init__(
        self,
        message: str,
        parser_name: str | None = None,
        input_sample: str | None = None,
    ):
        self.parser_name = parser_name
        self.input_sample = input_sample
        details = {}
        if parser_name:
            details["parser_name"] = parser_name
        if input_sample:
            # Truncate sample for logging
            details["input_sample"] = input_sample[:200] + "..." if len(input_sample) > 200 else input_sample
        super().__init__(
            message,
            code=ErrorCode.PARSER_ERROR,
            details=details,
        )


class ToolRateLimitedError(ToolProcessorError):
    """Raised when a tool call is rate limited."""

    def __init__(
        self,
        tool_name: str,
        retry_after: float | None = None,
        limit: int | None = None,
    ):
        self.tool_name = tool_name
        self.retry_after = retry_after
        self.limit = limit
        message = f"Tool '{tool_name}' rate limited"
        if retry_after:
            message += f" (retry after {retry_after}s)"
        super().__init__(
            message,
            code=ErrorCode.TOOL_RATE_LIMITED,
            details={"tool_name": tool_name, "retry_after": retry_after, "limit": limit},
        )


class ToolCircuitOpenError(ToolProcessorError):
    """Raised when a tool circuit breaker is open."""

    def __init__(
        self,
        tool_name: str,
        failure_count: int,
        reset_timeout: float | None = None,
    ):
        self.tool_name = tool_name
        self.failure_count = failure_count
        self.reset_timeout = reset_timeout
        message = f"Tool '{tool_name}' circuit breaker is open (failures: {failure_count})"
        if reset_timeout:
            message += f" (reset in {reset_timeout}s)"
        super().__init__(
            message,
            code=ErrorCode.TOOL_CIRCUIT_OPEN,
            details={"tool_name": tool_name, "failure_count": failure_count, "reset_timeout": reset_timeout},
        )


class MCPError(ToolProcessorError):
    """Base class for MCP-related errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        server_name: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        if server_name:
            error_details["server_name"] = server_name
        super().__init__(message, code=code, details=error_details)


class MCPConnectionError(MCPError):
    """Raised when MCP connection fails."""

    def __init__(self, server_name: str, reason: str | None = None):
        message = f"Failed to connect to MCP server '{server_name}'"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            code=ErrorCode.MCP_CONNECTION_FAILED,
            server_name=server_name,
            details={"reason": reason} if reason else None,
        )


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""

    def __init__(self, server_name: str, operation: str, timeout: float):
        super().__init__(
            f"MCP operation '{operation}' on server '{server_name}' timed out after {timeout}s",
            code=ErrorCode.MCP_TIMEOUT,
            server_name=server_name,
            details={"operation": operation, "timeout": timeout},
        )
