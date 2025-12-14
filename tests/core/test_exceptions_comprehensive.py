# tests/core/test_exceptions_comprehensive.py
"""
Comprehensive tests for exception classes and error codes.
"""

import pytest

from chuk_tool_processor.core.exceptions import (
    BulkheadFullError,
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
)


class TestErrorCodeEnum:
    """Tests for ErrorCode enum."""

    def test_all_error_codes_exist(self):
        """Test that all expected error codes exist."""
        assert ErrorCode.TOOL_NOT_FOUND == "TOOL_NOT_FOUND"
        assert ErrorCode.TOOL_REGISTRATION_FAILED == "TOOL_REGISTRATION_FAILED"
        assert ErrorCode.TOOL_EXECUTION_FAILED == "TOOL_EXECUTION_FAILED"
        assert ErrorCode.TOOL_TIMEOUT == "TOOL_TIMEOUT"
        assert ErrorCode.TOOL_CANCELLED == "TOOL_CANCELLED"
        assert ErrorCode.TOOL_VALIDATION_ERROR == "TOOL_VALIDATION_ERROR"
        assert ErrorCode.TOOL_ARGUMENT_ERROR == "TOOL_ARGUMENT_ERROR"
        assert ErrorCode.TOOL_RESULT_ERROR == "TOOL_RESULT_ERROR"
        assert ErrorCode.TOOL_RATE_LIMITED == "TOOL_RATE_LIMITED"
        assert ErrorCode.TOOL_CIRCUIT_OPEN == "TOOL_CIRCUIT_OPEN"
        assert ErrorCode.PARSER_ERROR == "PARSER_ERROR"
        assert ErrorCode.PARSER_INVALID_FORMAT == "PARSER_INVALID_FORMAT"
        assert ErrorCode.MCP_CONNECTION_FAILED == "MCP_CONNECTION_FAILED"
        assert ErrorCode.MCP_TRANSPORT_ERROR == "MCP_TRANSPORT_ERROR"
        assert ErrorCode.MCP_SERVER_ERROR == "MCP_SERVER_ERROR"
        assert ErrorCode.MCP_TIMEOUT == "MCP_TIMEOUT"
        assert ErrorCode.RESOURCE_EXHAUSTED == "RESOURCE_EXHAUSTED"
        assert ErrorCode.CONFIGURATION_ERROR == "CONFIGURATION_ERROR"

    def test_error_codes_are_strings(self):
        """Test that error codes can be used as strings."""
        code = ErrorCode.TOOL_NOT_FOUND
        assert isinstance(code.value, str)
        assert code.value == "TOOL_NOT_FOUND"


class TestToolNotFoundError:
    """Tests for ToolNotFoundError."""

    def test_creation_without_available_tools(self):
        """Test creating error without available tools list."""
        error = ToolNotFoundError("missing_tool")

        # New enhanced error message includes namespace and helpful tips
        assert "Tool 'missing_tool' not found in namespace 'default'" in str(error)
        assert "Tip:" in str(error)
        assert error.code == ErrorCode.TOOL_NOT_FOUND
        assert error.tool_name == "missing_tool"
        assert error.namespace == "default"
        assert error.details["tool_name"] == "missing_tool"
        assert error.details["namespace"] == "default"

    def test_creation_with_available_tools(self):
        """Test creating error with available tools list."""
        available = ["tool1", "tool2", "tool3"]
        error = ToolNotFoundError("missing_tool", available_tools=available)

        assert error.details["available_tools"] == available

    def test_to_dict_method(self):
        """Test converting error to dict."""
        error = ToolNotFoundError("missing_tool", available_tools=["tool1"])
        error_dict = error.to_dict()

        assert error_dict["error"] == "ToolNotFoundError"
        assert error_dict["code"] == "TOOL_NOT_FOUND"
        assert "missing_tool" in error_dict["message"]
        assert error_dict["details"]["tool_name"] == "missing_tool"
        assert error_dict["details"]["available_tools"] == ["tool1"]


class TestToolRateLimitedError:
    """Tests for ToolRateLimitedError."""

    def test_creation_basic(self):
        """Test creating basic rate limit error."""
        error = ToolRateLimitedError("api_tool")

        assert "api_tool" in str(error)
        assert "rate limited" in str(error).lower()
        assert error.code == ErrorCode.TOOL_RATE_LIMITED
        assert error.tool_name == "api_tool"

    def test_creation_with_retry_after(self):
        """Test creating error with retry_after hint."""
        error = ToolRateLimitedError("api_tool", retry_after=60.0)

        assert "retry after 60" in str(error).lower()
        assert error.retry_after == 60.0
        assert error.details["retry_after"] == 60.0

    def test_creation_with_limit(self):
        """Test creating error with limit info."""
        error = ToolRateLimitedError("api_tool", limit=100)

        assert error.limit == 100
        assert error.details["limit"] == 100


class TestToolCircuitOpenError:
    """Tests for ToolCircuitOpenError."""

    def test_creation_basic(self):
        """Test creating basic circuit open error."""
        error = ToolCircuitOpenError("failing_tool", failure_count=5)

        assert "failing_tool" in str(error)
        assert "circuit breaker is open" in str(error).lower()
        assert "failures: 5" in str(error).lower()
        assert error.code == ErrorCode.TOOL_CIRCUIT_OPEN
        assert error.tool_name == "failing_tool"
        assert error.failure_count == 5

    def test_creation_with_reset_timeout(self):
        """Test creating error with reset timeout."""
        error = ToolCircuitOpenError("failing_tool", failure_count=5, reset_timeout=30.0)

        assert "reset in 30" in str(error).lower()
        assert error.reset_timeout == 30.0
        assert error.details["reset_timeout"] == 30.0


class TestMCPErrors:
    """Tests for MCP-related errors."""

    def test_mcp_connection_error(self):
        """Test MCPConnectionError."""
        error = MCPConnectionError("notion_server", reason="Network timeout")

        assert "notion_server" in str(error)
        assert "Network timeout" in str(error)
        assert error.code == ErrorCode.MCP_CONNECTION_FAILED
        assert error.details["reason"] == "Network timeout"

    def test_mcp_connection_error_without_reason(self):
        """Test MCPConnectionError without reason."""
        error = MCPConnectionError("notion_server")

        assert "notion_server" in str(error)
        assert "Failed to connect" in str(error)
        assert error.code == ErrorCode.MCP_CONNECTION_FAILED

    def test_mcp_timeout_error(self):
        """Test MCPTimeoutError."""
        error = MCPTimeoutError("sqlite_server", operation="query_database", timeout=30.0)

        assert "sqlite_server" in str(error)
        assert "query_database" in str(error)
        assert "30" in str(error)
        assert error.code == ErrorCode.MCP_TIMEOUT
        assert error.details["operation"] == "query_database"
        assert error.details["timeout"] == 30.0

    def test_mcp_error_base_class(self):
        """Test MCPError base class."""
        error = MCPError(
            "Custom MCP error",
            code=ErrorCode.MCP_SERVER_ERROR,
            server_name="test_server",
            details={"extra": "info"},
        )

        assert str(error) == "Custom MCP error"
        assert error.code == ErrorCode.MCP_SERVER_ERROR
        assert error.details["server_name"] == "test_server"
        assert error.details["extra"] == "info"


class TestToolProcessorError:
    """Tests for ToolProcessorError base class."""

    def test_creation_with_defaults(self):
        """Test creating error with default values."""
        error = ToolProcessorError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.code == ErrorCode.TOOL_EXECUTION_FAILED  # Default code
        assert error.details == {}
        assert error.original_error is None

    def test_creation_with_original_error(self):
        """Test creating error with original exception."""
        original = ValueError("Original problem")
        error = ToolProcessorError(
            "Wrapper error",
            code=ErrorCode.TOOL_EXECUTION_FAILED,
            original_error=original,
        )

        assert error.original_error == original

        error_dict = error.to_dict()
        assert error_dict["original_error"]["type"] == "ValueError"
        assert error_dict["original_error"]["message"] == "Original problem"

    def test_to_dict_without_original_error(self):
        """Test to_dict when no original error exists."""
        error = ToolProcessorError("Test error", code=ErrorCode.TOOL_TIMEOUT)
        error_dict = error.to_dict()

        assert "original_error" not in error_dict
        assert error_dict["code"] == "TOOL_TIMEOUT"


class TestToolExecutionError:
    """Tests for ToolExecutionError."""

    def test_creation_with_original_error(self):
        """Test creating execution error with original exception."""
        original = RuntimeError("Execution failed")
        error = ToolExecutionError("my_tool", original_error=original)

        assert "my_tool" in str(error)
        assert "Execution failed" in str(error)
        assert error.tool_name == "my_tool"
        assert error.original_error == original

    def test_creation_with_details(self):
        """Test creating execution error with additional details."""
        error = ToolExecutionError(
            "my_tool",
            details={"attempt": 3, "error_type": "NetworkError"},
        )

        assert error.details["tool_name"] == "my_tool"
        assert error.details["attempt"] == 3
        assert error.details["error_type"] == "NetworkError"


class TestToolTimeoutError:
    """Tests for ToolTimeoutError."""

    def test_creation(self):
        """Test creating timeout error."""
        error = ToolTimeoutError("slow_tool", timeout=30.0, attempts=2)

        assert "slow_tool" in str(error)
        assert "30" in str(error)
        assert "attempts: 2" in str(error).lower()
        assert error.code == ErrorCode.TOOL_TIMEOUT
        assert error.tool_name == "slow_tool"
        assert error.timeout == 30.0
        assert error.attempts == 2

    def test_inherits_from_execution_error(self):
        """Test that ToolTimeoutError inherits from ToolExecutionError."""
        error = ToolTimeoutError("tool", timeout=10.0)
        assert isinstance(error, ToolExecutionError)


class TestToolValidationError:
    """Tests for ToolValidationError."""

    def test_creation_for_arguments(self):
        """Test creating validation error for arguments."""
        errors = {"field1": "required", "field2": "invalid type"}
        error = ToolValidationError("my_tool", errors=errors, validation_type="arguments")

        assert "my_tool" in str(error)
        assert "arguments" in str(error)
        assert error.tool_name == "my_tool"
        assert error.errors == errors
        assert error.validation_type == "arguments"
        assert error.code == ErrorCode.TOOL_VALIDATION_ERROR

    def test_creation_for_results(self):
        """Test creating validation error for results."""
        errors = {"output": "missing required field"}
        error = ToolValidationError("my_tool", errors=errors, validation_type="results")

        assert "results" in str(error)
        assert error.validation_type == "results"


class TestParserError:
    """Tests for ParserError."""

    def test_creation_basic(self):
        """Test creating basic parser error."""
        error = ParserError("Failed to parse XML")

        assert "Failed to parse XML" in str(error)
        assert error.code == ErrorCode.PARSER_ERROR
        assert error.parser_name is None
        assert error.input_sample is None

    def test_creation_with_parser_name(self):
        """Test creating parser error with parser name."""
        error = ParserError("Parse failed", parser_name="XMLParser")

        assert error.parser_name == "XMLParser"
        assert error.details["parser_name"] == "XMLParser"

    def test_creation_with_input_sample(self):
        """Test creating parser error with input sample."""
        long_input = "x" * 300
        error = ParserError("Parse failed", input_sample=long_input)

        # Should truncate to 200 chars
        assert len(error.details["input_sample"]) == 203  # 200 + "..."
        assert error.details["input_sample"].endswith("...")

    def test_creation_with_short_input_sample(self):
        """Test creating parser error with short input."""
        short_input = "short input"
        error = ParserError("Parse failed", input_sample=short_input)

        # Should not truncate
        assert error.details["input_sample"] == short_input
        assert not error.details["input_sample"].endswith("...")


class TestExceptionRaisingAndCatching:
    """Tests for raising and catching exceptions."""

    def test_raise_and_catch_specific_error(self):
        """Test raising and catching specific error types."""
        with pytest.raises(ToolNotFoundError) as exc_info:
            raise ToolNotFoundError("missing_tool")

        assert exc_info.value.tool_name == "missing_tool"

    def test_catch_as_base_class(self):
        """Test catching specific error as base class."""
        with pytest.raises(ToolProcessorError) as exc_info:
            raise ToolTimeoutError("slow_tool", timeout=10.0)

        assert exc_info.value.code == ErrorCode.TOOL_TIMEOUT

    def test_error_code_in_exception_handling(self):
        """Test using error codes in exception handling."""
        try:
            raise ToolNotFoundError("missing")
        except ToolProcessorError as e:
            assert e.code == ErrorCode.TOOL_NOT_FOUND
            error_dict = e.to_dict()
            assert error_dict["code"] == "TOOL_NOT_FOUND"


class TestToolNotFoundErrorWithTupleTools:
    """Tests for ToolNotFoundError with tuple format tools (lines 244-250, 257, 278)."""

    def test_with_tuple_format_tools(self):
        """Test creating error with tuple format (namespace, name) tools."""
        # Tuple format: list of (namespace, name) tuples
        available_tools = [
            ("default", "calculator"),
            ("default", "calendar"),
            ("utils", "formatter"),
        ]
        error = ToolNotFoundError(
            "calcuator",  # typo to get suggestions
            namespace="default",
            available_tools=available_tools,
        )

        # Should find similar tools
        assert "Did you mean" in str(error)
        assert error.details.get("suggestions") is not None
        assert len(error.details["suggestions"]) > 0

    def test_with_tuple_format_tools_exact_match_namespace(self):
        """Test similar tools are found within namespace."""
        available_tools = [
            ("default", "search_tool"),
            ("default", "search_api"),
            ("other", "different_tool"),
        ]
        error = ToolNotFoundError(
            "search_tol",  # typo
            namespace="default",
            available_tools=available_tools,
        )

        # Should suggest similar tools
        assert "suggestions" in error.details

    def test_with_tuple_format_no_similar_tools(self):
        """Test when no similar tools are found."""
        available_tools = [
            ("default", "completely_different"),
        ]
        error = ToolNotFoundError(
            "xyz123",  # no similarity
            namespace="default",
            available_tools=available_tools,
        )

        # No suggestions when nothing is similar
        assert "suggestions" not in error.details or len(error.details.get("suggestions", [])) == 0

    def test_with_string_format_similar_tools(self):
        """Test with string format tools that find similar matches."""
        available_tools = ["calculator", "calendar", "formatter"]
        error = ToolNotFoundError(
            "calcuator",  # typo
            available_tools=available_tools,
        )

        # Should find similar tools and add to message
        assert "Did you mean" in str(error)
        assert "suggestions" in error.details


class TestBulkheadFullError:
    """Tests for BulkheadFullError (lines 498-508)."""

    def test_creation_basic(self):
        """Test creating basic bulkhead full error."""
        error = BulkheadFullError(
            tool_name="api_tool",
            namespace="default",
            limit_type="tool",
            limit=10,
        )

        assert "api_tool" in str(error)
        assert "tool limit: 10" in str(error).lower()
        assert error.code == ErrorCode.BULKHEAD_FULL
        assert error.tool_name == "api_tool"
        assert error.namespace == "default"
        assert error.limit_type == "tool"
        assert error.limit == 10

    def test_creation_with_timeout(self):
        """Test creating bulkhead error with timeout."""
        error = BulkheadFullError(
            tool_name="api_tool",
            namespace="prod",
            limit_type="namespace",
            limit=50,
            timeout=5.0,
        )

        assert "after 5" in str(error).lower()
        assert error.timeout == 5.0
        assert error.details["timeout"] == 5.0

    def test_details_structure(self):
        """Test that details contain all expected fields."""
        error = BulkheadFullError(
            tool_name="my_tool",
            namespace="my_ns",
            limit_type="global",
            limit=100,
            timeout=10.0,
        )

        assert error.details["tool_name"] == "my_tool"
        assert error.details["namespace"] == "my_ns"
        assert error.details["limit_type"] == "global"
        assert error.details["limit"] == 100
        assert error.details["timeout"] == 10.0


class TestErrorInfoFromException:
    """Tests for ErrorInfo.from_exception method (line 597)."""

    def test_from_tool_processor_error(self):
        """Test creating ErrorInfo from ToolProcessorError subclass."""
        original_error = ToolNotFoundError("missing_tool")
        error_info = ErrorInfo.from_exception(original_error)

        assert error_info.code == ErrorCode.TOOL_NOT_FOUND
        assert error_info.category == ErrorCategory.NOT_FOUND
        assert "missing_tool" in error_info.message

    def test_from_rate_limited_error(self):
        """Test creating ErrorInfo from ToolRateLimitedError."""
        original_error = ToolRateLimitedError("api_tool", retry_after=60.0)
        error_info = ErrorInfo.from_exception(original_error)

        assert error_info.code == ErrorCode.TOOL_RATE_LIMITED
        assert error_info.category == ErrorCategory.RATE_LIMIT
        assert error_info.retryable is True

    def test_from_generic_exception(self):
        """Test creating ErrorInfo from generic exception."""
        original_error = ValueError("Something went wrong")
        error_info = ErrorInfo.from_exception(original_error)

        assert error_info.code == ErrorCode.TOOL_EXECUTION_FAILED
        assert error_info.category == ErrorCategory.EXECUTION
        assert error_info.message == "Something went wrong"
        assert error_info.details["exception_type"] == "ValueError"


class TestErrorInfoFromErrorString:
    """Tests for ErrorInfo.from_error_string method (lines 620, 628, 636)."""

    def test_rate_limit_pattern(self):
        """Test parsing 'rate limit' error string."""
        error_info = ErrorInfo.from_error_string(
            "Tool hit rate limit, try again later",
            tool_name="api_tool",
        )

        assert error_info.code == ErrorCode.TOOL_RATE_LIMITED
        assert error_info.category == ErrorCategory.RATE_LIMIT
        assert error_info.retryable is True
        assert error_info.details["tool_name"] == "api_tool"

    def test_circuit_open_pattern(self):
        """Test parsing 'circuit open' error string."""
        error_info = ErrorInfo.from_error_string(
            "Circuit breaker is open for this service",
            tool_name="failing_service",
        )

        assert error_info.code == ErrorCode.TOOL_CIRCUIT_OPEN
        assert error_info.category == ErrorCategory.CIRCUIT_OPEN
        assert error_info.retryable is True
        assert error_info.details["tool_name"] == "failing_service"

    def test_bulkhead_pattern(self):
        """Test parsing 'bulkhead' error string."""
        error_info = ErrorInfo.from_error_string(
            "Bulkhead capacity exceeded",
            tool_name="busy_tool",
        )

        assert error_info.code == ErrorCode.BULKHEAD_FULL
        assert error_info.category == ErrorCategory.BULKHEAD_FULL
        assert error_info.retryable is True

    def test_concurrency_pattern(self):
        """Test parsing 'concurrency' error string."""
        error_info = ErrorInfo.from_error_string(
            "Concurrency limit reached",
            tool_name="limited_tool",
        )

        assert error_info.code == ErrorCode.BULKHEAD_FULL
        assert error_info.category == ErrorCategory.BULKHEAD_FULL

    def test_without_tool_name(self):
        """Test parsing error string without tool name."""
        error_info = ErrorInfo.from_error_string("Rate limit exceeded")

        assert error_info.code == ErrorCode.TOOL_RATE_LIMITED
        assert error_info.details == {}
