# tests/logging/test_helpers.py
"""
Tests for async logging helpers.
"""
import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from chuk_tool_processor.logging.helpers import log_context_span, request_logging, log_tool_call
from chuk_tool_processor.logging.context import log_context


@pytest.mark.asyncio
async def test_log_context_span():
    """Test the log_context_span context manager."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager
        async with log_context_span("test_operation", {"extra": "data"}):
            # Check context was set up
            assert "span_id" in log_context.context
            assert log_context.context["operation"] == "test_operation"
            assert log_context.context["extra"] == "data"
            assert "start_time" in log_context.context
            
            # Should have logged start
            mock_logger.debug.assert_called_with("Starting %s", "test_operation")
            mock_logger.debug.reset_mock()
        
        # Should have logged completion
        mock_logger.debug.assert_called_once()
        args, kwargs = mock_logger.debug.call_args
        assert args[0] == "Completed %s"
        assert args[1] == "test_operation"
        assert "context" in kwargs["extra"]
        assert "duration" in kwargs["extra"]["context"]


@pytest.mark.asyncio
async def test_log_context_span_no_duration():
    """Test log_context_span without duration logging."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager with log_duration=False
        async with log_context_span("test_operation", log_duration=False):
            mock_logger.debug.assert_called_with("Starting %s", "test_operation")
            mock_logger.debug.reset_mock()
        
        # Should have logged completion without duration
        mock_logger.debug.assert_called_with("Completed %s", "test_operation")
        # No extra context with duration
        assert "extra" not in mock_logger.debug.call_args[1] or \
               "duration" not in mock_logger.debug.call_args[1].get("extra", {}).get("context", {})


@pytest.mark.asyncio
async def test_log_context_span_with_exception():
    """Test log_context_span with an exception."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager with an exception
        with pytest.raises(ValueError):
            async with log_context_span("test_operation"):
                raise ValueError("Test error")
        
        # Should have logged the exception
        mock_logger.exception.assert_called_once()
        args, kwargs = mock_logger.exception.call_args
        assert args[0] == "Error in %s: %s"
        assert args[1] == "test_operation"
        assert isinstance(args[2], ValueError)
        assert "context" in kwargs["extra"]
        assert "duration" in kwargs["extra"]["context"]


@pytest.mark.asyncio
async def test_request_logging():
    """Test the request_logging context manager."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager with specific request ID
        async with request_logging("test-request") as rid:
            # Should return the request ID
            assert rid == "test-request"
            
            # Should have started request in context
            assert log_context.request_id == "test-request"
            assert log_context.context["request_id"] == "test-request"
            
            # Should have logged start
            mock_logger.debug.assert_called_with("Starting request %s", "test-request")
            mock_logger.debug.reset_mock()
        
        # Should have logged completion
        mock_logger.debug.assert_called_once()
        args, kwargs = mock_logger.debug.call_args
        assert args[0] == "Completed request %s"
        assert args[1] == "test-request"
        assert "context" in kwargs["extra"]
        assert "duration" in kwargs["extra"]["context"]
        
        # Should have cleared context
        assert log_context.request_id is None


@pytest.mark.asyncio
async def test_request_logging_auto_id():
    """Test request_logging with auto-generated ID."""
    # Mock the logger
    mock_logger = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager without specific request ID
        async with request_logging() as rid:
            # Should have generated an ID
            assert rid is not None
            assert len(rid) > 10  # UUID should be reasonably long
            
            # Context should have the ID
            assert log_context.request_id == rid
            assert log_context.context["request_id"] == rid


@pytest.mark.asyncio
async def test_request_logging_with_exception():
    """Test request_logging with an exception."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Use the context manager with an exception
        with pytest.raises(ValueError):
            async with request_logging("test-request"):
                raise ValueError("Test error")
        
        # Should have logged the exception
        mock_logger.exception.assert_called_once()
        args, kwargs = mock_logger.exception.call_args
        assert args[0] == "Error in request %s: %s"
        assert args[1] == "test-request"
        assert isinstance(args[2], ValueError)
        assert "context" in kwargs["extra"]
        assert "duration" in kwargs["extra"]["context"]
        
        # Should have cleared context despite exception
        assert log_context.request_id is None


@pytest.mark.asyncio
async def test_log_tool_call_success():
    """Test log_tool_call with successful result."""
    from datetime import datetime, timezone, timedelta
    
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.error = MagicMock()
    
    # Mock tool call and result with properly configured MagicMocks
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}
    
    # Create a start_time and end_time that are real datetime objects
    start_time = datetime.now(timezone.utc) - timedelta(seconds=2)
    end_time = datetime.now(timezone.utc)
    
    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    # Use real datetime objects instead of MagicMocks
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234
    # Configure attempts to return an integer rather than a MagicMock
    mock_result.attempts = 1
    mock_result.cached = False
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)
        
        # Should have logged success
        mock_logger.debug.assert_called_once()
        mock_logger.error.assert_not_called()
        
        args, kwargs = mock_logger.debug.call_args
        assert args[0] == "Tool %s succeeded in %.3fs"
        assert args[1] == "test_tool"
        assert isinstance(args[2], float)
        assert args[2] >= 1.9  # Should be close to 2 seconds
        
        # Check context
        assert "context" in kwargs["extra"]
        ctx = kwargs["extra"]["context"]
        assert ctx["tool"] == "test_tool"
        assert ctx["arguments"] == {"arg1": "value1"}
        assert ctx["result"] == {"output": "test_output"}
        assert ctx["error"] is None
        assert isinstance(ctx["duration"], float)
        assert ctx["machine"] == "test-machine"
        assert ctx["pid"] == 1234


@pytest.mark.asyncio
async def test_log_tool_call_error():
    """Test log_tool_call with error result."""
    from datetime import datetime, timezone, timedelta
    
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.error = MagicMock()
    
    # Mock tool call and result with properly configured MagicMocks
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}
    
    # Create a start_time and end_time that are real datetime objects
    start_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    end_time = datetime.now(timezone.utc)
    
    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = None
    mock_result.error = "Test error message"
    # Use real datetime objects instead of MagicMocks
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234
    
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)
        
        # Should have logged error
        mock_logger.error.assert_called_once()
        mock_logger.debug.assert_not_called()
        
        args, kwargs = mock_logger.error.call_args
        assert args[0] == "Tool %s failed: %s"
        assert args[1] == "test_tool"
        assert args[2] == "Test error message"
        
        # Check context
        assert "context" in kwargs["extra"]
        ctx = kwargs["extra"]["context"]
        assert ctx["tool"] == "test_tool"
        assert ctx["arguments"] == {"arg1": "value1"}
        assert ctx["result"] is None
        assert ctx["error"] == "Test error message"


@pytest.mark.asyncio
async def test_log_tool_call_with_optional_fields():
    """Test log_tool_call with optional fields."""
    from datetime import datetime, timezone, timedelta
    
    # Mock the logger properly
    mock_logger = MagicMock()
    mock_debug = MagicMock()
    mock_error = MagicMock()
    mock_logger.debug = mock_debug
    mock_logger.error = mock_error
    
    # Mock tool call and result with properly configured MagicMocks
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}
    
    # Create a start_time and end_time that are real datetime objects
    start_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    end_time = datetime.now(timezone.utc)
    
    # Create a mock result with proper attributes
    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234
    
    # Configure special attributes that will be checked
    mock_result.cached = True
    mock_result.attempts = 3
    mock_result.stream_id = "stream-123"
    mock_result.is_partial = True
    
    # Get logger and call helper
    with patch('chuk_tool_processor.logging.helpers.get_logger', return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)
        
        # Check basic debug was logged
        mock_debug.assert_called_once()
        args, kwargs = mock_debug.call_args
        
        # First arg is format string, second should be tool name
        assert args[1] == "test_tool"
        
        # Check context was included
        assert "extra" in kwargs
        assert "context" in kwargs["extra"]
        ctx = kwargs["extra"]["context"]
        
        # Verify optional fields were included
        assert ctx["cached"] is True
        assert "attempts" in ctx
        assert ctx["attempts"] == 3
        assert ctx["stream_id"] == "stream-123"
        assert ctx["is_partial"] is True