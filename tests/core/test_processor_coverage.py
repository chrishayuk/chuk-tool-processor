"""
Additional tests for processor.py to improve code coverage.

These tests target specific uncovered lines to push coverage above 90%.
"""

from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.execution.wrappers.caching import CachingToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall


class TestProcessorAdditionalCoverage:
    """Additional tests to improve processor coverage."""

    @pytest_asyncio.fixture
    async def mock_registry(self):
        """Create a mock registry."""
        registry = AsyncMock()
        registry.list_tools = AsyncMock(return_value=[("default", "test_tool")])
        registry.get_tool = AsyncMock(return_value=Mock(execute=AsyncMock(return_value={"result": "ok"})))
        registry.get_metadata = AsyncMock(return_value=Mock(description="Test tool"))
        return registry

    @pytest.mark.asyncio
    async def test_circuit_breaker_enabled(self, mock_registry):
        """Test processor with circuit breaker enabled (lines 234-239)."""
        processor = ToolProcessor(
            registry=mock_registry,
            enable_circuit_breaker=True,
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=30.0,
        )
        await processor.initialize()

        # Verify circuit breaker is in the executor chain
        assert processor.executor is not None
        assert processor._initialized

    @pytest.mark.asyncio
    async def test_executor_not_initialized_error(self, mock_registry):
        """Test RuntimeError when executor is None (line 560)."""
        processor = ToolProcessor(registry=mock_registry)
        # Manually set executor to None after initialization to trigger the error
        await processor.initialize()
        processor.executor = None

        calls = [ToolCall(tool="test", arguments={})]

        with pytest.raises(RuntimeError, match="Executor not initialized"):
            await processor.execute(calls)

    @pytest.mark.asyncio
    async def test_list_tools(self, mock_registry):
        """Test list_tools method (lines 673-680)."""
        mock_registry.list_tools = AsyncMock(
            return_value=[
                ("default", "tool1"),
                ("default", "tool2"),
                ("custom", "tool3"),
            ]
        )

        processor = ToolProcessor(registry=mock_registry)
        tools = await processor.list_tools()

        assert len(tools) == 3
        assert "tool1" in tools
        assert "tool2" in tools
        assert "tool3" in tools

    @pytest.mark.asyncio
    async def test_list_tools_registry_not_initialized(self, mock_registry):
        """Test list_tools with uninitialized registry (line 676)."""
        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()
        processor.registry = None

        with pytest.raises(RuntimeError, match="Registry not initialized"):
            await processor.list_tools()

    @pytest.mark.asyncio
    async def test_get_tool_count(self, mock_registry):
        """Test get_tool_count method (lines 694-700)."""
        mock_registry.list_tools = AsyncMock(
            return_value=[
                ("default", "tool1"),
                ("default", "tool2"),
            ]
        )

        processor = ToolProcessor(registry=mock_registry)
        count = await processor.get_tool_count()

        assert count == 2

    @pytest.mark.asyncio
    async def test_get_tool_count_registry_not_initialized(self, mock_registry):
        """Test get_tool_count with uninitialized registry (line 697)."""
        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()
        processor.registry = None

        with pytest.raises(RuntimeError, match="Registry not initialized"):
            await processor.get_tool_count()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_registry):
        """Test context manager entry and exit (lines 707-708, 712-713)."""
        processor = ToolProcessor(registry=mock_registry)

        async with processor as p:
            assert p._initialized
            assert p is processor

        # After context manager exit, processor should still be valid
        # (close() is called but doesn't break the processor)

    @pytest.mark.asyncio
    async def test_close_with_executor_close_method(self, mock_registry):
        """Test close() with executor that has close method (lines 726-731)."""
        # Create a mock executor with a close method
        mock_executor = AsyncMock()
        mock_executor.close = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=[])
        mock_executor.executor = None  # Break the chain to avoid infinite loop

        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()
        processor.executor = mock_executor

        await processor.close()

        # Verify close was called
        mock_executor.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_sync_executor_close(self, mock_registry):
        """Test close() with synchronous executor close method (line 731)."""
        # Create a mock executor with a synchronous close method
        mock_executor = Mock()
        mock_executor.close = Mock()
        mock_executor.execute = AsyncMock(return_value=[])
        mock_executor.executor = None  # Break the chain to avoid infinite loop

        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()
        processor.executor = mock_executor

        await processor.close()

        # Verify close was called
        mock_executor.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_strategy_close_method(self, mock_registry):
        """Test close() with strategy that has close method (lines 734-742)."""
        # Create a mock strategy with a close method
        mock_strategy = AsyncMock()
        mock_strategy.close = AsyncMock()
        mock_strategy.execute = AsyncMock(return_value=[])

        processor = ToolProcessor(registry=mock_registry, strategy=mock_strategy)
        await processor.initialize()

        await processor.close()

        # Verify strategy close was called
        mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_sync_strategy_returning_coroutine(self, mock_registry):
        """Test close() with synchronous strategy that returns a coroutine (lines 739-742)."""

        # Create a coroutine to return
        async def async_close():
            pass

        # Create a mock strategy with a sync close that returns a coroutine
        mock_strategy = Mock()
        mock_strategy.close = Mock(return_value=async_close())
        mock_strategy.execute = AsyncMock(return_value=[])

        processor = ToolProcessor(registry=mock_registry, strategy=mock_strategy)
        await processor.initialize()

        await processor.close()

        # Verify close was called
        mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_cache_clearing(self, mock_registry):
        """Test close() with cache clearing (lines 745-759)."""
        processor = ToolProcessor(
            registry=mock_registry,
            enable_caching=True,
            cache_ttl=300,
        )
        await processor.initialize()

        # Ensure caching executor is in the chain
        assert isinstance(processor.executor, CachingToolExecutor)

        # Add a spy to verify clear is called
        original_clear = processor.executor.cache.clear
        processor.executor.cache.clear = Mock(side_effect=original_clear)

        await processor.close()

        # Verify cache clear was called
        processor.executor.cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_cache_clear_async(self, mock_registry):
        """Test close() with async cache clear method (lines 752-753)."""

        # Create a mock cache with async clear
        mock_cache = AsyncMock()
        mock_cache.clear = AsyncMock()

        processor = ToolProcessor(
            registry=mock_registry,
            enable_caching=True,
        )
        await processor.initialize()

        # Replace the cache with our mock
        if isinstance(processor.executor, CachingToolExecutor):
            processor.executor.cache = mock_cache

        await processor.close()

        # Verify async clear was called
        mock_cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_cache_clear_returns_coroutine(self, mock_registry):
        """Test close() with cache clear that returns coroutine (lines 755-757)."""

        # Create a coroutine to return
        async def async_clear():
            pass

        # Create a mock cache with sync clear that returns a coroutine
        mock_cache = Mock()
        mock_cache.clear = Mock(return_value=async_clear())

        processor = ToolProcessor(
            registry=mock_registry,
            enable_caching=True,
        )
        await processor.initialize()

        # Replace the cache with our mock
        if isinstance(processor.executor, CachingToolExecutor):
            processor.executor.cache = mock_cache

        await processor.close()

        # Verify clear was called
        mock_cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_exception(self, mock_registry):
        """Test close() handles exceptions gracefully (lines 763-764)."""
        # Create a mock executor that raises an exception
        mock_executor = Mock()
        mock_executor.close = Mock(side_effect=Exception("Close failed"))
        mock_executor.executor = None  # Break the chain to avoid infinite loop

        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()
        processor.executor = mock_executor

        # Should not raise, but log the error
        await processor.close()

        # Test passed if no exception was raised

    @pytest.mark.asyncio
    async def test_process_text_with_empty_result(self, mock_registry):
        """Test process_text when no tools are found (line 596)."""
        processor = ToolProcessor(registry=mock_registry)
        await processor.initialize()

        # Process empty text
        results = await processor.process_text("")

        assert results == []
