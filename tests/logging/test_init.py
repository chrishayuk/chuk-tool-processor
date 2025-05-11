# tests/logging/test_init.py
"""
Tests for the logging package initialization.
"""
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from chuk_tool_processor.logging import setup_logging, get_logger

@pytest.mark.asyncio
async def test_setup_logging_default():
    """Test setting up logging with default configuration."""
    # Mock root logger and internal logger
    mock_root_logger = MagicMock()
    mock_internal_logger = MagicMock()
    
    # This is critical - configure the handlers collection properly
    mock_root_logger.handlers = [MagicMock()]
    
    def mock_getlogger(name):
        if name == "chuk_tool_processor":
            return mock_root_logger
        elif name == "chuk_tool_processor.logging":
            return mock_internal_logger
        return MagicMock()
    
    with patch('logging.getLogger', side_effect=mock_getlogger):
        # Setup logging
        await setup_logging()
        
        # Now removeHandler should have been called since we added a mock handler
        mock_root_logger.removeHandler.assert_called()
        
        # Should have set level to INFO
        mock_root_logger.setLevel.assert_called_with(logging.INFO)
        
        # Should have added a console handler
        mock_root_logger.addHandler.assert_called()
        
        # Internal logger should have logged startup
        mock_internal_logger.info.assert_called()


@pytest.mark.asyncio
async def test_setup_logging_custom_level():
    """Test setting up logging with custom level."""
    # Mock root logger
    mock_root_logger = MagicMock()
    
    with patch('logging.getLogger', return_value=mock_root_logger) as mock_get_logger:
        # Setup logging with DEBUG level
        await setup_logging(level=logging.DEBUG)
        
        # Should have set level to DEBUG
        mock_root_logger.setLevel.assert_called_with(logging.DEBUG)


@pytest.mark.asyncio
async def test_setup_logging_with_file():
    """Test setting up logging with a log file."""
    # Mock root logger
    mock_root_logger = MagicMock()
    mock_file_handler = MagicMock()
    
    with (
        patch('logging.getLogger', return_value=mock_root_logger) as mock_get_logger,
        patch('logging.FileHandler', return_value=mock_file_handler) as mock_file_handler_cls,
        tempfile.NamedTemporaryFile() as temp_file
    ):
        # Setup logging with file
        await setup_logging(log_file=temp_file.name)
        
        # Should have created a FileHandler
        mock_file_handler_cls.assert_called_with(temp_file.name)
        
        # Should have set formatter and added handler
        mock_file_handler.setFormatter.assert_called()
        mock_root_logger.addHandler.assert_any_call(mock_file_handler)


@pytest.mark.asyncio
async def test_setup_logging_unstructured():
    """Test setting up logging with unstructured format."""
    # Mock root logger
    mock_root_logger = MagicMock()
    mock_formatter = MagicMock()
    
    with (
        patch('logging.getLogger', return_value=mock_root_logger) as mock_get_logger,
        patch('logging.Formatter', return_value=mock_formatter) as mock_formatter_cls,
        patch('chuk_tool_processor.logging.StructuredFormatter') as mock_structured_formatter_cls
    ):
        # Setup logging with unstructured format
        await setup_logging(structured=False)
        
        # Should have used plain Formatter
        mock_formatter_cls.assert_called()
        mock_structured_formatter_cls.assert_not_called()


@pytest.mark.asyncio
async def test_setup_logging_startup_log():
    """Test that setup_logging logs startup message."""
    # Mock loggers
    mock_root_logger = MagicMock()
    mock_internal_logger = MagicMock()
    
    def mock_getlogger(name):
        if name == "chuk_tool_processor":
            return mock_root_logger
        elif name == "chuk_tool_processor.logging":
            return mock_internal_logger
        return MagicMock()
    
    with patch('logging.getLogger', side_effect=mock_getlogger):
        # Setup logging
        await setup_logging()
        
        # Internal logger should have logged startup
        mock_internal_logger.info.assert_called()
        args, kwargs = mock_internal_logger.info.call_args
        assert "Logging initialized" in args[0]
        assert "context" in kwargs["extra"]
        assert "level" in kwargs["extra"]["context"]


def test_default_handler_setup():
    """Test that default handler is set up correctly at import time."""
    # Import the module to trigger handler setup
    import chuk_tool_processor.logging
    
    # Get the root logger
    root_logger = logging.getLogger("chuk_tool_processor")
    
    # Should have at least one handler
    assert len(root_logger.handlers) > 0
    
    # First handler should be a StreamHandler
    handler = root_logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    
    # Should have a StructuredFormatter
    assert isinstance(handler.formatter, chuk_tool_processor.logging.StructuredFormatter)
    
    # Should have a level set
    assert handler.level is not None