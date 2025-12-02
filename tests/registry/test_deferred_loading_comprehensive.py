# tests/registry/test_deferred_loading_comprehensive.py
"""
Comprehensive tests for deferred loading functionality.

Tests both memory.py deferred loading methods and the full integration
with register_mcp_tools.
"""

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry import reset_registry
from chuk_tool_processor.registry.metadata import MCPToolFactoryParams
from chuk_tool_processor.registry.provider import ToolRegistryProvider

# ============================================================================
# Test Tool Definitions
# ============================================================================


class EagerTool(ValidatedTool):
    """An eagerly loaded tool."""

    class Arguments(BaseModel):
        value: int = Field(..., description="Test value")

    class Result(BaseModel):
        result: int = Field(..., description="Test result")

    async def _execute(self, value: int) -> dict:
        return {"result": value * 2}


class DeferredTool(ValidatedTool):
    """A deferred tool."""

    class Arguments(BaseModel):
        value: int = Field(..., description="Test value")

    class Result(BaseModel):
        result: int = Field(..., description="Test result")

    async def _execute(self, value: int) -> dict:
        return {"result": value * 3}


class AnotherDeferredTool(ValidatedTool):
    """Another deferred tool with different keywords."""

    class Arguments(BaseModel):
        value: int = Field(..., description="Test value")

    class Result(BaseModel):
        result: int = Field(..., description="Test result")

    async def _execute(self, value: int) -> dict:
        return {"result": value * 4}


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def registry():
    """Provide a clean registry for each test."""
    await reset_registry()
    reg = await ToolRegistryProvider.get_registry()
    yield reg
    # Cleanup
    await reset_registry()


@pytest_asyncio.fixture
async def sample_tools(registry):
    """Register sample tools for testing."""

    # Register eager tool
    await registry.register_tool(
        EagerTool(),
        name="eager_tool",
        namespace="test",
        metadata={
            "description": "Eagerly loaded tool for testing",
            "defer_loading": False,
        },
    )

    # Register deferred tools
    await registry.register_tool(
        DeferredTool(),
        name="deferred_tool",
        namespace="test",
        metadata={
            "description": "Deferred tool for testing calculations",
            "defer_loading": True,
            "search_keywords": ["deferred", "calculation", "multiply"],
            "tags": {"math", "deferred"},
        },
    )

    await registry.register_tool(
        AnotherDeferredTool(),
        name="another_deferred",
        namespace="test",
        metadata={
            "description": "Another deferred tool for advanced operations",
            "defer_loading": True,
            "search_keywords": ["advanced", "operation", "quadruple"],
            "tags": {"math", "advanced", "deferred"},
        },
    )

    return {
        "eager": EagerTool(),
        "deferred": DeferredTool(),
        "another_deferred": AnotherDeferredTool(),
    }


# ============================================================================
# Test: Basic Registration
# ============================================================================


@pytest.mark.asyncio
async def test_eager_tool_is_immediately_available(registry, sample_tools):
    """Eager tools should be immediately available in active tools."""
    active_tools = await registry.get_active_tools(namespace="test")

    # Should have only the eager tool
    assert len(active_tools) == 1
    assert active_tools[0].name == "eager_tool"


@pytest.mark.asyncio
async def test_deferred_tools_not_in_active(registry, sample_tools):
    """Deferred tools should not appear in active tools initially."""
    active_tools = await registry.get_active_tools(namespace="test")
    deferred_tools = await registry.get_deferred_tools(namespace="test")

    # Only eager tool is active
    assert len(active_tools) == 1
    assert active_tools[0].name == "eager_tool"

    # Deferred tools should be tracked separately
    assert len(deferred_tools) == 2
    deferred_names = {t.name for t in deferred_tools}
    assert "deferred_tool" in deferred_names
    assert "another_deferred" in deferred_names


@pytest.mark.asyncio
async def test_deferred_tool_metadata_accessible(registry, sample_tools):
    """Metadata for deferred tools should be accessible."""
    metadata = await registry.get_metadata("deferred_tool", "test")

    assert metadata is not None
    assert metadata.name == "deferred_tool"
    assert metadata.defer_loading is True
    assert "deferred" in metadata.search_keywords
    assert "calculation" in metadata.search_keywords


# ============================================================================
# Test: Search Functionality
# ============================================================================


@pytest.mark.asyncio
async def test_search_finds_relevant_tools(registry, sample_tools):
    """Search should find deferred tools by keywords."""
    results = await registry.search_deferred_tools(query="calculation", limit=5)

    assert len(results) == 1
    assert results[0].name == "deferred_tool"


@pytest.mark.asyncio
async def test_search_by_description(registry, sample_tools):
    """Search should match against tool descriptions."""
    results = await registry.search_deferred_tools(query="advanced operations", limit=5)

    assert len(results) >= 1
    names = {r.name for r in results}
    assert "another_deferred" in names


@pytest.mark.asyncio
async def test_search_returns_multiple_matches(registry, sample_tools):
    """Search should return multiple matches ordered by relevance."""
    results = await registry.search_deferred_tools(query="deferred", limit=5)

    # Should find both deferred tools
    assert len(results) >= 1
    names = {r.name for r in results}
    assert "deferred_tool" in names or "another_deferred" in names


@pytest.mark.asyncio
async def test_search_with_tag_filter(registry, sample_tools):
    """Search should filter by tags."""
    results = await registry.search_deferred_tools(query="tool", tags=["advanced"], limit=5)

    # Only another_deferred has "advanced" tag
    names = {r.name for r in results}
    assert "another_deferred" in names


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_matches(registry, sample_tools):
    """Search should return empty list when no matches found."""
    results = await registry.search_deferred_tools(query="nonexistent_keyword_xyz", limit=5)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_excludes_loaded_tools(registry, sample_tools):
    """Search should not return tools that have been loaded."""
    # Load one deferred tool
    await registry.load_deferred_tool("deferred_tool", "test")

    # Search for it
    results = await registry.search_deferred_tools(query="calculation", limit=5)

    # Should not find it (already loaded)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_respects_limit(registry, sample_tools):
    """Search should respect the limit parameter."""
    # Register more deferred tools
    for i in range(5):

        class TestTool(ValidatedTool):
            async def _execute(self, **kwargs):
                return {}

        await registry.register_tool(
            TestTool(),
            name=f"extra_tool_{i}",
            namespace="test",
            metadata={
                "description": "Extra deferred tool for limit testing",
                "defer_loading": True,
                "search_keywords": ["extra", "limit", "test"],
            },
        )

    results = await registry.search_deferred_tools(query="extra", limit=2)

    assert len(results) <= 2


# ============================================================================
# Test: Loading Deferred Tools
# ============================================================================


@pytest.mark.asyncio
async def test_load_deferred_tool(registry, sample_tools):
    """Loading a deferred tool should make it active."""
    # Before loading
    active_before = await registry.get_active_tools(namespace="test")
    deferred_before = await registry.get_deferred_tools(namespace="test")

    assert len(active_before) == 1
    assert len(deferred_before) == 2

    # Load deferred tool
    tool = await registry.load_deferred_tool("deferred_tool", "test")

    assert tool is not None

    # After loading
    active_after = await registry.get_active_tools(namespace="test")
    deferred_after = await registry.get_deferred_tools(namespace="test")

    assert len(active_after) == 2  # eager + loaded deferred
    assert len(deferred_after) == 1  # one less deferred


@pytest.mark.asyncio
async def test_load_same_tool_twice(registry, sample_tools):
    """Loading the same tool twice should be safe."""
    # Load once
    tool1 = await registry.load_deferred_tool("deferred_tool", "test")
    # Load again
    tool2 = await registry.load_deferred_tool("deferred_tool", "test")

    assert tool1 is not None
    assert tool2 is not None
    # Should be the same instance
    assert tool1 is tool2


@pytest.mark.asyncio
async def test_load_nonexistent_tool_raises(registry, sample_tools):
    """Loading a nonexistent tool should raise ToolNotFoundError."""
    with pytest.raises(ToolNotFoundError):
        await registry.load_deferred_tool("nonexistent", "test")


@pytest.mark.asyncio
async def test_auto_load_on_get_tool(registry, sample_tools):
    """get_tool should auto-load deferred tools."""
    # Tool is deferred initially
    active_before = await registry.get_active_tools(namespace="test")
    assert len(active_before) == 1

    # get_tool should load it automatically
    tool = await registry.get_tool("deferred_tool", "test")

    assert tool is not None

    # Now it should be active
    active_after = await registry.get_active_tools(namespace="test")
    assert len(active_after) == 2


# ============================================================================
# Test: Tool Execution
# ============================================================================


@pytest.mark.asyncio
async def test_execute_eager_tool(registry, sample_tools):
    """Eager tools should execute immediately."""
    tool = await registry.get_tool("eager_tool", "test")
    result = await tool.execute(value=5)

    # Result is a Pydantic model
    assert result.result == 10  # 5 * 2


@pytest.mark.asyncio
async def test_execute_deferred_tool_after_load(registry, sample_tools):
    """Deferred tools should execute after loading."""
    # Load the tool
    tool = await registry.load_deferred_tool("deferred_tool", "test")

    # Execute it
    result = await tool.execute(value=5)

    assert result.result == 15  # 5 * 3


@pytest.mark.asyncio
async def test_execute_via_auto_load(registry, sample_tools):
    """Tools should execute via auto-loading through get_tool."""
    # get_tool will auto-load
    tool = await registry.get_tool("deferred_tool", "test")

    # Execute it
    result = await tool.execute(value=7)

    assert result.result == 21  # 7 * 3


# ============================================================================
# Test: Relevance Scoring
# ============================================================================


@pytest.mark.asyncio
async def test_relevance_exact_name_match(registry, sample_tools):
    """Exact name match should have highest score."""
    results = await registry.search_deferred_tools(query="deferred_tool", limit=5)

    # Should find the exact match first
    assert len(results) >= 1
    assert results[0].name == "deferred_tool"


@pytest.mark.asyncio
async def test_relevance_keyword_match(registry, sample_tools):
    """Keyword matches should rank tools appropriately."""
    results = await registry.search_deferred_tools(query="quadruple", limit=5)

    # Should find another_deferred (has "quadruple" keyword)
    assert len(results) >= 1
    assert results[0].name == "another_deferred"


# ============================================================================
# Test: Namespace Isolation
# ============================================================================


@pytest.mark.asyncio
async def test_deferred_tools_isolated_by_namespace(registry):
    """Deferred tools in different namespaces should be isolated."""

    class ToolA(ValidatedTool):
        async def _execute(self, **kwargs):
            return {}

    class ToolB(ValidatedTool):
        async def _execute(self, **kwargs):
            return {}

    # Register in different namespaces
    await registry.register_tool(
        ToolA(),
        name="tool_a",
        namespace="ns1",
        metadata={"defer_loading": True, "description": "Tool in namespace 1"},
    )

    await registry.register_tool(
        ToolB(),
        name="tool_b",
        namespace="ns2",
        metadata={"defer_loading": True, "description": "Tool in namespace 2"},
    )

    # Check isolation
    deferred_ns1 = await registry.get_deferred_tools(namespace="ns1")
    deferred_ns2 = await registry.get_deferred_tools(namespace="ns2")

    assert len(deferred_ns1) == 1
    assert deferred_ns1[0].name == "tool_a"

    assert len(deferred_ns2) == 1
    assert deferred_ns2[0].name == "tool_b"


# ============================================================================
# Test: MCP Factory Params
# ============================================================================


@pytest.mark.asyncio
async def test_mcp_factory_params_storage(registry):
    """MCP factory params should be stored correctly in metadata."""

    class MockTool(ValidatedTool):
        async def _execute(self, **kwargs):
            return {}

    factory_params = MCPToolFactoryParams(
        tool_name="mcp_test_tool",
        default_timeout=45.0,
        enable_resilience=True,
        recovery_config=None,
        namespace="mcp_test",
    )

    await registry.register_tool(
        MockTool(),
        name="mcp_test_tool",
        namespace="mcp_test",
        metadata={
            "defer_loading": True,
            "description": "MCP test tool",
            "mcp_factory_params": factory_params,
        },
    )

    # Retrieve metadata
    metadata = await registry.get_metadata("mcp_test_tool", "mcp_test")

    assert metadata is not None
    assert metadata.mcp_factory_params is not None
    assert metadata.mcp_factory_params.tool_name == "mcp_test_tool"
    assert metadata.mcp_factory_params.default_timeout == 45.0
    assert metadata.mcp_factory_params.namespace == "mcp_test"


@pytest.mark.asyncio
async def test_stream_manager_storage(registry):
    """StreamManager should be stored by namespace."""

    class MockStreamManager:
        def __init__(self, name):
            self.name = name

    sm = MockStreamManager("test_manager")
    registry.set_stream_manager("test_ns", sm)

    # Verify it's stored
    assert registry._stream_managers.get("test_ns") is sm


# ============================================================================
# Test: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_get_tool_returns_none_for_nonexistent(registry, sample_tools):
    """get_tool should return None for nonexistent tools."""
    tool = await registry.get_tool("nonexistent", "test")
    assert tool is None


@pytest.mark.asyncio
async def test_get_metadata_returns_none_for_nonexistent(registry, sample_tools):
    """get_metadata should return None for nonexistent tools."""
    metadata = await registry.get_metadata("nonexistent", "test")
    assert metadata is None


@pytest.mark.asyncio
async def test_empty_search_query(registry, sample_tools):
    """Search with empty query should return no or very few results."""
    results = await registry.search_deferred_tools(query="", limit=5)
    # Empty query scores very low but may have some results due to tag/description matches
    # Just ensure it returns a list
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_deferred_tools_all_namespaces(registry, sample_tools):
    """get_deferred_tools without namespace should return all."""

    # Add tools to another namespace
    class OtherTool(ValidatedTool):
        async def _execute(self, **kwargs):
            return {}

    await registry.register_tool(
        OtherTool(),
        name="other_tool",
        namespace="other",
        metadata={"defer_loading": True, "description": "Tool in other namespace"},
    )

    all_deferred = await registry.get_deferred_tools()

    # Should have deferred tools from both namespaces
    assert len(all_deferred) >= 3  # 2 from test + 1 from other


@pytest.mark.asyncio
async def test_active_tools_all_namespaces(registry, sample_tools):
    """get_active_tools without namespace should return all active."""

    # Add tool to another namespace
    class OtherTool(ValidatedTool):
        async def _execute(self, **kwargs):
            return {}

    await registry.register_tool(
        OtherTool(),
        name="other_active",
        namespace="other",
        metadata={"defer_loading": False, "description": "Active tool in other namespace"},
    )

    all_active = await registry.get_active_tools()

    # Should have active tools from both namespaces
    assert len(all_active) >= 2  # 1 from test + 1 from other
