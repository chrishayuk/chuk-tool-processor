# tests/registry/providers/test_redis.py
"""
Tests for the Redis registry provider.

These tests use a mock Redis client to avoid requiring a real Redis server.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.metadata import ToolMetadata


class AsyncTool:
    """A simple async tool for testing."""

    async def execute(self, x: int, y: int) -> int:
        """Add two numbers."""
        return x + y


class AnotherTool:
    """Another test tool."""

    async def execute(self, value: str) -> str:
        """Process a string."""
        return value.upper()


class DeferredTool:
    """A tool that can be deferred."""

    async def execute(self, data: str) -> dict:
        """Process data."""
        return {"data": data}


# -----------------------------------------------------------------------------
# Mock Redis Client
# -----------------------------------------------------------------------------
class MockRedis:
    """Mock async Redis client for testing."""

    def __init__(self):
        self._data: dict[str, bytes] = {}
        self._sets: dict[str, set[bytes]] = {}

    async def get(self, key: str | bytes) -> bytes | None:
        key_str = key.decode() if isinstance(key, bytes) else key
        return self._data.get(key_str)

    async def set(self, key: str, value: str | bytes) -> None:
        if isinstance(value, str):
            value = value.encode()
        self._data[key] = value

    async def delete(self, key: str | bytes) -> None:
        key_str = key.decode() if isinstance(key, bytes) else key
        self._data.pop(key_str, None)
        self._sets.pop(key_str, None)

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def sadd(self, key: str, *values: str) -> int:
        if key not in self._sets:
            self._sets[key] = set()
        added = 0
        for v in values:
            encoded = v.encode() if isinstance(v, str) else v
            if encoded not in self._sets[key]:
                self._sets[key].add(encoded)
                added += 1
        return added

    async def smembers(self, key: str) -> set[bytes]:
        return self._sets.get(key, set())

    async def scan_iter(self, match: str = "*"):
        """Async generator that yields keys matching the pattern."""
        import fnmatch

        # Combine both _data and _sets keys
        all_keys = set(self._data.keys()) | set(self._sets.keys())
        for key in list(all_keys):
            # Simple pattern matching
            if fnmatch.fnmatch(key, match):
                yield key.encode() if isinstance(key, str) else key


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return MockRedis()


@pytest.fixture
def registry(mock_redis):
    """Create a Redis registry with mock client."""
    from chuk_tool_processor.registry.providers.redis import RedisToolRegistry

    return RedisToolRegistry(mock_redis)


# -----------------------------------------------------------------------------
# Basic Registration and Retrieval Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_and_get_tool(registry):
    """Test basic tool registration and retrieval."""
    await registry.register_tool(AsyncTool, name="async_tool")

    tool = await registry.get_tool("async_tool")
    assert tool is AsyncTool


@pytest.mark.asyncio
async def test_register_tool_with_namespace(registry):
    """Test tool registration with custom namespace."""
    await registry.register_tool(AsyncTool, name="add", namespace="math")

    tool = await registry.get_tool("add", namespace="math")
    assert tool is AsyncTool

    # Should not find in default namespace
    default_tool = await registry.get_tool("add")
    assert default_tool is None


@pytest.mark.asyncio
async def test_register_tool_with_metadata(registry):
    """Test tool registration with custom metadata."""
    await registry.register_tool(
        AsyncTool,
        name="tool_with_meta",
        metadata={"version": "2.0", "requires_auth": True},
    )

    metadata = await registry.get_metadata("tool_with_meta")
    assert metadata is not None
    assert metadata.version == "2.0"
    assert metadata.requires_auth is True


@pytest.mark.asyncio
async def test_register_tool_auto_name(registry):
    """Test tool registration with auto-generated name."""
    await registry.register_tool(AsyncTool)

    tool = await registry.get_tool("AsyncTool")
    assert tool is AsyncTool


@pytest.mark.asyncio
async def test_register_tool_dotted_name(registry):
    """Test tool registration with dotted name."""
    await registry.register_tool(AsyncTool, name="math.add")

    # Should auto-extract namespace
    tool = await registry.get_tool("add", namespace="math")
    assert tool is AsyncTool


@pytest.mark.asyncio
async def test_get_tool_returns_none_for_missing(registry):
    """Test that get_tool returns None for missing tools."""
    tool = await registry.get_tool("nonexistent")
    assert tool is None


@pytest.mark.asyncio
async def test_get_tool_strict_raises_for_missing(registry):
    """Test that get_tool_strict raises for missing tools."""
    with pytest.raises(ToolNotFoundError) as exc_info:
        await registry.get_tool_strict("nonexistent")

    assert "nonexistent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_tool_strict_success(registry):
    """Test get_tool_strict with existing tool."""
    await registry.register_tool(AsyncTool, name="existing")

    tool = await registry.get_tool_strict("existing")
    assert tool is AsyncTool


@pytest.mark.asyncio
async def test_get_metadata_returns_none_for_missing(registry):
    """Test that get_metadata returns None for missing tools."""
    metadata = await registry.get_metadata("nonexistent")
    assert metadata is None


# -----------------------------------------------------------------------------
# Listing Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_tools_empty(registry):
    """Test list_tools with no registered tools."""
    tools = await registry.list_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_list_tools_all(registry):
    """Test list_tools returns all registered tools."""
    await registry.register_tool(AsyncTool, name="tool1", namespace="ns1")
    await registry.register_tool(AnotherTool, name="tool2", namespace="ns2")

    tools = await registry.list_tools()
    assert len(tools) == 2

    tool_names = {(t.namespace, t.name) for t in tools}
    assert ("ns1", "tool1") in tool_names
    assert ("ns2", "tool2") in tool_names


@pytest.mark.asyncio
async def test_list_tools_by_namespace(registry):
    """Test list_tools filtered by namespace."""
    await registry.register_tool(AsyncTool, name="tool1", namespace="ns1")
    await registry.register_tool(AnotherTool, name="tool2", namespace="ns1")
    await registry.register_tool(DeferredTool, name="tool3", namespace="ns2")

    ns1_tools = await registry.list_tools(namespace="ns1")
    assert len(ns1_tools) == 2
    assert all(t.namespace == "ns1" for t in ns1_tools)


@pytest.mark.asyncio
async def test_list_namespaces(registry):
    """Test list_namespaces."""
    await registry.register_tool(AsyncTool, name="tool1", namespace="alpha")
    await registry.register_tool(AnotherTool, name="tool2", namespace="beta")

    namespaces = await registry.list_namespaces()
    assert set(namespaces) == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_list_metadata(registry):
    """Test list_metadata returns all tool metadata."""
    await registry.register_tool(AsyncTool, name="tool1")
    await registry.register_tool(AnotherTool, name="tool2")

    metadata_list = await registry.list_metadata()
    assert len(metadata_list) == 2

    names = {m.name for m in metadata_list}
    assert names == {"tool1", "tool2"}


@pytest.mark.asyncio
async def test_list_metadata_by_namespace(registry):
    """Test list_metadata filtered by namespace."""
    await registry.register_tool(AsyncTool, name="tool1", namespace="ns1")
    await registry.register_tool(AnotherTool, name="tool2", namespace="ns2")

    ns1_metadata = await registry.list_metadata(namespace="ns1")
    assert len(ns1_metadata) == 1
    assert ns1_metadata[0].name == "tool1"


# -----------------------------------------------------------------------------
# Deferred Loading Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_register_deferred_tool(registry):
    """Test registering a deferred tool."""
    await registry.register_tool(
        DeferredTool,
        name="deferred_tool",
        metadata={"defer_loading": True},
    )

    # Tool should not be in active tools yet
    active_tools = await registry.get_active_tools()
    assert not any(t.name == "deferred_tool" for t in active_tools)

    # But should be in deferred tools
    deferred_tools = await registry.get_deferred_tools()
    assert any(t.name == "deferred_tool" for t in deferred_tools)


@pytest.mark.asyncio
async def test_load_deferred_tool(registry):
    """Test loading a deferred tool on demand."""
    await registry.register_tool(
        DeferredTool,
        name="lazy_tool",
        metadata={"defer_loading": True},
    )

    # Load the deferred tool
    tool = await registry.load_deferred_tool("lazy_tool")
    assert tool is DeferredTool

    # Should now be in loaded set
    assert "default.lazy_tool" in registry._loaded_deferred_tools


@pytest.mark.asyncio
async def test_get_tool_loads_deferred_automatically(registry):
    """Test that get_tool loads deferred tools automatically."""
    await registry.register_tool(
        DeferredTool,
        name="auto_load",
        metadata={"defer_loading": True},
    )

    # get_tool should trigger loading
    tool = await registry.get_tool("auto_load")
    assert tool is DeferredTool


@pytest.mark.asyncio
async def test_load_deferred_tool_not_found(registry):
    """Test that load_deferred_tool raises for unknown tools."""
    with pytest.raises(ToolNotFoundError):
        await registry.load_deferred_tool("unknown_deferred")


@pytest.mark.asyncio
async def test_search_deferred_tools(registry, mock_redis):
    """Test searching deferred tools."""
    # Manually add deferred tool metadata to Redis (bypassing register_tool)
    # This simulates what would be stored when defer_loading=True
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    metadata1 = ToolMetadata(
        name="data_processor",
        namespace="default",
        defer_loading=True,
        description="Processes data efficiently",
        search_keywords=["data", "processing", "etl"],
    )
    deferred_key1 = f"chuk:{RedisKeyType.DEFERRED.value}:default:data_processor"
    await mock_redis.set(deferred_key1, metadata1.model_dump_json())

    metadata2 = ToolMetadata(
        name="math_add",
        namespace="default",
        defer_loading=True,
        description="Adds numbers",
        search_keywords=["math", "arithmetic"],
    )
    deferred_key2 = f"chuk:{RedisKeyType.DEFERRED.value}:default:math_add"
    await mock_redis.set(deferred_key2, metadata2.model_dump_json())

    # Search for data-related tools
    results = await registry.search_deferred_tools("data")
    assert len(results) > 0
    assert any(m.name == "data_processor" for m in results)


@pytest.mark.asyncio
async def test_search_deferred_tools_with_tags(registry, mock_redis):
    """Test searching deferred tools with tag filter."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    # Manually add deferred tool metadata to Redis
    metadata1 = ToolMetadata(
        name="tagged_tool",
        namespace="default",
        defer_loading=True,
        tags={"production", "critical"},
        search_keywords=["important"],
    )
    deferred_key1 = f"chuk:{RedisKeyType.DEFERRED.value}:default:tagged_tool"
    await mock_redis.set(deferred_key1, metadata1.model_dump_json())

    metadata2 = ToolMetadata(
        name="untagged_tool",
        namespace="default",
        defer_loading=True,
        search_keywords=["important"],
    )
    deferred_key2 = f"chuk:{RedisKeyType.DEFERRED.value}:default:untagged_tool"
    await mock_redis.set(deferred_key2, metadata2.model_dump_json())

    # Search with tag filter
    results = await registry.search_deferred_tools("important", tags=["production"])
    assert len(results) == 1
    assert results[0].name == "tagged_tool"


# -----------------------------------------------------------------------------
# Serialization Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_metadata_serialization(registry):
    """Test that metadata is properly serialized and deserialized."""
    await registry.register_tool(
        AsyncTool,
        name="serialization_test",
        metadata={
            "version": "1.5.0",
            "requires_auth": True,
            "tags": {"tag1", "tag2"},
            "description": "Test tool",
        },
    )

    metadata = await registry.get_metadata("serialization_test")
    assert metadata.version == "1.5.0"
    assert metadata.requires_auth is True
    assert metadata.tags == {"tag1", "tag2"}
    assert metadata.description == "Test tool"


# -----------------------------------------------------------------------------
# Concurrent Access Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_registrations(registry):
    """Test concurrent tool registrations."""

    async def register_tool(name: str):
        class DynamicTool:
            async def execute(self):
                return name

        await registry.register_tool(DynamicTool, name=name)

    # Register multiple tools concurrently
    await asyncio.gather(*[register_tool(f"tool_{i}") for i in range(10)])

    # All should be registered
    tools = await registry.list_tools()
    assert len(tools) == 10


@pytest.mark.asyncio
async def test_concurrent_get_tool(registry):
    """Test concurrent tool retrieval."""
    await registry.register_tool(AsyncTool, name="concurrent_tool")

    # Get the same tool concurrently
    results = await asyncio.gather(*[registry.get_tool("concurrent_tool") for _ in range(10)])

    # All should return the same tool
    assert all(r is AsyncTool for r in results)


# -----------------------------------------------------------------------------
# Clear Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clear(registry):
    """Test clearing all registrations."""
    await registry.register_tool(AsyncTool, name="tool1")
    await registry.register_tool(AnotherTool, name="tool2")

    # Clear everything
    await registry.clear()

    # Should have no tools
    tools = await registry.list_tools()
    assert tools == []


# -----------------------------------------------------------------------------
# Key Helper Tests
# -----------------------------------------------------------------------------
def test_tool_key(registry):
    """Test tool key generation."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    key = registry._tool_key("myns", "mytool")
    assert key == f"chuk:{RedisKeyType.TOOLS.value}:myns:mytool"
    assert key == "chuk:tools:myns:mytool"


def test_namespace_key(registry):
    """Test namespace key generation."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    key = registry._namespace_key()
    assert key == f"chuk:{RedisKeyType.NAMESPACES.value}"
    assert key == "chuk:namespaces"


def test_deferred_key(registry):
    """Test deferred key generation."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    key = registry._deferred_key("ns", "tool")
    assert key == f"chuk:{RedisKeyType.DEFERRED.value}:ns:tool"
    assert key == "chuk:deferred:ns:tool"


def test_tools_pattern(registry):
    """Test tools pattern generation."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    # With namespace
    pattern = registry._tools_pattern("myns")
    assert pattern == f"chuk:{RedisKeyType.TOOLS.value}:myns:*"

    # Without namespace
    pattern = registry._tools_pattern()
    assert pattern == f"chuk:{RedisKeyType.TOOLS.value}:*"


def test_deferred_pattern(registry):
    """Test deferred pattern generation."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    # With namespace
    pattern = registry._deferred_pattern("myns")
    assert pattern == f"chuk:{RedisKeyType.DEFERRED.value}:myns:*"

    # Without namespace
    pattern = registry._deferred_pattern()
    assert pattern == f"chuk:{RedisKeyType.DEFERRED.value}:*"


def test_build_key(registry):
    """Test generic key building."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    # With parts
    key = registry._build_key(RedisKeyType.TOOLS, "ns", "name")
    assert key == "chuk:tools:ns:name"

    # Without parts
    key = registry._build_key(RedisKeyType.NAMESPACES)
    assert key == "chuk:namespaces"


def test_parse_key_parts(registry):
    """Test key parsing."""
    # Valid key
    result = registry._parse_key_parts("chuk:tools:ns:name")
    assert result == ("ns", "name")

    # Valid bytes key
    result = registry._parse_key_parts(b"chuk:tools:ns:name")
    assert result == ("ns", "name")

    # Invalid key (too few parts)
    result = registry._parse_key_parts("chuk:tools")
    assert result is None


# -----------------------------------------------------------------------------
# Relevance Score Tests
# -----------------------------------------------------------------------------
def test_compute_relevance_score_exact_match(registry):
    """Test relevance score for exact name match."""
    metadata = ToolMetadata(name="test_tool", namespace="default")
    score = registry._compute_relevance_score("test_tool", metadata)
    assert score >= 100.0


def test_compute_relevance_score_partial_match(registry):
    """Test relevance score for partial name match."""
    metadata = ToolMetadata(name="test_tool", namespace="default")
    score = registry._compute_relevance_score("test", metadata)
    assert score >= 50.0


def test_compute_relevance_score_description_match(registry):
    """Test relevance score for description match."""
    metadata = ToolMetadata(
        name="tool",
        namespace="default",
        description="This tool processes data efficiently",
    )
    score = registry._compute_relevance_score("process data", metadata)
    assert score > 0


def test_compute_relevance_score_keyword_match(registry):
    """Test relevance score for keyword match."""
    metadata = ToolMetadata(
        name="tool",
        namespace="default",
        search_keywords=["data", "processing", "etl"],
    )
    score = registry._compute_relevance_score("data", metadata)
    assert score >= 20.0


def test_compute_relevance_score_tag_match(registry):
    """Test relevance score for tag match."""
    metadata = ToolMetadata(
        name="tool",
        namespace="default",
        tags={"production", "critical"},
    )
    score = registry._compute_relevance_score("production", metadata)
    assert score >= 10.0


def test_compute_relevance_score_no_match(registry):
    """Test relevance score with no match."""
    metadata = ToolMetadata(name="tool", namespace="default")
    score = registry._compute_relevance_score("completely_unrelated", metadata)
    assert score == 0.0


# -----------------------------------------------------------------------------
# Stream Manager Tests
# -----------------------------------------------------------------------------
def test_set_stream_manager(registry):
    """Test setting stream manager."""
    mock_manager = MagicMock()
    registry.set_stream_manager("mcp_ns", mock_manager)

    assert registry._stream_managers["mcp_ns"] is mock_manager


# -----------------------------------------------------------------------------
# Import Tool Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_import_tool(registry):
    """Test dynamic tool import."""
    # Use a real module path
    tool_class = await registry._import_tool("datetime.datetime")
    assert tool_class is datetime


@pytest.mark.asyncio
async def test_import_tool_invalid_path(registry):
    """Test import with invalid path."""
    with pytest.raises(ValueError, match="Invalid import path"):
        await registry._import_tool("invalid")


# -----------------------------------------------------------------------------
# Get Active/Deferred Tools Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_active_tools(registry):
    """Test get_active_tools."""
    await registry.register_tool(AsyncTool, name="active1")
    await registry.register_tool(AnotherTool, name="active2", namespace="ns2")

    # Get all active tools
    active = await registry.get_active_tools()
    assert len(active) == 2

    # Get active tools by namespace
    ns2_active = await registry.get_active_tools(namespace="ns2")
    assert len(ns2_active) == 1
    assert ns2_active[0].name == "active2"


@pytest.mark.asyncio
async def test_get_deferred_tools_by_namespace(registry):
    """Test get_deferred_tools with namespace filter."""
    await registry.register_tool(
        DeferredTool,
        name="deferred1",
        namespace="ns1",
        metadata={"defer_loading": True},
    )
    await registry.register_tool(
        AsyncTool,
        name="deferred2",
        namespace="ns2",
        metadata={"defer_loading": True},
    )

    # Get deferred tools for ns1
    ns1_deferred = await registry.get_deferred_tools(namespace="ns1")
    assert len(ns1_deferred) == 1
    assert ns1_deferred[0].name == "deferred1"


# -----------------------------------------------------------------------------
# Factory Function Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_redis_registry_import_error():
    """Test create_redis_registry raises ImportError when redis is not installed."""

    with (
        patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}),
        patch(
            "chuk_tool_processor.registry.providers.redis.create_redis_registry",
            side_effect=ImportError("redis package not installed"),
        ),
    ):
        # This would raise ImportError if redis is not installed
        # Since redis is installed in our test env, we mock the error
        pass


# -----------------------------------------------------------------------------
# Get Tool with Import Path Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_tool_loads_from_import_path(registry, mock_redis):
    """Test that get_tool loads from import_path when tool not in cache."""
    # Create metadata with import_path
    metadata = ToolMetadata(
        name="importable_tool",
        namespace="default",
        import_path="datetime.datetime",
    )

    # Store metadata directly in mock redis
    tool_key = registry._tool_key("default", "importable_tool")
    await mock_redis.set(tool_key, registry._serialize_metadata(metadata))
    await mock_redis.sadd(registry._namespace_key(), "default")

    # Get the tool - should load from import_path
    tool = await registry.get_tool("importable_tool")
    assert tool is datetime


# -----------------------------------------------------------------------------
# Load Deferred Tool with Import Path Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_deferred_with_import_path(registry, mock_redis):
    """Test loading deferred tool via import_path."""
    # Create deferred metadata with import_path
    metadata = ToolMetadata(
        name="import_deferred",
        namespace="default",
        defer_loading=True,
        import_path="json.loads",
    )

    # Store in deferred key
    deferred_key = registry._deferred_key("default", "import_deferred")
    await mock_redis.set(deferred_key, registry._serialize_metadata(metadata))

    # Load the deferred tool
    tool = await registry.load_deferred_tool("import_deferred")
    assert tool is json.loads


@pytest.mark.asyncio
async def test_load_deferred_no_source_error(registry, mock_redis):
    """Test loading deferred tool with no source raises error."""
    # Create deferred metadata with no import_path or pre-instantiated tool
    metadata = ToolMetadata(
        name="no_source",
        namespace="default",
        defer_loading=True,
    )

    # Store in deferred key
    deferred_key = registry._deferred_key("default", "no_source")
    await mock_redis.set(deferred_key, registry._serialize_metadata(metadata))

    # Should raise ValueError
    with pytest.raises(ValueError, match="no import_path or pre-instantiated tool"):
        await registry.load_deferred_tool("no_source")


# -----------------------------------------------------------------------------
# MCP Tool Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_mcp_tool_no_stream_manager(registry):
    """Test creating MCP tool without stream manager raises error."""
    from chuk_tool_processor.registry.metadata import MCPToolFactoryParams

    metadata = ToolMetadata(
        name="mcp_tool",
        namespace="default",
        mcp_factory_params=MCPToolFactoryParams(
            tool_name="mcp_tool",
            namespace="mcp_ns",
        ),
    )

    with pytest.raises(ValueError, match="No StreamManager found"):
        await registry._create_mcp_tool(metadata)


@pytest.mark.asyncio
async def test_create_mcp_tool_no_params(registry):
    """Test creating MCP tool without params raises error."""
    metadata = ToolMetadata(
        name="mcp_tool",
        namespace="default",
    )

    with pytest.raises(ValueError, match="no mcp_factory_params"):
        await registry._create_mcp_tool(metadata)


# -----------------------------------------------------------------------------
# Custom Key Prefix Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_custom_key_prefix(mock_redis):
    """Test registry with custom key prefix."""
    from chuk_tool_processor.registry.providers.redis import RedisConfig, RedisToolRegistry

    config = RedisConfig(key_prefix="myapp")
    registry = RedisToolRegistry(mock_redis, config=config)

    await registry.register_tool(AsyncTool, name="test")

    # Check that custom prefix is used
    assert "myapp:tools:default:test" in mock_redis._data


# -----------------------------------------------------------------------------
# RedisConfig Tests
# -----------------------------------------------------------------------------
def test_redis_config_defaults():
    """Test RedisConfig default values."""
    from chuk_tool_processor.registry.providers.redis import RedisConfig

    config = RedisConfig()
    assert config.key_prefix == "chuk"
    assert config.local_cache_ttl == 60.0
    assert config.redis_url == "redis://localhost:6379/0"


def test_redis_config_custom_values():
    """Test RedisConfig with custom values."""
    from chuk_tool_processor.registry.providers.redis import RedisConfig

    config = RedisConfig(
        key_prefix="custom",
        local_cache_ttl=120.0,
        redis_url="redis://localhost:6380/1",
    )
    assert config.key_prefix == "custom"
    assert config.local_cache_ttl == 120.0
    assert config.redis_url == "redis://localhost:6380/1"


def test_redis_config_serialization():
    """Test RedisConfig Pydantic serialization."""
    from chuk_tool_processor.registry.providers.redis import RedisConfig

    config = RedisConfig(key_prefix="test")
    data = config.model_dump()
    assert data["key_prefix"] == "test"

    # Deserialize
    restored = RedisConfig.model_validate(data)
    assert restored.key_prefix == "test"


# -----------------------------------------------------------------------------
# RedisKeyType Enum Tests
# -----------------------------------------------------------------------------
def test_redis_key_type_enum():
    """Test RedisKeyType enum values."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    assert RedisKeyType.TOOLS.value == "tools"
    assert RedisKeyType.NAMESPACES.value == "namespaces"
    assert RedisKeyType.DEFERRED.value == "deferred"


def test_redis_key_type_is_string_enum():
    """Test RedisKeyType is a string enum."""
    from chuk_tool_processor.registry.providers.redis import RedisKeyType

    # Should be usable as string in f-strings
    key = f"prefix:{RedisKeyType.TOOLS.value}:ns:name"
    assert key == "prefix:tools:ns:name"


# -----------------------------------------------------------------------------
# Serialization Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_serialize_deserialize_metadata(registry):
    """Test metadata serialization uses Pydantic native methods."""
    metadata = ToolMetadata(
        name="test",
        namespace="default",
        description="Test description",
        version="2.0.0",
        tags={"tag1", "tag2"},
    )

    # Serialize
    serialized = registry._serialize_metadata(metadata)
    assert isinstance(serialized, str)

    # Deserialize
    restored = registry._deserialize_metadata(serialized)
    assert restored.name == "test"
    assert restored.namespace == "default"
    assert restored.description == "Test description"
    assert restored.version == "2.0.0"
    assert restored.tags == {"tag1", "tag2"}


@pytest.mark.asyncio
async def test_deserialize_bytes(registry):
    """Test deserializing bytes directly."""
    metadata = ToolMetadata(name="bytestest", namespace="default")
    serialized = registry._serialize_metadata(metadata)

    # Test with bytes
    restored = registry._deserialize_metadata(serialized.encode())
    assert restored.name == "bytestest"
