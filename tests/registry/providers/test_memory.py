# tests/tool_processor/registry/providers/test_memory.py
import pytest
import inspect
import asyncio

from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.metadata import ToolMetadata


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