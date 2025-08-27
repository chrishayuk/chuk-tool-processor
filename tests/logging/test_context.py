# tests/logging/test_context.py
"""
Tests for the async-native logging context.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.logging.context import LogContext, get_logger, log_context


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
