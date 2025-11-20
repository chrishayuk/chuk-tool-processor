# tests/logging/test_context.py
"""
Tests for the async-native logging context.
"""

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.logging.context import (
    LibraryLoggingManager,
    LibraryShutdownFilter,
    LogContext,
    get_logger,
    log_context,
)


@pytest.mark.asyncio
async def test_log_context_init():
    """Test that a new context starts empty."""
    context = LogContext()
    assert context.context == {}
    assert context.request_id is None


@pytest.mark.asyncio
async def test_log_context_update():
    """Test updating the context."""
    context = LogContext()
    context.update({"key": "value"})
    assert context.context == {"key": "value"}

    # Add more data
    context.update({"another": "value2"})
    assert context.context == {"key": "value", "another": "value2"}


@pytest.mark.asyncio
async def test_log_context_clear():
    """Test clearing the context."""
    context = LogContext()
    context.update({"key": "value"})
    assert context.context != {}

    context.clear()
    assert context.context == {}


@pytest.mark.asyncio
async def test_log_context_get_copy():
    """Test getting a copy of the context."""
    context = LogContext()
    context.update({"key": "value"})

    # Get a copy
    copy = context.get_copy()
    assert copy == {"key": "value"}

    # Modify the copy
    copy["new"] = "data"

    # Original should be unchanged
    assert context.context == {"key": "value"}


@pytest.mark.asyncio
async def test_log_context_request_id():
    """Test request ID management."""
    context = LogContext()

    # Start with specific ID
    rid = context.start_request("test-request")
    assert rid == "test-request"
    assert context.request_id == "test-request"
    assert context.context.get("request_id") == "test-request"

    # End request
    context.end_request()
    assert context.request_id is None
    assert context.context == {}

    # Auto-generated ID
    rid = context.start_request()
    assert rid is not None
    assert len(rid) > 10  # UUID should be reasonably long
    assert context.request_id == rid


@pytest.mark.asyncio
async def test_log_context_async_isolation():
    """Test that context is isolated between async tasks."""
    context = log_context  # Use the global instance

    # Clear any existing context
    context.clear()

    async def task1():
        context.update({"task": "task1"})
        await asyncio.sleep(0.1)
        return context.context

    async def task2():
        context.update({"task": "task2"})
        await asyncio.sleep(0.1)
        return context.context

    # Run tasks concurrently
    t1 = asyncio.create_task(task1())
    t2 = asyncio.create_task(task2())

    result1 = await t1
    result2 = await t2

    # Each task should have its own context
    assert result1 == {"task": "task1"}
    assert result2 == {"task": "task2"}


@pytest.mark.asyncio
async def test_context_scope():
    """Test the async context scope."""
    context = log_context

    # Set initial data
    context.clear()
    context.update({"initial": "value"})

    # Use context scope
    async with context.context_scope(key="value", another="data") as ctx:
        assert ctx == {"initial": "value", "key": "value", "another": "data"}
        assert context.context == {"initial": "value", "key": "value", "another": "data"}

    # After scope, should revert to original
    assert context.context == {"initial": "value"}


@pytest.mark.asyncio
async def test_request_scope():
    """Test the async request scope."""
    context = log_context
    context.clear()

    # Use request scope
    async with context.request_scope("test-req") as rid:
        assert rid == "test-req"
        assert context.request_id == "test-req"

        # Add other data
        context.update({"data": "value"})
        assert context.context == {"request_id": "test-req", "data": "value"}

    # After scope, should be cleared
    assert context.request_id is None
    assert context.context == {}


@pytest.mark.asyncio
async def test_structured_adapter():
    """Test the StructuredAdapter for logging."""
    # Create a mock for the underlying logger and its info method
    mock_logger = MagicMock()
    mock_info = MagicMock()
    mock_logger.info = mock_info

    # Set up context BEFORE creating the adapter
    log_context.clear()
    log_context.update({"test": "data", "request_id": "test-123"})

    # The key is to patch logging.getLogger BEFORE creating the adapter
    with patch("logging.getLogger", return_value=mock_logger):
        # FIRST set up the mock and THEN create the adapter
        adapter = get_logger("test")

        # Log a message
        adapter.info("Test message")

        # Verify the call was made to our mock
        mock_info.assert_called_once()

        # Check args and kwargs for correct context
        args, kwargs = mock_info.call_args
        assert args[0] == "Test message"
        assert "extra" in kwargs
        assert "context" in kwargs["extra"]
        assert kwargs["extra"]["context"]["test"] == "data"
        assert kwargs["extra"]["context"]["request_id"] == "test-123"


def test_library_shutdown_filter():
    """Test LibraryShutdownFilter filtering logic."""
    filter_instance = LibraryShutdownFilter()

    # Test filtering known error patterns
    error_record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Task error during shutdown: Attempted to exit cancel scope in a different task",
        args=(),
        exc_info=None,
    )
    assert filter_instance.filter(error_record) is False

    # Test filtering cancel scope warning
    warning_record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="Warning: cancel scope in a different task",
        args=(),
        exc_info=None,
    )
    assert filter_instance.filter(warning_record) is False

    # Test non-matching pattern (should pass through)
    normal_record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Normal log message",
        args=(),
        exc_info=None,
    )
    assert filter_instance.filter(normal_record) is True

    # Test partial match (should pass through)
    partial_record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Some other error message",
        args=(),
        exc_info=None,
    )
    assert filter_instance.filter(partial_record) is True


def test_library_logging_manager_duplicate_filter():
    """Test that LibraryLoggingManager doesn't add duplicate filters."""
    manager = LibraryLoggingManager()
    root_logger = logging.getLogger()

    # Get initial filter count
    initial_filter_count = len([f for f in root_logger.filters if isinstance(f, LibraryShutdownFilter)])

    # Call initialize multiple times
    manager.initialize()
    manager.initialize()
    manager.initialize()

    # Filter count should not increase
    final_filter_count = len([f for f in root_logger.filters if isinstance(f, LibraryShutdownFilter)])
    assert final_filter_count == initial_filter_count


@pytest.mark.asyncio
async def test_context_scope_with_exception():
    """Test context scope exception handling."""
    context = log_context
    context.clear()
    context.update({"initial": "value"})

    # Test that exception propagates but context is restored
    with pytest.raises(ValueError):
        async with context.context_scope(temp="data"):
            assert context.context == {"initial": "value", "temp": "data"}
            raise ValueError("Test error")

    # Context should be restored even after exception
    assert context.context == {"initial": "value"}


@pytest.mark.asyncio
async def test_structured_adapter_critical():
    """Test the critical method of StructuredAdapter."""
    mock_logger = MagicMock()
    mock_critical = MagicMock()
    mock_logger.critical = mock_critical

    log_context.clear()
    log_context.update({"severity": "high"})

    with patch("logging.getLogger", return_value=mock_logger):
        adapter = get_logger("test")
        adapter.critical("Critical error")

        mock_critical.assert_called_once()
        args, kwargs = mock_critical.call_args
        assert args[0] == "Critical error"
        assert "extra" in kwargs
        assert kwargs["extra"]["context"]["severity"] == "high"


@pytest.mark.asyncio
async def test_structured_adapter_all_log_levels():
    """Test all log level methods of StructuredAdapter."""
    mock_logger = MagicMock()
    log_context.clear()
    log_context.update({"test": "data"})

    with patch("logging.getLogger", return_value=mock_logger):
        adapter = get_logger("test")

        # Test debug
        adapter.debug("Debug message")
        mock_logger.debug.assert_called_once()
        args, kwargs = mock_logger.debug.call_args
        assert args[0] == "Debug message"
        assert kwargs["extra"]["context"]["test"] == "data"

        # Test warning
        adapter.warning("Warning message")
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert args[0] == "Warning message"
        assert kwargs["extra"]["context"]["test"] == "data"

        # Test error
        adapter.error("Error message")
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert args[0] == "Error message"
        assert kwargs["extra"]["context"]["test"] == "data"

        # Test exception
        adapter.exception("Exception message")
        mock_logger.exception.assert_called_once()
        args, kwargs = mock_logger.exception.call_args
        assert args[0] == "Exception message"
        assert kwargs["exc_info"] is True
        assert kwargs["extra"]["context"]["test"] == "data"


@pytest.mark.asyncio
async def test_async_context_manager_exception_handling():
    """Test AsyncContextManagerWrapper exception handling paths."""
    context = log_context
    context.clear()

    # Test case 1: Generator that catches and continues after exception
    async def exception_continuing_gen():
        try:
            context.update({"temp": "data"})
            yield context.context
        except ValueError:
            # Catch exception but continue the generator
            context.update({"exception_handled": True})
            # Yield again to not raise StopAsyncIteration
            yield

    from chuk_tool_processor.logging.context import AsyncContextManagerWrapper

    wrapper1 = AsyncContextManagerWrapper(exception_continuing_gen())
    result = await wrapper1.__aenter__()
    assert result == {"temp": "data"}

    # Exit with exception - generator continues, so should return True (suppressed)
    exception_suppressed = await wrapper1.__aexit__(ValueError, ValueError("test"), None)
    assert exception_suppressed is True

    # Test case 2: Generator that raises StopAsyncIteration when exception is thrown
    async def exception_stopping_gen():
        context.update({"temp2": "data2"})
        yield context.context
        # After yield, if exception is thrown, generator will raise StopAsyncIteration

    wrapper2 = AsyncContextManagerWrapper(exception_stopping_gen())
    await wrapper2.__aenter__()

    # Exit with exception - when generator doesn't catch exception, it propagates
    # This should raise the exception (not suppress it)
    with pytest.raises(ValueError):
        await wrapper2.__aexit__(ValueError, ValueError("test"), None)

    # Test case 3: Generator that catches exception and immediately stops (raises StopAsyncIteration)
    async def exception_stopping_immediately_gen():
        try:
            context.update({"temp3": "data3"})
            yield context.context
        except ValueError:
            # Catch the exception but don't yield again - this will cause StopAsyncIteration
            # when the generator finishes
            return

    wrapper3 = AsyncContextManagerWrapper(exception_stopping_immediately_gen())
    await wrapper3.__aenter__()

    # Exit with exception - generator catches it but immediately stops (returns False)
    exception_suppressed = await wrapper3.__aexit__(ValueError, ValueError("test"), None)
    assert exception_suppressed is False
