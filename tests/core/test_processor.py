# tests/core/test_processor.py
"""Tests for the ToolProcessor class."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from chuk_tool_processor.core.processor import ToolProcessor, get_default_processor, process, process_text
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_registry():
    """Create a mock registry."""
    registry = Mock()
    registry.get_tool = AsyncMock(return_value=Mock())
    return registry


@pytest.fixture
def mock_strategy():
    """Create a mock execution strategy."""
    strategy = AsyncMock()
    strategy.execute = AsyncMock(return_value=[ToolResult(tool="test_tool", result="test result", machine="test")])
    return strategy


@pytest_asyncio.fixture
async def processor(mock_registry, mock_strategy):
    """Create a processor with mocked dependencies."""
    proc = ToolProcessor(registry=mock_registry, strategy=mock_strategy, enable_caching=False, enable_retries=False)
    await proc.initialize()
    return proc


class TestToolProcessor:
    """Test cases for ToolProcessor."""

    async def test_initialization(self, mock_registry, mock_strategy):
        """Test processor initialization."""
        processor = ToolProcessor(
            registry=mock_registry,
            strategy=mock_strategy,
            default_timeout=30.0,
            max_concurrency=5,
            enable_caching=True,
            cache_ttl=600,
            enable_rate_limiting=True,
            global_rate_limit=100,
            enable_retries=True,
            max_retries=5,
        )

        assert not processor._initialized
        await processor.initialize()
        assert processor._initialized
        assert processor.registry is mock_registry
        assert processor.strategy is mock_strategy

    async def test_double_initialization(self, processor):
        """Test that double initialization doesn't cause issues."""
        # Already initialized in fixture
        assert processor._initialized
        await processor.initialize()  # Should be a no-op
        assert processor._initialized

    async def test_execute_tool_calls(self, processor):
        """Test executing tool calls directly."""
        tool_calls = [
            ToolCall(tool="tool1", arguments={"arg": "val1"}),
            ToolCall(tool="tool2", arguments={"arg": "val2"}),
        ]

        results = await processor.execute(tool_calls)

        assert len(results) == 1  # Mock returns single result
        assert results[0].error is None  # No error means success
        assert results[0].tool == "test_tool"

    async def test_process_json_dict(self, processor):
        """Test processing JSON dict with tool_calls."""
        data = {"tool_calls": [{"id": "call_1", "function": {"name": "test_tool", "arguments": '{"key": "value"}'}}]}

        results = await processor.process(data)

        assert len(results) == 1
        assert results[0].error is None

    async def test_process_single_tool_dict(self, processor):
        """Test processing single tool dict."""
        data = {"tool": "test_tool", "arguments": {"key": "value"}}

        results = await processor.process(data)

        assert len(results) == 1
        assert results[0].error is None

    async def test_process_list_of_tools(self, processor):
        """Test processing list of tool dicts."""
        data = [
            {"tool": "tool1", "arguments": {"arg": "val1"}},
            {"tool": "tool2", "arguments": {"arg": "val2"}},
        ]

        results = await processor.process(data)

        assert len(results) == 1  # Mock returns single result
        assert results[0].error is None

    async def test_process_text_with_parsers(self, processor):
        """Test processing text with parser plugins."""
        text = "Execute test_tool with arg=value"

        # Mock parser
        mock_parser = Mock()
        mock_parser.__class__.__name__ = "MockParser"
        mock_parser.try_parse = AsyncMock(return_value=[ToolCall(tool="test_tool", arguments={"arg": "value"})])
        processor.parsers = [mock_parser]

        results = await processor.process(text)

        assert len(results) == 1
        assert results[0].error is None
        mock_parser.try_parse.assert_called_once_with(text)

    async def test_process_text_no_tools_found(self, processor):
        """Test processing text when no tools are found."""
        text = "No tools here"

        # Mock parser that finds nothing
        mock_parser = Mock()
        mock_parser.__class__.__name__ = "MockParser"
        mock_parser.try_parse = AsyncMock(return_value=[])
        processor.parsers = [mock_parser]

        results = await processor.process(text)

        assert len(results) == 0

    async def test_process_invalid_input(self, processor):
        """Test processing invalid input type."""
        results = await processor.process(12345)  # Invalid type
        assert results == []

    async def test_process_with_unknown_tool(self, processor):
        """Test processing with unknown tool."""
        processor.registry.get_tool = AsyncMock(return_value=None)

        tool_call = ToolCall(tool="unknown_tool", arguments={})
        results = await processor.execute([tool_call])

        assert len(results) == 1  # Still executes, mock returns result

    async def test_process_text_legacy_method(self, processor):
        """Test the legacy process_text method."""
        text = "Execute test_tool"

        mock_parser = Mock()
        mock_parser.__class__.__name__ = "MockParser"
        mock_parser.try_parse = AsyncMock(return_value=[ToolCall(tool="test_tool", arguments={})])
        processor.parsers = [mock_parser]

        results = await processor.process_text(text)

        assert len(results) == 1
        assert results[0].error is None

    async def test_executor_with_caching(self, mock_registry):
        """Test that caching wrapper is applied."""
        strategy = AsyncMock()
        processor = ToolProcessor(registry=mock_registry, strategy=strategy, enable_caching=True, cache_ttl=60)
        await processor.initialize()

        assert processor.executor is not None
        # The executor should be wrapped with caching
        assert processor.enable_caching is True

    async def test_executor_with_rate_limiting(self, mock_registry):
        """Test that rate limiting wrapper is applied."""
        strategy = AsyncMock()
        processor = ToolProcessor(
            registry=mock_registry, strategy=strategy, enable_rate_limiting=True, global_rate_limit=10
        )
        await processor.initialize()

        assert processor.executor is not None
        assert processor.enable_rate_limiting is True

    async def test_executor_with_retries(self, mock_registry):
        """Test that retry wrapper is applied."""
        strategy = AsyncMock()
        processor = ToolProcessor(registry=mock_registry, strategy=strategy, enable_retries=True, max_retries=5)
        await processor.initialize()

        assert processor.executor is not None
        assert processor.enable_retries is True

    async def test_lazy_initialization(self, mock_registry, mock_strategy):
        """Test that components are lazily initialized on first use."""
        processor = ToolProcessor(registry=mock_registry, strategy=mock_strategy)

        assert not processor._initialized

        # First call should trigger initialization
        tool_call = ToolCall(tool="test_tool", arguments={})
        await processor.execute([tool_call])

        assert processor._initialized

    async def test_concurrent_initialization(self, mock_registry, mock_strategy):
        """Test that concurrent calls to initialize are handled correctly."""
        processor = ToolProcessor(registry=mock_registry, strategy=mock_strategy)

        # Start multiple initialization tasks
        tasks = [processor.initialize() for _ in range(5)]
        await asyncio.gather(*tasks)

        assert processor._initialized
        # Should only initialize once despite concurrent calls

    async def test_process_with_custom_parser_plugins(self, mock_registry, mock_strategy):
        """Test using custom parser plugins."""
        with patch("chuk_tool_processor.core.processor.plugin_registry") as mock_plugin_registry:
            mock_plugin_registry.list_plugins.return_value = {"parser": ["json_tool", "xml_tool"]}
            mock_plugin_registry.get_plugin.return_value = Mock()

            processor = ToolProcessor(registry=mock_registry, strategy=mock_strategy, parser_plugins=["json_tool"])
            await processor.initialize()

            # Verify parser plugins were loaded
            assert len(processor.parsers) > 0

    async def test_extract_tool_calls_multiple_parsers(self, processor):
        """Test extracting tool calls with multiple parsers."""
        text = "Execute tool1 and tool2"

        # Create multiple mock parsers
        parser1 = Mock()
        parser1.__class__.__name__ = "Parser1"
        parser1.try_parse = AsyncMock(return_value=[ToolCall(tool="tool1", arguments={})])

        parser2 = Mock()
        parser2.__class__.__name__ = "Parser2"
        parser2.try_parse = AsyncMock(return_value=[ToolCall(tool="tool2", arguments={})])

        processor.parsers = [parser1, parser2]

        calls = await processor._extract_tool_calls(text)

        assert len(calls) == 2
        assert {call.tool for call in calls} == {"tool1", "tool2"}

    async def test_extract_tool_calls_with_duplicates(self, processor):
        """Test that duplicate tool calls are removed."""
        text = "Execute test_tool twice"

        # Parser that returns duplicates
        parser = Mock()
        parser.__class__.__name__ = "Parser"
        parser.try_parse = AsyncMock(
            return_value=[
                ToolCall(tool="test_tool", arguments={"arg": "value"}),
                ToolCall(tool="test_tool", arguments={"arg": "value"}),
            ]
        )
        processor.parsers = [parser]

        calls = await processor._extract_tool_calls(text)

        assert len(calls) == 1  # Duplicates removed
        assert calls[0].tool == "test_tool"

    async def test_extract_tool_calls_parser_exception(self, processor):
        """Test handling parser exceptions."""
        text = "Parse this"

        # Parser that raises exception
        parser = Mock()
        parser.__class__.__name__ = "FailingParser"
        parser.try_parse = AsyncMock(side_effect=Exception("Parser error"))
        processor.parsers = [parser]

        calls = await processor._extract_tool_calls(text)

        assert len(calls) == 0  # No calls due to exception

    async def test_process_with_json_decode_error(self, processor):
        """Test handling JSON decode errors in arguments."""
        data = {
            "tool_calls": [
                {
                    "id": "call_1",  # Add required id field
                    "function": {"name": "test_tool", "arguments": "invalid json"},
                }
            ]
        }

        results = await processor.process(data)

        # Should still process but with raw argument
        assert len(results) == 1

    async def test_default_registry_initialization(self, mock_strategy):
        """Test initialization with default registry."""
        with patch("chuk_tool_processor.core.processor.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=Mock())
            processor = ToolProcessor(strategy=mock_strategy)
            await processor.initialize()

            assert processor.registry is not None
            mock_provider.get_registry.assert_called_once()

    async def test_default_strategy_initialization(self, mock_registry):
        """Test initialization with default strategy."""
        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()

        assert processor.strategy is not None
        # Should create InProcessStrategy by default


class TestGlobalProcessor:
    """Test global processor functions."""

    async def test_get_default_processor(self):
        """Test getting default processor."""
        with patch("chuk_tool_processor.core.processor._global_processor", None):
            processor = await get_default_processor()
            assert processor is not None
            assert isinstance(processor, ToolProcessor)

    async def test_global_process_function(self):
        """Test global process function."""
        with patch("chuk_tool_processor.core.processor.get_default_processor") as mock_get:
            mock_processor = AsyncMock()
            mock_processor.process = AsyncMock(return_value=[])
            mock_get.return_value = mock_processor

            results = await process("test data")

            assert results == []
            mock_processor.process.assert_called_once()

    async def test_global_process_text_function(self):
        """Test global process_text function."""
        with patch("chuk_tool_processor.core.processor.get_default_processor") as mock_get:
            mock_processor = AsyncMock()
            mock_processor.process_text = AsyncMock(return_value=[])
            mock_get.return_value = mock_processor

            results = await process_text("test text")

            assert results == []
            mock_processor.process_text.assert_called_once()
