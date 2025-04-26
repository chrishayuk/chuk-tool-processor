# chuk_tool_processor/exceptions.py
from typing import Optional, Any, Dict


class ToolProcessorError(Exception):
    """Base exception for all tool processor errors."""
    pass


class ToolNotFoundError(ToolProcessorError):
    """Raised when a requested tool is not found in the registry."""
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in registry")


class ToolExecutionError(ToolProcessorError):
    """Raised when a tool execution fails."""
    def __init__(self, tool_name: str, original_error: Optional[Exception] = None):
        self.tool_name = tool_name
        self.original_error = original_error
        message = f"Tool '{tool_name}' execution failed"
        if original_error:
            message += f": {str(original_error)}"
        super().__init__(message)


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool execution times out."""
    def __init__(self, tool_name: str, timeout: float):
        self.timeout = timeout
        super().__init__(tool_name, Exception(f"Execution timed out after {timeout}s"))


class ToolValidationError(ToolProcessorError):
    """Raised when tool arguments or results fail validation."""
    def __init__(self, tool_name: str, errors: Dict[str, Any]):
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Validation failed for tool '{tool_name}': {errors}")


class ParserError(ToolProcessorError):
    """Raised when parsing tool calls from raw input fails."""
    pass