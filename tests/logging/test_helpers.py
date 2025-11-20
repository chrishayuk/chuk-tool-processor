# tests/logging/test_helpers.py
"""
Tests for async logging helpers.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.logging.context import log_context
from chuk_tool_processor.logging.helpers import log_context_span, log_tool_call, request_logging


@pytest.mark.asyncio
async def test_log_context_span():
    """Test the log_context_span context manager."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Use the context manager with log_duration=False
        async with log_context_span("test_operation", log_duration=False):
            mock_logger.debug.assert_called_with("Starting %s", "test_operation")
            mock_logger.debug.reset_mock()

        # Should have logged completion without duration
        mock_logger.debug.assert_called_with("Completed %s", "test_operation")
        # No extra context with duration
        assert "extra" not in mock_logger.debug.call_args[1] or "duration" not in mock_logger.debug.call_args[1].get(
            "extra", {}
        ).get("context", {})


@pytest.mark.asyncio
async def test_log_context_span_nested():
    """Test nested log_context_span context managers restore previous context."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Use nested context managers
        async with log_context_span("outer_operation", {"outer": "data"}):
            outer_span_id = log_context.context["span_id"]
            outer_context = log_context.get_copy()
            assert outer_context["operation"] == "outer_operation"
            assert outer_context["outer"] == "data"

            # Nested span - saves previous context and creates new one
            async with log_context_span("inner_operation", {"inner": "data"}):
                inner_context = log_context.get_copy()
                assert inner_context["operation"] == "inner_operation"
                assert inner_context["inner"] == "data"
                # The context is updated, so outer data carries forward
                assert inner_context["outer"] == "data"
                # Span ID should be different
                assert inner_context["span_id"] != outer_span_id

            # After inner span completes, outer context should be restored
            restored_context = log_context.get_copy()
            assert restored_context["operation"] == "outer_operation"
            assert restored_context["outer"] == "data"
            assert restored_context["span_id"] == outer_span_id
            # Inner data should not be present after restoration
            assert "inner" not in restored_context


@pytest.mark.asyncio
async def test_log_context_span_with_exception():
    """Test log_context_span with an exception."""
    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.exception = MagicMock()

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.error = MagicMock()

    # Mock tool call and result with properly configured MagicMocks
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a start_time and end_time that are real datetime objects
    start_time = datetime.now(UTC) - timedelta(seconds=2)
    end_time = datetime.now(UTC)

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

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.error = MagicMock()

    # Mock tool call and result with properly configured MagicMocks
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a start_time and end_time that are real datetime objects
    start_time = datetime.now(UTC) - timedelta(seconds=1)
    end_time = datetime.now(UTC)

    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = None
    mock_result.error = "Test error message"
    # Use real datetime objects instead of MagicMocks
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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
    start_time = datetime.now(UTC) - timedelta(seconds=1)
    end_time = datetime.now(UTC)

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
    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
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


@pytest.mark.asyncio
async def test_log_tool_call_with_duration_exception():
    """Test log_tool_call when duration calculation fails."""

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a mock result where start_time and end_time raise TypeError
    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    mock_result.machine = "test-machine"
    mock_result.pid = 1234

    # Configure start_time and end_time to raise TypeError when subtracted
    mock_result.start_time = MagicMock()
    mock_result.end_time = MagicMock()
    # Make subtraction raise TypeError
    mock_result.end_time.__sub__ = MagicMock(side_effect=TypeError("Cannot subtract"))

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)

        # Should have logged success with duration 0.0
        mock_logger.debug.assert_called_once()
        args, kwargs = mock_logger.debug.call_args
        assert args[0] == "Tool %s succeeded in %.3fs"
        assert args[1] == "test_tool"
        assert args[2] == 0.0  # Duration should be 0.0 when calculation fails

        # Check context has duration 0.0
        ctx = kwargs["extra"]["context"]
        assert ctx["duration"] == 0.0


@pytest.mark.asyncio
async def test_log_tool_call_with_cached_exception():
    """Test log_tool_call when cached attribute access raises exception."""

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a mock result with proper datetime objects
    start_time = datetime.now(UTC) - timedelta(seconds=1)
    end_time = datetime.now(UTC)

    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234

    # Configure cached to be True but raise TypeError when checked in boolean context
    mock_cached = MagicMock()
    mock_cached.__bool__ = MagicMock(side_effect=TypeError("Cannot convert to bool"))
    mock_result.cached = mock_cached

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)

        # Should have logged success without cached field
        mock_logger.debug.assert_called_once()
        ctx = mock_logger.debug.call_args[1]["extra"]["context"]
        assert "cached" not in ctx


@pytest.mark.asyncio
async def test_log_tool_call_with_attempts_conversion_exception():
    """Test log_tool_call when attempts needs conversion but fails."""

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a mock result with proper datetime objects
    start_time = datetime.now(UTC) - timedelta(seconds=1)
    end_time = datetime.now(UTC)

    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234

    # Configure attempts to fail comparison but succeed int() conversion fails too
    mock_attempts = MagicMock()
    mock_attempts.__gt__ = MagicMock(side_effect=TypeError("Cannot compare"))
    mock_attempts.__int__ = MagicMock(side_effect=TypeError("Cannot convert to int"))
    mock_result.attempts = mock_attempts

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)

        # Should have logged success with attempts as-is (the MagicMock)
        mock_logger.debug.assert_called_once()
        ctx = mock_logger.debug.call_args[1]["extra"]["context"]
        assert "attempts" in ctx
        assert ctx["attempts"] is mock_attempts


@pytest.mark.asyncio
async def test_log_tool_call_with_stream_id_exception():
    """Test log_tool_call when stream_id attribute access raises exception."""

    # Mock the logger
    mock_logger = MagicMock()
    mock_logger.debug = MagicMock()

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.tool = "test_tool"
    mock_tool_call.arguments = {"arg1": "value1"}

    # Create a mock result with proper datetime objects
    start_time = datetime.now(UTC) - timedelta(seconds=1)
    end_time = datetime.now(UTC)

    mock_result = MagicMock()
    mock_result.tool = "test_tool"
    mock_result.result = {"output": "test_output"}
    mock_result.error = None
    mock_result.start_time = start_time
    mock_result.end_time = end_time
    mock_result.machine = "test-machine"
    mock_result.pid = 1234

    # Configure stream_id to be truthy but raise TypeError when checked
    mock_stream_id = MagicMock()
    mock_stream_id.__bool__ = MagicMock(side_effect=TypeError("Cannot convert to bool"))
    mock_result.stream_id = mock_stream_id

    with patch("chuk_tool_processor.logging.helpers.get_logger", return_value=mock_logger):
        # Log the tool call
        await log_tool_call(mock_tool_call, mock_result)

        # Should have logged success without stream_id field
        mock_logger.debug.assert_called_once()
        ctx = mock_logger.debug.call_args[1]["extra"]["context"]
        assert "stream_id" not in ctx
        assert "is_partial" not in ctx
