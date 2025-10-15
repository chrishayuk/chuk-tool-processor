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
    # Empty initially
    assert await registry.list_tools() == []
    assert await registry.list_namespaces() == []

    # Register in default and custom namespace
    await registry.register_tool(AsyncTool)
    await registry.register_tool(NoDocTool, namespace="other")

    # List all
    all_tools = set(await registry.list_tools())
    assert all_tools == {("default", "AsyncTool"), ("other", "NoDocTool")}

    # List just default
    assert await registry.list_tools(namespace="default") == [("default", "AsyncTool")]

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

    # Verify the error message includes the namespace and name
    assert "default.NonExistentTool" in str(exc_info.value)


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
