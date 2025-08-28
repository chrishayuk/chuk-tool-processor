# tests/registry/test_tool_export_simple.py
"""Simple tests for tool export functionality."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

from chuk_tool_processor.registry.tool_export import (
    _build_openai_name_cache,
    clear_name_cache,
    openai_functions,
    tool_by_openai_name,
)


class MockTool:
    """Mock tool for testing."""

    __name__ = "MockTool"
    __doc__ = "A mock tool for testing"

    @classmethod
    def to_openai(cls, registry_name: str | None = None) -> dict:
        """Mock OpenAI export."""
        name = registry_name or cls.__name__
        return {
            "type": "function",
            "function": {"name": name, "description": cls.__doc__, "parameters": {"type": "object", "properties": {}}},
        }


class TestToolExport:
    """Test tool export functions."""

    async def test_build_openai_name_cache(self):
        """Test building the OpenAI name cache."""
        # Clear cache first
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "tool1"), ("custom", "tool2")])
        mock_registry.get_tool = AsyncMock(side_effect=[MockTool, MockTool])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            await _build_openai_name_cache()

            # Cache should be built
            mock_registry.list_tools.assert_called_once()
            assert mock_registry.get_tool.call_count == 2

    async def test_build_openai_name_cache_concurrent(self):
        """Test that concurrent cache builds only build once."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            # Start multiple concurrent builds
            tasks = [_build_openai_name_cache() for _ in range(5)]
            await asyncio.gather(*tasks)

            # Should only call list_tools once
            assert mock_registry.list_tools.call_count == 1

    async def test_tool_by_openai_name(self):
        """Test looking up tool by OpenAI name."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "MyTool")])
        mock_registry.get_tool = AsyncMock(return_value=MockTool)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            # First call builds cache
            tool = await tool_by_openai_name("MockTool")
            assert tool == MockTool

            # Second call uses cache
            tool = await tool_by_openai_name("MockTool")
            assert tool == MockTool

            # Unknown tool returns None
            tool = await tool_by_openai_name("UnknownTool")
            assert tool is None

    async def test_openai_functions(self):
        """Test listing tools in OpenAI format."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "Tool1"), ("custom", "Tool2")])
        mock_registry.get_tool = AsyncMock(return_value=MockTool)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            tools = await openai_functions()

            assert len(tools) == 2
            assert all("type" in tool for tool in tools)
            assert all(tool["type"] == "function" for tool in tools)

    async def test_clear_name_cache(self):
        """Test clearing the cache."""
        import chuk_tool_processor.registry.tool_export as export_module

        # Set up a mock cache
        export_module._OPENAI_NAME_CACHE = {"test": "data"}

        await clear_name_cache()

        assert export_module._OPENAI_NAME_CACHE is None

    async def test_tool_without_to_openai(self):
        """Test handling tool without to_openai method."""
        await clear_name_cache()

        class BasicTool:
            __name__ = "BasicTool"

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "BasicTool")])
        mock_registry.get_tool = AsyncMock(return_value=BasicTool)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            # Should handle gracefully
            tools = await openai_functions()
            assert len(tools) == 0  # Tool skipped due to missing method
