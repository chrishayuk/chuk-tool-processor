# tests/logging/test_metrics.py
"""
Tests for the async metrics logger.
"""
import asyncio
from unittest.mock import patch, MagicMock, ANY

import pytest

from chuk_tool_processor.logging.metrics import MetricsLogger, metrics


@pytest.mark.asyncio
async def test_metrics_logger_initialization():
    """Test that MetricsLogger initializes correctly."""
    # Create a new metrics logger
    with patch('chuk_tool_processor.logging.metrics.get_logger') as mock_get_logger:
        logger = MetricsLogger()
        
        # Should have called get_logger with the right name
        mock_get_logger.assert_called_once_with("chuk_tool_processor.metrics")


@pytest.mark.asyncio
async def test_log_tool_execution():
    """Test logging tool execution metrics."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Direct patch to make sure we're patching the right thing
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Create metrics logger
        logger = MetricsLogger()
        logger.logger = mock_logger  # Explicitly set the logger
        
        # Log failed tool execution
        await logger.log_tool_execution(
            tool="test_tool",
            success=False,
            duration=0.5,
            error="Test error message",
            attempts=3
        )
        
        # Check context
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        ctx = kwargs["extra"]["context"]
        assert ctx["success"] is False
        assert ctx["error"] == "Test error message"
        assert ctx["attempts"] == 3


@pytest.mark.asyncio
async def test_global_metrics_instance():
    """Test that the global metrics instance works correctly."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Replace the metrics logger with our mock
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Need to directly access and patch the global metrics instance
        original_logger = metrics.logger
        metrics.logger = mock_logger
        
        try:
            # Use the global metrics instance
            await metrics.log_tool_execution(
                tool="global_test",
                success=True,
                duration=1.0
            )
            
            # Check logging
            mock_logger.info.assert_called_once()
            args, kwargs = mock_logger.info.call_args
            assert "global_test" in args[0]
            assert kwargs["extra"]["context"]["tool"] == "global_test"
        finally:
            # Restore original logger
            metrics.logger = original_logger


@pytest.mark.asyncio
async def test_concurrent_metrics_logging():
    """Test concurrent metrics logging with multiple tasks."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Direct patch to make sure we're patching the right thing
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Create metrics logger
        logger = MetricsLogger()
        logger.logger = mock_logger  # Explicitly set the logger
        
        # Create tasks to log metrics concurrently
        async def log_task(i):
            await logger.log_tool_execution(
                tool=f"tool_{i}",
                success=i % 2 == 0,  # Alternate success/failure
                duration=i / 10,
                error="Error" if i % 2 == 1 else None,
                attempts=i
            )
            
        # Run 5 concurrent logging tasks
        tasks = [log_task(i) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # Should have logged 5 times
        assert mock_logger.info.call_count == 5
        
        # Reset the mock before the additional call
        mock_logger.info.reset_mock()
        
        # Now make a separate call with a clean mock state
        await logger.log_tool_execution(
            tool="test_tool",
            success=True,
            duration=0.123,
            error=None,
            cached=True,
            attempts=2
        )
        
        # Check that this specific call was logged once
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        assert "test_tool" in args[0]
        assert kwargs["extra"]["context"]["tool"] == "test_tool"
        
        # Check that all tools were logged across all calls
        # Reset the mock again for clean state
        mock_logger.info.reset_mock()
        
        # Log each tool again to get a fresh set of calls
        for i in range(5):
            await logger.log_tool_execution(
                tool=f"tool_{i}",
                success=i % 2 == 0,
                duration=i / 10,
                error="Error" if i % 2 == 1 else None,
                attempts=i
            )
            
        # Now check the tool names
        tool_names = set()
        for call in mock_logger.info.call_args_list:
            args, kwargs = call
            tool_name = kwargs["extra"]["context"]["tool"]
            tool_names.add(tool_name)
            
        assert tool_names == {"tool_0", "tool_1", "tool_2", "tool_3", "tool_4"}

@pytest.mark.asyncio
async def test_log_parser_metric():
    """Test logging parser metrics."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Direct patch to make sure we're patching the right thing
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Create metrics logger
        logger = MetricsLogger()
        logger.logger = mock_logger  # Explicitly set the logger
        
        # Log metrics
        await logger.log_parser_metric(
            parser="xml_parser",
            success=True,
            duration=0.456,
            num_calls=5
        )
        
        # Check logging
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        assert "xml_parser" in args[0]
        assert "context" in kwargs["extra"]
        ctx = kwargs["extra"]["context"]
        assert ctx["metric_type"] == "parser"
        assert ctx["parser"] == "xml_parser"
        assert ctx["success"] is True
        assert ctx["duration"] == 0.456
        assert ctx["num_calls"] == 5


@pytest.mark.asyncio
async def test_log_registry_metric():
    """Test logging registry metrics."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Direct patch to make sure we're patching the right thing
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Create metrics logger
        logger = MetricsLogger()
        logger.logger = mock_logger  # Explicitly set the logger
        
        # Log metrics
        await logger.log_registry_metric(
            operation="register",
            success=True,
            duration=0.789,
            tool="test_tool",
            namespace="math"
        )
        
        # Check logging
        mock_logger.info.assert_called_once()
        args, kwargs = mock_logger.info.call_args
        assert "register" in args[0]
        assert "context" in kwargs["extra"]
        ctx = kwargs["extra"]["context"]
        assert ctx["metric_type"] == "registry"
        assert ctx["operation"] == "register"
        assert ctx["success"] is True
        assert ctx["duration"] == 0.789
        assert ctx["tool"] == "test_tool"
        assert ctx["namespace"] == "math"


@pytest.mark.asyncio
async def test_failed_operation_metrics():
    """Test logging metrics for failed operations."""
    # Mock the logger
    mock_logger = MagicMock()
    
    # Direct patch to make sure we're patching the right thing
    with patch('chuk_tool_processor.logging.metrics.get_logger', return_value=mock_logger):
        # Create metrics logger
        logger = MetricsLogger()
        logger.logger = mock_logger  # Explicitly set the