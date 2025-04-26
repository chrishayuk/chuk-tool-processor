# tests/tool_processor/registry/providers/test_memory.py
import pytest
import inspect
import asyncio

from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.metadata import ToolMetadata


class SyncTool:
    """Synchronously adds two numbers."""
    def execute(self, x: int, y: int) -> int:
        return x + y


class AsyncTool:
    """Asynchronously multiplies two numbers."""
    async def execute(self, x: int, y: int) -> int:
        await asyncio.sleep(0)
        return x * y


class NoDocTool:
    def execute(self):
        return "nodoc"


@pytest.fixture
def registry():
    return InMemoryToolRegistry()


def test_register_and_get_sync_tool(registry):
    # register without explicit name or namespace
    registry.register_tool(SyncTool)
    # default name should be class __name__
    tool = registry.get_tool("SyncTool")
    assert tool is SyncTool

    # metadata
    meta = registry.get_metadata("SyncTool")
    assert isinstance(meta, ToolMetadata)
    assert meta.name == "SyncTool"
    assert meta.namespace == "default"
    # docstring used as description
    assert "adds two numbers" in meta.description.lower()
    # synchronous -> is_async False
    assert meta.is_async is False
    # default version, requires_auth, tags
    assert meta.version == "1.0.0"
    assert meta.requires_auth is False
    assert meta.tags == set()


@pytest.mark.asyncio
async def test_register_and_get_async_tool(registry):
    # pass requires_auth via metadata dict
    registry.register_tool(
        AsyncTool,
        name="Mul",
        namespace="math_ns",
        metadata={"requires_auth": True},
    )
    # explicit name & namespace
    tool = registry.get_tool("Mul", namespace="math_ns")
    assert tool is AsyncTool

    # metadata
    meta = registry.get_metadata("Mul", namespace="math_ns")
    assert meta.name == "Mul"
    assert meta.namespace == "math_ns"
    assert "multiplies two numbers" in meta.description.lower()
    # async -> is_async True
    assert meta.is_async is True
    # metadata override
    assert meta.requires_auth is True


def test_get_missing_tool_returns_none(registry):
    assert registry.get_tool("nope") is None
    assert registry.get_metadata("nope") is None


def test_get_tool_strict_raises(registry):
    with pytest.raises(ToolNotFoundError):
        registry.get_tool_strict("missing")


def test_list_tools_and_namespaces(registry):
    # empty initially
    assert registry.list_tools() == []
    assert registry.list_namespaces() == []

    # register in default and custom namespace
    registry.register_tool(SyncTool)
    registry.register_tool(NoDocTool, namespace="other")
    # list all
    all_tools = set(registry.list_tools())
    assert all_tools == {("default", "SyncTool"), ("other", "NoDocTool")}
    # list just default
    assert registry.list_tools(namespace="default") == [("default", "SyncTool")]
    # list unknown namespace -> empty
    assert registry.list_tools(namespace="missing") == []
    # namespaces
    names = registry.list_namespaces()
    assert set(names) == {"default", "other"}


def test_metadata_override_fields(registry):
    # override version, tags, argument_schema
    custom_meta = {
        "version": "9.9",
        "tags": {"a", "b"},
        "argument_schema": {"type": "object"},
    }
    registry.register_tool(SyncTool, metadata=custom_meta)
    meta = registry.get_metadata("SyncTool")
    # overrides applied
    assert meta.version == "9.9"
    assert meta.tags == {"a", "b"}
    assert meta.argument_schema == {"type": "object"}
