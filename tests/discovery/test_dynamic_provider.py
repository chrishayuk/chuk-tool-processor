# tests/discovery/test_dynamic_provider.py
"""Tests for the BaseDynamicToolProvider."""

from dataclasses import dataclass
from typing import Any

import pytest

from chuk_tool_processor.discovery import (
    BaseDynamicToolProvider,
    DynamicToolName,
    SearchResult,
)

# ============================================================================
# Test Tool Model
# ============================================================================


@dataclass
class MockTool:
    """Simple tool model for testing."""

    name: str
    namespace: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


# ============================================================================
# Concrete Implementation for Testing
# ============================================================================


class MockDynamicProvider(BaseDynamicToolProvider[MockTool]):
    """Concrete implementation of BaseDynamicToolProvider for testing."""

    def __init__(self, tools: list[MockTool] | None = None):
        super().__init__()
        self._tools = tools or []
        self._executed_tools: list[tuple[str, dict[str, Any]]] = []
        self._filter_called = False

    async def get_all_tools(self) -> list[MockTool]:
        """Return the test tools."""
        return self._tools

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Record and simulate tool execution."""
        self._executed_tools.append((tool_name, arguments))

        # Simulate different tool results
        if tool_name == "error_tool":
            return {"success": False, "error": "Simulated error"}

        if tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            return {"success": True, "result": a + b}

        return {"success": True, "result": f"Executed {tool_name}"}

    def filter_search_results(
        self,
        results: list[SearchResult[MockTool]],
    ) -> list[SearchResult[MockTool]]:
        """Track that filter was called."""
        self._filter_called = True
        return results


# ============================================================================
# DynamicToolName Enum Tests
# ============================================================================


class TestDynamicToolName:
    """Tests for DynamicToolName enum."""

    def test_list_tools_value(self):
        """Test list_tools value."""
        assert DynamicToolName.LIST_TOOLS.value == "list_tools"

    def test_search_tools_value(self):
        """Test search_tools value."""
        assert DynamicToolName.SEARCH_TOOLS.value == "search_tools"

    def test_get_tool_schema_value(self):
        """Test get_tool_schema value."""
        assert DynamicToolName.GET_TOOL_SCHEMA.value == "get_tool_schema"

    def test_call_tool_value(self):
        """Test call_tool value."""
        assert DynamicToolName.CALL_TOOL.value == "call_tool"

    def test_get_tool_schemas_value(self):
        """Test get_tool_schemas value."""
        assert DynamicToolName.GET_TOOL_SCHEMAS.value == "get_tool_schemas"

    def test_is_string_enum(self):
        """Test that it's a string enum."""
        assert isinstance(DynamicToolName.LIST_TOOLS, str)
        assert DynamicToolName.LIST_TOOLS == "list_tools"


# ============================================================================
# BaseDynamicToolProvider Tests
# ============================================================================


class TestBaseDynamicToolProvider:
    """Tests for BaseDynamicToolProvider base class."""

    @pytest.fixture
    def sample_tools(self) -> list[MockTool]:
        """Create sample tools."""
        return [
            MockTool(
                name="add",
                namespace="math",
                description="Add two numbers",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            ),
            MockTool(
                name="subtract",
                namespace="math",
                description="Subtract two numbers",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            ),
            MockTool(
                name="normal_cdf",
                namespace="stats",
                description="Calculate cumulative distribution function",
                parameters={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "mean": {"type": "number"},
                        "std": {"type": "number"},
                    },
                },
            ),
        ]

    @pytest.fixture
    def provider(self, sample_tools) -> MockDynamicProvider:
        """Create a provider with sample tools."""
        return MockDynamicProvider(sample_tools)

    # =========================================================================
    # get_dynamic_tools Tests
    # =========================================================================

    def test_get_dynamic_tools_returns_list(self, provider):
        """Test that get_dynamic_tools returns a list."""
        tools = provider.get_dynamic_tools()
        assert isinstance(tools, list)
        assert len(tools) == 5  # list, search, get_schema, get_schemas, call

    def test_get_dynamic_tools_has_list_tools(self, provider):
        """Test that list_tools is included."""
        tools = provider.get_dynamic_tools()
        names = [t["function"]["name"] for t in tools]
        assert "list_tools" in names

    def test_get_dynamic_tools_has_search_tools(self, provider):
        """Test that search_tools is included."""
        tools = provider.get_dynamic_tools()
        names = [t["function"]["name"] for t in tools]
        assert "search_tools" in names

    def test_get_dynamic_tools_has_get_tool_schema(self, provider):
        """Test that get_tool_schema is included."""
        tools = provider.get_dynamic_tools()
        names = [t["function"]["name"] for t in tools]
        assert "get_tool_schema" in names

    def test_get_dynamic_tools_has_call_tool(self, provider):
        """Test that call_tool is included."""
        tools = provider.get_dynamic_tools()
        names = [t["function"]["name"] for t in tools]
        assert "call_tool" in names

    def test_dynamic_tools_have_function_format(self, provider):
        """Test that tools are in function format."""
        tools = provider.get_dynamic_tools()
        for tool in tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    # =========================================================================
    # list_tools Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_list_tools_returns_all(self, provider, sample_tools):
        """Test that list_tools returns all tools."""
        results = await provider.list_tools()
        assert len(results) == len(sample_tools)

    @pytest.mark.asyncio
    async def test_list_tools_contains_names(self, provider):
        """Test that results contain tool names."""
        results = await provider.list_tools()
        names = [r["name"] for r in results]
        assert "add" in names
        assert "subtract" in names
        assert "normal_cdf" in names

    @pytest.mark.asyncio
    async def test_list_tools_contains_descriptions(self, provider):
        """Test that results contain descriptions."""
        results = await provider.list_tools()
        for result in results:
            assert "description" in result
            assert result["description"] is not None

    @pytest.mark.asyncio
    async def test_list_tools_contains_namespaces(self, provider):
        """Test that results contain namespaces."""
        results = await provider.list_tools()
        for result in results:
            assert "namespace" in result

    @pytest.mark.asyncio
    async def test_list_tools_respects_limit(self, provider):
        """Test that list_tools respects limit parameter."""
        results = await provider.list_tools(limit=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_tools_truncates_long_descriptions(self, provider):
        """Test that long descriptions are truncated."""
        long_desc = "A" * 300
        provider._tools = [MockTool(name="long", namespace="ns", description=long_desc)]
        results = await provider.list_tools()
        assert len(results[0]["description"]) <= 203  # 200 + "..."

    # =========================================================================
    # search_tools Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_search_tools_finds_exact_name(self, provider):
        """Test searching by exact name."""
        results = await provider.search_tools("add")
        assert len(results) > 0
        assert results[0]["name"] == "add"

    @pytest.mark.asyncio
    async def test_search_tools_finds_by_description(self, provider):
        """Test searching by description content."""
        results = await provider.search_tools("cumulative distribution")
        assert len(results) > 0
        names = [r["name"] for r in results]
        assert "normal_cdf" in names

    @pytest.mark.asyncio
    async def test_search_tools_returns_scores(self, provider):
        """Test that results include scores."""
        results = await provider.search_tools("add")
        for result in results:
            assert "score" in result
            assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_search_tools_returns_match_reasons(self, provider):
        """Test that results include match reasons."""
        results = await provider.search_tools("add")
        for result in results:
            assert "match_reasons" in result

    @pytest.mark.asyncio
    async def test_search_tools_respects_limit(self, provider):
        """Test that limit is respected."""
        results = await provider.search_tools("math", limit=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_tools_calls_filter(self, provider):
        """Test that filter_search_results is called."""
        await provider.search_tools("add")
        assert provider._filter_called

    @pytest.mark.asyncio
    async def test_search_tools_always_returns_results(self, provider):
        """Test that search always returns something (fallback)."""
        results = await provider.search_tools("xyznonexistent123")
        assert len(results) > 0

    # =========================================================================
    # get_tool_schema Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_tool_schema_returns_schema(self, provider):
        """Test getting schema for existing tool."""
        schema = await provider.get_tool_schema("add")
        assert "function" in schema
        assert schema["function"]["name"] == "add"

    @pytest.mark.asyncio
    async def test_get_tool_schema_includes_parameters(self, provider):
        """Test that schema includes parameters."""
        schema = await provider.get_tool_schema("add")
        assert "parameters" in schema["function"]
        assert "properties" in schema["function"]["parameters"]
        assert "a" in schema["function"]["parameters"]["properties"]
        assert "b" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_get_tool_schema_includes_description(self, provider):
        """Test that schema includes description."""
        schema = await provider.get_tool_schema("add")
        assert "description" in schema["function"]
        assert "Add two numbers" in schema["function"]["description"]

    @pytest.mark.asyncio
    async def test_get_tool_schema_not_found(self, provider):
        """Test error for non-existent tool."""
        schema = await provider.get_tool_schema("nonexistent")
        assert "error" in schema

    @pytest.mark.asyncio
    async def test_get_tool_schema_suggests_similar(self, provider):
        """Test that not-found error includes suggestions."""
        schema = await provider.get_tool_schema("ad")  # Close to "add"
        assert "error" in schema
        assert "suggestions" in schema

    @pytest.mark.asyncio
    async def test_get_tool_schema_caches_result(self, provider):
        """Test that schema is cached."""
        await provider.get_tool_schema("add")
        assert "add" in provider._tool_cache

    @pytest.mark.asyncio
    async def test_get_tool_schema_resolves_alias(self, provider):
        """Test that aliases are resolved."""
        # Create a provider with tools that can be aliased
        provider._tools = [MockTool(name="normal_cdf", namespace="math", description="CDF")]
        provider._tool_cache.clear()

        # Search by camelCase alias
        schema = await provider.get_tool_schema("normalCdf")
        assert "function" in schema
        assert schema["function"]["name"] == "normal_cdf"

    # =========================================================================
    # call_tool Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_call_tool_executes(self, provider):
        """Test that call_tool executes the tool."""
        result = await provider.call_tool("add", {"a": 1, "b": 2})
        assert result["success"] is True
        assert result["result"] == 3

    @pytest.mark.asyncio
    async def test_call_tool_records_execution(self, provider):
        """Test that execution is recorded."""
        await provider.call_tool("add", {"a": 5, "b": 3})
        assert len(provider._executed_tools) == 1
        assert provider._executed_tools[0] == ("add", {"a": 5, "b": 3})

    @pytest.mark.asyncio
    async def test_call_tool_handles_errors(self, provider):
        """Test that errors are returned properly."""
        provider._tools.append(MockTool(name="error_tool", namespace="test", description="Errors"))
        result = await provider.call_tool("error_tool", {})
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_tool_auto_fetches_schema(self, provider):
        """Test that schema is auto-fetched if not known."""
        provider._schema_fetched.clear()
        await provider.call_tool("add", {"a": 1, "b": 2})
        assert "add" in provider._schema_fetched

    @pytest.mark.asyncio
    async def test_call_tool_resolves_alias(self, provider):
        """Test that aliases are resolved for execution."""
        # This should work even with camelCase
        await provider.get_tool_schema("add")  # Warm up cache
        await provider.call_tool("add", {"a": 1, "b": 2})

        executed_name = provider._executed_tools[-1][0]
        assert executed_name == "add"

    # =========================================================================
    # execute_dynamic_tool Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_list(self, provider):
        """Test executing list_tools via execute_dynamic_tool."""
        result = await provider.execute_dynamic_tool("list_tools", {"limit": 2})
        assert result["success"] is True
        assert "result" in result
        assert "count" in result
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_search(self, provider):
        """Test executing search_tools via execute_dynamic_tool."""
        result = await provider.execute_dynamic_tool("search_tools", {"query": "add", "limit": 5})
        assert result["success"] is True
        assert "result" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_get_schema(self, provider):
        """Test executing get_tool_schema via execute_dynamic_tool."""
        result = await provider.execute_dynamic_tool("get_tool_schema", {"tool_name": "add"})
        assert "function" in result

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_get_schemas(self, provider):
        """Test executing get_tool_schemas via execute_dynamic_tool."""
        result = await provider.execute_dynamic_tool("get_tool_schemas", {"tool_names": ["add", "subtract"]})
        assert "schemas" in result
        assert "count" in result
        assert result["count"] == 2
        assert len(result["schemas"]) == 2

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_get_schemas_with_errors(self, provider):
        """Test get_tool_schemas with some missing tools."""
        result = await provider.execute_dynamic_tool("get_tool_schemas", {"tool_names": ["add", "nonexistent_tool"]})
        assert "schemas" in result
        assert "errors" in result
        assert result["count"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["tool_name"] == "nonexistent_tool"

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_call(self, provider):
        """Test executing call_tool via execute_dynamic_tool."""
        result = await provider.execute_dynamic_tool("call_tool", {"tool_name": "add", "a": 1, "b": 2})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_unknown(self, provider):
        """Test executing unknown dynamic tool."""
        result = await provider.execute_dynamic_tool("unknown_tool", {})
        assert "error" in result

    # =========================================================================
    # is_dynamic_tool Tests
    # =========================================================================

    def test_is_dynamic_tool_list_tools(self, provider):
        """Test recognizing list_tools as dynamic."""
        assert provider.is_dynamic_tool("list_tools") is True

    def test_is_dynamic_tool_search_tools(self, provider):
        """Test recognizing search_tools as dynamic."""
        assert provider.is_dynamic_tool("search_tools") is True

    def test_is_dynamic_tool_get_tool_schema(self, provider):
        """Test recognizing get_tool_schema as dynamic."""
        assert provider.is_dynamic_tool("get_tool_schema") is True

    def test_is_dynamic_tool_call_tool(self, provider):
        """Test recognizing call_tool as dynamic."""
        assert provider.is_dynamic_tool("call_tool") is True

    def test_is_dynamic_tool_get_tool_schemas(self, provider):
        """Test recognizing get_tool_schemas as dynamic."""
        assert provider.is_dynamic_tool("get_tool_schemas") is True

    def test_is_dynamic_tool_regular_tool(self, provider):
        """Test that regular tools are not dynamic."""
        assert provider.is_dynamic_tool("add") is False
        assert provider.is_dynamic_tool("normal_cdf") is False

    # =========================================================================
    # Cache Invalidation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_tool_cache(self, provider):
        """Test that invalidate_cache clears the tool cache."""
        await provider.get_tool_schema("add")
        assert len(provider._tool_cache) > 0

        provider.invalidate_cache()
        assert len(provider._tool_cache) == 0

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_schema_fetched(self, provider):
        """Test that invalidate_cache clears schema_fetched tracking."""
        await provider.get_tool_schema("add")
        assert len(provider._schema_fetched) > 0

        provider.invalidate_cache()
        assert len(provider._schema_fetched) == 0

    @pytest.mark.asyncio
    async def test_invalidate_cache_resets_index_flag(self, provider):
        """Test that invalidate_cache resets the index flag."""
        await provider.search_tools("add")
        assert provider._tools_indexed is True

        provider.invalidate_cache()
        assert provider._tools_indexed is False

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_list_tools_handles_exception(self):
        """Test that list_tools handles exceptions gracefully."""

        class FailingProvider(MockDynamicProvider):
            async def get_all_tools(self):
                raise RuntimeError("Simulated failure")

        provider = FailingProvider()
        results = await provider.list_tools()
        assert results == []

    @pytest.mark.asyncio
    async def test_search_tools_handles_exception(self):
        """Test that search_tools handles exceptions gracefully."""

        class FailingProvider(MockDynamicProvider):
            async def get_all_tools(self):
                raise RuntimeError("Simulated failure")

        provider = FailingProvider()
        results = await provider.search_tools("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_tool_schema_handles_exception(self):
        """Test that get_tool_schema handles exceptions gracefully."""

        class FailingProvider(MockDynamicProvider):
            async def get_all_tools(self):
                raise RuntimeError("Simulated failure")

        provider = FailingProvider()
        result = await provider.get_tool_schema("test")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_tool_handles_exception(self):
        """Test that call_tool handles exceptions gracefully."""

        class FailingProvider(MockDynamicProvider):
            async def execute_tool(self, tool_name, arguments):
                raise RuntimeError("Execution failed")

        provider = FailingProvider([MockTool(name="test", namespace="ns", description="Test")])
        result = await provider.call_tool("test", {})
        assert result["success"] is False
        assert "error" in result

    # =========================================================================
    # Edge Cases
    # =========================================================================

    @pytest.mark.asyncio
    async def test_search_with_empty_results(self):
        """Test search when no tools exist."""
        provider = MockDynamicProvider([])
        results = await provider.search_tools("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_call_tool_with_unknown_tool(self):
        """Test calling a tool that doesn't exist."""
        provider = MockDynamicProvider([MockTool(name="exists", namespace="ns", description="Exists")])
        result = await provider.call_tool("nonexistent", {})
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_call_tool_resolves_via_alias(self, provider):
        """Test that call_tool resolves tools via alias."""
        # Call with camelCase alias
        await provider.call_tool("normalCdf", {"x": 1})
        # Should resolve to normal_cdf
        executed = provider._executed_tools[-1]
        assert executed[0] == "normal_cdf"

    @pytest.mark.asyncio
    async def test_get_tool_schema_with_cache_hit(self, provider):
        """Test that subsequent calls return cached schema."""
        # First call - cache miss
        schema1 = await provider.get_tool_schema("add")
        # Second call - cache hit
        schema2 = await provider.get_tool_schema("add")
        assert schema1 == schema2

    @pytest.mark.asyncio
    async def test_search_reindexes_when_tools_change(self, provider):
        """Test that search reindexes when tool count changes."""
        # First search - indexes tools
        await provider.search_tools("add")
        assert provider._tools_indexed is True

        # Add a tool
        provider._tools.append(MockTool(name="new_tool", namespace="ns", description="New"))

        # Second search - should reindex
        results = await provider.search_tools("new")
        assert any(r["name"] == "new_tool" for r in results)

    @pytest.mark.asyncio
    async def test_get_tool_name_override(self):
        """Test that get_tool_name can be overridden."""

        class CustomProvider(MockDynamicProvider):
            def get_tool_name(self, tool):
                return f"custom_{tool.name}"

        provider = CustomProvider([MockTool(name="test", namespace="ns", description="Test")])
        results = await provider.list_tools()
        assert results[0]["name"] == "custom_test"

    @pytest.mark.asyncio
    async def test_get_tool_namespace_override(self):
        """Test that get_tool_namespace can be overridden."""

        class CustomProvider(MockDynamicProvider):
            def get_tool_namespace(self, tool):
                return f"custom_{tool.namespace}"

        provider = CustomProvider([MockTool(name="test", namespace="ns", description="Test")])
        results = await provider.list_tools()
        assert results[0]["namespace"] == "custom_ns"

    @pytest.mark.asyncio
    async def test_execute_dynamic_tool_list_returns_total(self, provider):
        """Test that list_tools includes total_available count."""
        result = await provider.execute_dynamic_tool("list_tools", {})
        assert "total_available" in result
        assert result["total_available"] == 3  # 3 sample tools

    @pytest.mark.asyncio
    async def test_get_tool_schema_no_suggestions_when_no_similar(self):
        """Test schema not found with no similar tools."""
        provider = MockDynamicProvider([MockTool(name="xyz123", namespace="ns", description="Xyz")])
        result = await provider.get_tool_schema("completely_different_abc")
        assert "error" in result
        # May or may not have suggestions depending on fuzzy match

    @pytest.mark.asyncio
    async def test_get_tool_schema_with_namespace_prefix(self, provider):
        """Test getting schema with full namespace.name format."""
        schema = await provider.get_tool_schema("math.add")
        assert "function" in schema
        assert schema["function"]["name"] == "add"

    @pytest.mark.asyncio
    async def test_search_tools_truncates_long_descriptions(self, provider):
        """Test that search results truncate long descriptions."""
        long_desc = "X" * 300
        provider._tools = [MockTool(name="long", namespace="ns", description=long_desc)]
        provider._tools_indexed = False

        results = await provider.search_tools("long")
        assert len(results[0]["description"]) <= 203
