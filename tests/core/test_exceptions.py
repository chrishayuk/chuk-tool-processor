# tests/chuk_tool_processor/core/test_exceptions.py
import pytest
from chuk_tool_processor.core.exceptions import (
    ToolProcessorError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
    ParserError
)

class TestToolProcessorError:
    def test_base_exception(self):
        """Test that ToolProcessorError works as a base exception."""
        # When
        exception = ToolProcessorError("Test error message")
        
        # Then
        assert isinstance(exception, Exception)
        assert str(exception) == "Test error message"


class TestToolNotFoundError:
    def test_creation(self):
        """Test ToolNotFoundError creation and message formatting."""
        # When
        tool_name = "test_tool"
        exception = ToolNotFoundError(tool_name)
        
        # Then
        assert isinstance(exception, ToolProcessorError)
        assert exception.tool_name == tool_name
        assert str(exception) == f"Tool '{tool_name}' not found in registry"


class TestToolExecutionError:
    def test_without_original_error(self):
        """Test ToolExecutionError creation without an original error."""
        # When
        tool_name = "test_tool"
        exception = ToolExecutionError(tool_name)
        
        # Then
        assert isinstance(exception, ToolProcessorError)
        assert exception.tool_name == tool_name
        assert exception.original_error is None
        assert str(exception) == f"Tool '{tool_name}' execution failed"
    
    def test_with_original_error(self):
        """Test ToolExecutionError creation with an original error."""
        # Given
        original_error = ValueError("Invalid value")
        
        # When
        tool_name = "test_tool"
        exception = ToolExecutionError(tool_name, original_error)
        
        # Then
        assert isinstance(exception, ToolProcessorError)
        assert exception.tool_name == tool_name
        assert exception.original_error == original_error
        assert str(exception) == f"Tool '{tool_name}' execution failed: {str(original_error)}"


class TestToolTimeoutError:
    def test_creation(self):
        """Test ToolTimeoutError creation and message formatting."""
        # When
        tool_name = "test_tool"
        timeout = 10.5
        exception = ToolTimeoutError(tool_name, timeout)
        
        # Then
        assert isinstance(exception, ToolExecutionError)
        assert exception.tool_name == tool_name
        assert exception.timeout == timeout
        assert str(exception) == f"Tool '{tool_name}' execution failed: Execution timed out after {timeout}s"


class TestToolValidationError:
    def test_creation(self):
        """Test ToolValidationError creation and message formatting."""
        # Given
        errors = {"param1": "Missing required parameter", "param2": "Invalid type"}
        
        # When
        tool_name = "test_tool"
        exception = ToolValidationError(tool_name, errors)
        
        # Then
        assert isinstance(exception, ToolProcessorError)
        assert exception.tool_name == tool_name
        assert exception.errors == errors
        assert str(exception) == f"Validation failed for tool '{tool_name}': {errors}"


class TestParserError:
    def test_creation(self):
        """Test ParserError creation."""
        # When
        exception = ParserError("Failed to parse tool call")
        
        # Then
        assert isinstance(exception, ToolProcessorError)
        assert str(exception) == "Failed to parse tool call"


class TestExceptionHierarchy:
    def test_inheritance_hierarchy(self):
        """Test that the exception inheritance hierarchy is correct."""
        # Base exception
        assert issubclass(ToolProcessorError, Exception)
        
        # Direct subclasses of ToolProcessorError
        assert issubclass(ToolNotFoundError, ToolProcessorError)
        assert issubclass(ToolExecutionError, ToolProcessorError)
        assert issubclass(ToolValidationError, ToolProcessorError)
        assert issubclass(ParserError, ToolProcessorError)
        
        # ToolTimeoutError is a subclass of ToolExecutionError
        assert issubclass(ToolTimeoutError, ToolExecutionError)
        assert issubclass(ToolTimeoutError, ToolProcessorError)


class TestExceptionRaising:
    def test_raise_tool_not_found_error(self):
        """Test raising ToolNotFoundError."""
        # When/Then
        with pytest.raises(ToolNotFoundError) as excinfo:
            raise ToolNotFoundError("missing_tool")
        
        assert "missing_tool" in str(excinfo.value)
    
    def test_raise_tool_execution_error(self):
        """Test raising ToolExecutionError."""
        # When/Then
        with pytest.raises(ToolExecutionError) as excinfo:
            raise ToolExecutionError("failed_tool", ValueError("Bad value"))
        
        assert "failed_tool" in str(excinfo.value)
        assert "Bad value" in str(excinfo.value)
    
    def test_raise_tool_timeout_error(self):
        """Test raising ToolTimeoutError."""
        # When/Then
        with pytest.raises(ToolTimeoutError) as excinfo:
            raise ToolTimeoutError("slow_tool", 30.0)
        
        assert "slow_tool" in str(excinfo.value)
        assert "30.0s" in str(excinfo.value)
        
        # Should also be caught by ToolExecutionError
        with pytest.raises(ToolExecutionError):
            raise ToolTimeoutError("slow_tool", 30.0)
    
    def test_raise_tool_validation_error(self):
        """Test raising ToolValidationError."""
        # When/Then
        errors = {"field": "Invalid type"}
        with pytest.raises(ToolValidationError) as excinfo:
            raise ToolValidationError("invalid_tool", errors)
        
        assert "invalid_tool" in str(excinfo.value)
        assert "Invalid type" in str(excinfo.value)
    
    def test_raise_parser_error(self):
        """Test raising ParserError."""
        # When/Then
        with pytest.raises(ParserError) as excinfo:
            raise ParserError("Malformed JSON")
        
        assert "Malformed JSON" in str(excinfo.value)


class TestExceptionCatching:
    def test_catch_specific_exceptions(self):
        """Test catching specific exceptions."""
        # Given
        exceptions = [
            ToolNotFoundError("tool1"),
            ToolExecutionError("tool2"),
            ToolTimeoutError("tool3", 5.0),
            ToolValidationError("tool4", {"field": "error"}),
            ParserError("Parse error")
        ]
        
        # When/Then
        for exception in exceptions:
            try:
                raise exception
            except ToolProcessorError as e:
                assert str(e) == str(exception)
    
    def test_catch_subclass_as_parent(self):
        """Test catching a subclass exception as its parent type."""
        # Given
        timeout_error = ToolTimeoutError("slow_tool", 10.0)
        
        # When/Then
        try:
            raise timeout_error
        except ToolExecutionError as e:
            assert isinstance(e, ToolTimeoutError)
            assert e.tool_name == "slow_tool"
            assert e.timeout == 10.0