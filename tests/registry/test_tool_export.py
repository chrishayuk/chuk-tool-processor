# tests/registry/test_tool_export.py
"""Tests for tool export functionality."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.registry.tool_export import (
    _build_openai_name_cache,
    clear_name_cache,
    openai_functions,
    tool_by_openai_name,
)

pytestmark = pytest.mark.asyncio


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

            # Unknown tool should raise KeyError or return None
            try:
                tool = await tool_by_openai_name("UnknownTool")
                assert tool is None
            except KeyError:
                # This is also acceptable behavior
                pass

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

    async def test_clear_openai_name_cache(self):
        """Test clearing the cache."""
        # Set up a mock cache
        import chuk_tool_processor.registry.tool_export as export_module

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

    async def test_build_cache_double_check_after_lock(self):
        """Test double-check pattern in _build_openai_name_cache - lines 38-39."""
        await clear_name_cache()

        import chuk_tool_processor.registry.tool_export as export_module

        # Set cache to simulate race condition
        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            # First build should populate cache
            await _build_openai_name_cache()

            # Verify cache is not None
            assert export_module._OPENAI_NAME_CACHE is not None

            # Second call should return early (line 38-39)
            await _build_openai_name_cache()

            # Should only call list_tools once
            assert mock_registry.list_tools.call_count == 1

    async def test_build_cache_with_none_tool(self):
        """Test _build_openai_name_cache when get_tool returns None - line 54."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "tool1"), ("default", "tool2")])
        # First tool is None, second is valid
        mock_registry.get_tool = AsyncMock(side_effect=[None, MockTool])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            await _build_openai_name_cache()

            # Should handle None gracefully and continue
            assert mock_registry.get_tool.call_count == 2

    async def test_openai_functions_skips_none_tool(self):
        """Test openai_functions skips None tools - line 98."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "NullTool")])
        mock_registry.get_tool = AsyncMock(return_value=None)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            tools = await openai_functions()

            # Should return empty list since tool is None
            assert len(tools) == 0

    async def test_tool_by_openai_name_cache_none_error(self):
        """Test tool_by_openai_name when cache is None - line 134."""
        await clear_name_cache()

        import chuk_tool_processor.registry.tool_export as export_module

        # Force cache to be None
        export_module._OPENAI_NAME_CACHE = None

        # Mock the build function to keep cache as None
        async def mock_build():
            pass

        # The code catches the "Tool cache not initialized" error and re-raises
        # with a "No tool registered" message, so we test for that
        with (
            patch("chuk_tool_processor.registry.tool_export._build_openai_name_cache", mock_build),
            pytest.raises(KeyError, match="No tool registered for OpenAI name"),
        ):
            await tool_by_openai_name("SomeTool")

    async def test_tool_by_openai_name_key_error(self):
        """Test tool_by_openai_name raises KeyError for unknown tool."""
        await clear_name_cache()

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "KnownTool")])
        mock_registry.get_tool = AsyncMock(return_value=MockTool)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            # Build cache with known tool
            await _build_openai_name_cache()

            # Try to get unknown tool
            with pytest.raises(KeyError, match="No tool registered for OpenAI name"):
                await tool_by_openai_name("UnknownTool")


class TestExportToolsAsOpenAPI:
    """Test export_tools_as_openapi function - lines 169-231."""

    async def test_export_tools_as_openapi_basic(self):
        """Test basic OpenAPI export."""
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi(title="Test API", version="2.0.0", description="Test Description")

            assert spec["openapi"] == "3.0.0"
            assert spec["info"]["title"] == "Test API"
            assert spec["info"]["version"] == "2.0.0"
            assert spec["info"]["description"] == "Test Description"
            assert "paths" in spec
            assert "components" in spec

    async def test_export_tools_as_openapi_with_tools(self):
        """Test OpenAPI export with tools that have schemas."""

        from chuk_tool_processor.registry.metadata import ToolMetadata
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        # Create a mock tool with Arguments and Result
        class ToolWithSchemas:
            class Arguments:
                @staticmethod
                def model_json_schema():
                    return {"type": "object", "properties": {"input": {"type": "string"}}}

            class Result:
                @staticmethod
                def model_json_schema():
                    return {"type": "object", "properties": {"output": {"type": "string"}}}

        metadata = ToolMetadata(
            name="Schematool", namespace="default", is_async=True, description="A tool with schemas"
        )

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "SchemaTool")])
        mock_registry.get_tool = AsyncMock(return_value=ToolWithSchemas)
        mock_registry.get_metadata = AsyncMock(return_value=metadata)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi()

            # Should have paths
            assert len(spec["paths"]) > 0
            assert "/default/SchemaTool" in spec["paths"]

            # Should have schemas
            assert "schemas" in spec["components"]
            assert "SchemaToolArgs" in spec["components"]["schemas"]
            assert "SchemaToolResult" in spec["components"]["schemas"]

    async def test_export_tools_as_openapi_none_tool(self):
        """Test OpenAPI export skips None tools - line 184."""
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "NullTool")])
        mock_registry.get_tool = AsyncMock(return_value=None)
        mock_registry.get_metadata = AsyncMock(return_value=None)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi()

            # Should have no paths since tool is None
            assert len(spec["paths"]) == 0

    async def test_export_tools_as_openapi_none_metadata(self):
        """Test OpenAPI export skips tools with None metadata."""
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        class SimpleTool:
            pass

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "SimpleTool")])
        mock_registry.get_tool = AsyncMock(return_value=SimpleTool)
        mock_registry.get_metadata = AsyncMock(return_value=None)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi()

            # Should skip tool with None metadata
            assert len(spec["paths"]) == 0

    async def test_export_tools_as_openapi_without_schemas(self):
        """Test OpenAPI export with tool without Arguments/Result schemas."""
        from chuk_tool_processor.registry.metadata import ToolMetadata
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        class ToolWithoutSchemas:
            pass

        metadata = ToolMetadata(name="NoSchema", namespace="default", is_async=True, description="No schemas")

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("default", "NoSchema")])
        mock_registry.get_tool = AsyncMock(return_value=ToolWithoutSchemas)
        mock_registry.get_metadata = AsyncMock(return_value=metadata)

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi()

            # Should have path but empty schemas
            assert "/default/NoSchema" in spec["paths"]
            path_spec = spec["paths"]["/default/NoSchema"]["post"]
            assert path_spec["summary"] == "No schemas"

    async def test_export_tools_multiple_namespaces(self):
        """Test OpenAPI export with tools in multiple namespaces."""
        from chuk_tool_processor.registry.metadata import ToolMetadata
        from chuk_tool_processor.registry.tool_export import export_tools_as_openapi

        class Tool1:
            pass

        class Tool2:
            pass

        metadata1 = ToolMetadata(name="Tool1", namespace="ns1", is_async=True, description="Tool 1")
        metadata2 = ToolMetadata(name="Tool2", namespace="ns2", is_async=True, description="Tool 2")

        mock_registry = Mock()
        mock_registry.list_tools = AsyncMock(return_value=[("ns1", "Tool1"), ("ns2", "Tool2")])
        mock_registry.get_tool = AsyncMock(side_effect=[Tool1, Tool2])
        mock_registry.get_metadata = AsyncMock(side_effect=[metadata1, metadata2])

        with patch("chuk_tool_processor.registry.tool_export.ToolRegistryProvider") as mock_provider:
            mock_provider.get_registry = AsyncMock(return_value=mock_registry)

            spec = await export_tools_as_openapi()

            # Should have paths for both namespaces
            assert "/ns1/Tool1" in spec["paths"]
            assert "/ns2/Tool2" in spec["paths"]

            # Should have correct tags
            assert spec["paths"]["/ns1/Tool1"]["post"]["tags"] == ["ns1"]
            assert spec["paths"]["/ns2/Tool2"]["post"]["tags"] == ["ns2"]
