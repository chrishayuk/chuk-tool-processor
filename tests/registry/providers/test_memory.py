# tests/tool_processor/registry/providers/test_memory.py
import asyncio

import pytest

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.metadata import ToolMetadata
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry


class AsyncTool:
    """Asynchronously adds two numbers."""

    async def execute(self, x: int, y: int) -> int:
        await asyncio.sleep(0)
        return x + y


class AsyncMulTool:
    """Asynchronously multiplies two numbers."""

    async def execute(self, x: int, y: int) -> int:
        await asyncio.sleep(0)
        return x * y


class NoDocTool:
    """Tool without documentation."""

    async def execute(self):
        return "nodoc"


@pytest.fixture
def registry():
    return InMemoryToolRegistry()


@pytest.mark.asyncio
async def test_register_and_get_async_tool(registry):
    # Register without explicit name or namespace
    await registry.register_tool(AsyncTool)
    # Default name should be class __name__
    tool = await registry.get_tool("AsyncTool")
    assert tool is AsyncTool

    # Check metadata
    meta = await registry.get_metadata("AsyncTool")
    assert isinstance(meta, ToolMetadata)
    assert meta.name == "AsyncTool"
    assert meta.namespace == "default"
    # Docstring used as description
    assert "adds two numbers" in meta.description.lower()
    # All tools are async in async-native mode
    assert meta.is_async is True
    # Default version, requires_auth, tags
    assert meta.version == "1.0.0"
    assert meta.requires_auth is False
    assert meta.tags == set()


@pytest.mark.asyncio
async def test_register_with_custom_metadata(registry):
    # Pass requires_auth via metadata dict
    await registry.register_tool(
        AsyncMulTool,
        name="Mul",
        namespace="math_ns",
        metadata={"requires_auth": True},
    )
    # Explicit name & namespace
    tool = await registry.get_tool("Mul", namespace="math_ns")
    assert tool is AsyncMulTool

    # Check metadata
    meta = await registry.get_metadata("Mul", namespace="math_ns")
    assert meta.name == "Mul"
    assert meta.namespace == "math_ns"
    assert "multiplies two numbers" in meta.description.lower()
    # All tools are async in async-native mode
    assert meta.is_async is True
    # Metadata override
    assert meta.requires_auth is True


@pytest.mark.asyncio
async def test_get_missing_tool_returns_none(registry):
    assert await registry.get_tool("nope") is None
    assert await registry.get_metadata("nope") is None


@pytest.mark.asyncio
async def test_get_tool_strict_raises(registry):
    with pytest.raises(ToolNotFoundError):
        await registry.get_tool_strict("missing")


@pytest.mark.asyncio
async def test_list_tools_and_namespaces(registry):
    from chuk_tool_processor.registry.metadata import ToolInfo

    # Empty initially
    assert await registry.list_tools() == []
    assert await registry.list_namespaces() == []

    # Register in default and custom namespace
    await registry.register_tool(AsyncTool)
    await registry.register_tool(NoDocTool, namespace="other")

    # List all
    all_tools = set(await registry.list_tools())
    assert all_tools == {
        ToolInfo(namespace="default", name="AsyncTool"),
        ToolInfo(namespace="other", name="NoDocTool"),
    }

    # List just default
    assert await registry.list_tools(namespace="default") == [ToolInfo(namespace="default", name="AsyncTool")]

    # List unknown namespace -> empty
    assert await registry.list_tools(namespace="missing") == []

    # List namespaces
    names = await registry.list_namespaces()
    assert set(names) == {"default", "other"}


@pytest.mark.asyncio
async def test_metadata_override_fields(registry):
    # Override version, tags, argument_schema
    custom_meta = {
        "version": "9.9",
        "tags": {"a", "b"},
        "argument_schema": {"type": "object"},
    }
    await registry.register_tool(AsyncTool, metadata=custom_meta)
    meta = await registry.get_metadata("AsyncTool")

    # Overrides applied
    assert meta.version == "9.9"
    assert meta.tags == {"a", "b"}
    assert meta.argument_schema == {"type": "object"}


@pytest.mark.asyncio
async def test_get_tool_strict_success(registry):
    """Test get_tool_strict when tool exists."""
    await registry.register_tool(AsyncTool, name="StrictTool")

    # Should return the tool without raising
    tool = await registry.get_tool_strict("StrictTool")
    assert tool is AsyncTool


@pytest.mark.asyncio
async def test_get_tool_strict_raises_on_missing(registry):
    """Test get_tool_strict raises ToolNotFoundError - line 89."""
    # Try to get a tool that doesn't exist
    with pytest.raises(ToolNotFoundError) as exc_info:
        await registry.get_tool_strict("NonExistentTool", namespace="default")

    # Verify the error message includes the namespace and name (new format)
    error_message = str(exc_info.value)
    assert "NonExistentTool" in error_message
    assert "namespace 'default'" in error_message


@pytest.mark.asyncio
async def test_list_metadata_with_specific_namespace(registry):
    """Test list_metadata with specific namespace - lines 127-128."""
    # Register tools in different namespaces
    await registry.register_tool(AsyncTool, name="Tool1", namespace="ns1")
    await registry.register_tool(AsyncMulTool, name="Tool2", namespace="ns2")
    await registry.register_tool(NoDocTool, name="Tool3", namespace="ns1")

    # List metadata for specific namespace
    ns1_metadata = await registry.list_metadata(namespace="ns1")

    # Should only include tools from ns1
    assert len(ns1_metadata) == 2
    names = [meta.name for meta in ns1_metadata]
    assert "Tool1" in names
    assert "Tool3" in names
    assert "Tool2" not in names

    # All should be from ns1
    assert all(meta.namespace == "ns1" for meta in ns1_metadata)


@pytest.mark.asyncio
async def test_list_metadata_all_namespaces(registry):
    """Test list_metadata with no namespace filter - lines 131-134."""
    # Register tools in different namespaces
    await registry.register_tool(AsyncTool, name="ToolA", namespace="alpha")
    await registry.register_tool(AsyncMulTool, name="ToolB", namespace="beta")
    await registry.register_tool(NoDocTool, name="ToolC", namespace="gamma")

    # List all metadata (namespace=None)
    all_metadata = await registry.list_metadata(namespace=None)

    # Should include all tools from all namespaces
    assert len(all_metadata) >= 3
    names = [meta.name for meta in all_metadata]
    assert "ToolA" in names
    assert "ToolB" in names
    assert "ToolC" in names

    # Should have tools from multiple namespaces
    namespaces = {meta.namespace for meta in all_metadata}
    assert "alpha" in namespaces
    assert "beta" in namespaces
    assert "gamma" in namespaces


@pytest.mark.asyncio
async def test_list_metadata_empty_namespace(registry):
    """Test list_metadata for a namespace with no tools."""
    # Don't register any tools in "empty_ns"
    await registry.register_tool(AsyncTool, name="Tool", namespace="other")

    # List metadata for empty namespace
    empty_metadata = await registry.list_metadata(namespace="empty_ns")

    # Should return empty list
    assert empty_metadata == []


@pytest.mark.asyncio
async def test_get_tool_from_different_namespace(registry):
    """Test getting tools from different namespaces."""
    # Register same tool name in different namespaces
    await registry.register_tool(AsyncTool, name="SameName", namespace="ns1")
    await registry.register_tool(AsyncMulTool, name="SameName", namespace="ns2")

    # Get from ns1
    tool1 = await registry.get_tool("SameName", namespace="ns1")
    assert tool1 is AsyncTool

    # Get from ns2
    tool2 = await registry.get_tool("SameName", namespace="ns2")
    assert tool2 is AsyncMulTool

    # They should be different
    assert tool1 is not tool2


@pytest.mark.asyncio
async def test_get_metadata_from_nonexistent_namespace(registry):
    """Test get_metadata from namespace that doesn't exist."""
    result = await registry.get_metadata("AnyTool", namespace="nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_concurrent_registrations(registry):
    """Test concurrent tool registrations work correctly."""
    import asyncio

    # Define multiple tools to register concurrently
    class Tool1:
        async def execute(self):
            return 1

    class Tool2:
        async def execute(self):
            return 2

    class Tool3:
        async def execute(self):
            return 3

    # Register tools concurrently
    await asyncio.gather(
        registry.register_tool(Tool1, name="Tool1"),
        registry.register_tool(Tool2, name="Tool2"),
        registry.register_tool(Tool3, name="Tool3"),
    )

    # All should be registered
    assert await registry.get_tool("Tool1") is Tool1
    assert await registry.get_tool("Tool2") is Tool2
    assert await registry.get_tool("Tool3") is Tool3


@pytest.mark.asyncio
async def test_register_tool_dotted_name_extracts_namespace(registry):
    """Test registering a tool with dotted name extracts namespace - lines 75-78."""

    class MyDottedTool:
        async def execute(self):
            return "dotted"

    # Register with dotted name - should auto-extract namespace
    await registry.register_tool(MyDottedTool, name="myns.dotted_tool")

    # Should be registered in "myns" namespace with name "dotted_tool"
    tool = await registry.get_tool("dotted_tool", namespace="myns")
    assert tool is MyDottedTool

    # Should NOT be in default namespace
    assert await registry.get_tool("myns.dotted_tool", namespace="default") is None


@pytest.mark.asyncio
async def test_import_tool_method(registry):
    """Test the _import_tool method directly - lines 370-382."""
    # Import a known module/class
    import_path = "chuk_tool_processor.core.exceptions.ToolNotFoundError"
    tool_class = await registry._import_tool(import_path)

    assert tool_class is ToolNotFoundError


@pytest.mark.asyncio
async def test_import_tool_invalid_path(registry):
    """Test _import_tool with invalid import path - lines 371-372."""
    # Invalid path without a dot
    with pytest.raises(ValueError, match="Invalid import path"):
        await registry._import_tool("nodot")


@pytest.mark.asyncio
async def test_load_deferred_tool_with_import_path(registry):
    """Test loading a deferred tool via import path - lines 342-344."""
    # Register a deferred tool with import_path
    metadata = {
        "defer_loading": True,
        "import_path": "chuk_tool_processor.core.exceptions.ToolNotFoundError",
    }

    class DummyTool:
        async def execute(self):
            return "dummy"

    await registry.register_tool(DummyTool, name="ImportTool", namespace="import_test", metadata=metadata)

    # Verify it's in deferred
    assert "ImportTool" in registry._deferred_metadata.get("import_test", {})

    # Load it
    tool = await registry.load_deferred_tool("ImportTool", namespace="import_test")
    assert tool is ToolNotFoundError


@pytest.mark.asyncio
async def test_load_deferred_tool_pre_instantiated(registry):
    """Test loading a pre-instantiated deferred tool - lines 345-347."""

    class PreInstantiatedTool:
        async def execute(self):
            return "pre-instantiated"

    # Register a deferred tool without import_path (pre-instantiated)
    metadata = {
        "defer_loading": True,
    }
    await registry.register_tool(PreInstantiatedTool, name="PreTool", namespace="pre_ns", metadata=metadata)

    # Verify it's stored in deferred_tools
    assert "PreTool" in registry._deferred_tools.get("pre_ns", {})
    assert "PreTool" in registry._deferred_metadata.get("pre_ns", {})

    # Load it
    tool = await registry.load_deferred_tool("PreTool", namespace="pre_ns")
    assert tool is PreInstantiatedTool


@pytest.mark.asyncio
async def test_load_deferred_tool_no_import_path_error(registry):
    """Test loading deferred tool without import_path or pre-instantiated tool raises error - line 349."""
    # Manually add metadata without import_path or pre-instantiated tool
    from chuk_tool_processor.registry.metadata import ToolMetadata

    registry._deferred_metadata.setdefault("error_ns", {})
    registry._deferred_metadata["error_ns"]["BadTool"] = ToolMetadata(
        name="BadTool",
        namespace="error_ns",
        defer_loading=True,
        # No import_path, no pre-instantiated tool
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="has no import_path or pre-instantiated tool"):
        await registry.load_deferred_tool("BadTool", namespace="error_ns")


@pytest.mark.asyncio
async def test_load_deferred_tool_double_check_pattern(registry):
    """Test double-check locking in load_deferred_tool - line 336."""

    class DoubleCheckTool:
        async def execute(self):
            return "double-check"

    # Register a deferred tool
    metadata = {"defer_loading": True}
    await registry.register_tool(DoubleCheckTool, name="DCTool", namespace="dc_ns", metadata=metadata)

    # Load it once
    tool1 = await registry.load_deferred_tool("DCTool", namespace="dc_ns")

    # Load it again - should hit the double-check and return the same tool
    tool2 = await registry.load_deferred_tool("DCTool", namespace="dc_ns")

    assert tool1 is tool2


@pytest.mark.asyncio
async def test_create_mcp_tool(registry):
    """Test _create_mcp_tool method - lines 394-415."""
    from unittest.mock import MagicMock, patch

    from chuk_tool_processor.registry.metadata import MCPToolFactoryParams, ToolMetadata

    # Create metadata with MCP factory params
    factory_params = MCPToolFactoryParams(
        namespace="mcp_ns",
        tool_name="mcp_tool",
        default_timeout=30.0,
        enable_resilience=True,
        recovery_config=None,
    )
    metadata = ToolMetadata(
        name="MCPTestTool",
        namespace="mcp_ns",
        defer_loading=True,
        mcp_factory_params=factory_params,
    )

    # Set up a mock stream manager
    mock_stream_manager = MagicMock()
    registry.set_stream_manager("mcp_ns", mock_stream_manager)

    # Mock the MCPTool class
    with patch("chuk_tool_processor.mcp.mcp_tool.MCPTool") as MockMCPTool:
        mock_tool_instance = MagicMock()
        MockMCPTool.return_value = mock_tool_instance

        tool = await registry._create_mcp_tool(metadata)

        # Verify MCPTool was created with correct params
        MockMCPTool.assert_called_once_with(
            tool_name="mcp_tool",
            stream_manager=mock_stream_manager,
            default_timeout=30.0,
            enable_resilience=True,
            recovery_config=None,
        )
        assert tool is mock_tool_instance


@pytest.mark.asyncio
async def test_create_mcp_tool_no_factory_params(registry):
    """Test _create_mcp_tool raises when no factory params - line 397."""
    from chuk_tool_processor.registry.metadata import ToolMetadata

    metadata = ToolMetadata(
        name="NoFactoryTool",
        namespace="mcp_ns",
        mcp_factory_params=None,  # No factory params
    )

    with pytest.raises(ValueError, match="has no mcp_factory_params"):
        await registry._create_mcp_tool(metadata)


@pytest.mark.asyncio
async def test_create_mcp_tool_no_stream_manager(registry):
    """Test _create_mcp_tool raises when no stream manager - lines 402-406."""
    from chuk_tool_processor.registry.metadata import MCPToolFactoryParams, ToolMetadata

    factory_params = MCPToolFactoryParams(
        namespace="missing_sm_ns",
        tool_name="mcp_tool",
    )
    metadata = ToolMetadata(
        name="NoSMTool",
        namespace="missing_sm_ns",
        defer_loading=True,
        mcp_factory_params=factory_params,
    )

    # Don't set stream manager

    with pytest.raises(ValueError, match="No StreamManager found"):
        await registry._create_mcp_tool(metadata)


@pytest.mark.asyncio
async def test_load_deferred_mcp_tool(registry):
    """Test loading a deferred MCP tool via load_deferred_tool - line 341."""
    from unittest.mock import MagicMock, patch

    from chuk_tool_processor.registry.metadata import MCPToolFactoryParams, ToolMetadata

    # Create a deferred MCP tool
    factory_params = MCPToolFactoryParams(
        namespace="mcp_defer_ns",
        tool_name="deferred_mcp",
    )

    # Manually add to deferred metadata
    registry._deferred_metadata.setdefault("mcp_defer_ns", {})
    registry._deferred_metadata["mcp_defer_ns"]["DeferredMCP"] = ToolMetadata(
        name="DeferredMCP",
        namespace="mcp_defer_ns",
        defer_loading=True,
        mcp_factory_params=factory_params,
    )

    # Set stream manager
    mock_stream_manager = MagicMock()
    registry.set_stream_manager("mcp_defer_ns", mock_stream_manager)

    # Mock MCPTool
    with patch("chuk_tool_processor.mcp.mcp_tool.MCPTool") as MockMCPTool:
        mock_tool_instance = MagicMock()
        MockMCPTool.return_value = mock_tool_instance

        tool = await registry.load_deferred_tool("DeferredMCP", namespace="mcp_defer_ns")

        assert tool is mock_tool_instance
        # Should be marked as loaded
        assert "mcp_defer_ns.DeferredMCP" in registry._loaded_deferred_tools
