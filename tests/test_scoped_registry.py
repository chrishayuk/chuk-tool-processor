# tests/test_scoped_registry.py
"""Tests for scoped registry functionality."""

from __future__ import annotations

import asyncio

import pytest

from chuk_tool_processor import ToolProcessor, create_registry
from chuk_tool_processor.registry import ToolRegistryInterface
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry


class MockTool:
    """Mock tool for testing."""

    async def execute(self, message: str = "hello") -> dict:
        return {"echo": message}


class AnotherMockTool:
    """Another mock tool for testing."""

    async def execute(self, value: int = 42) -> dict:
        return {"value": value * 2}


class TestCreateRegistry:
    """Test create_registry factory function."""

    def test_create_registry_returns_interface(self):
        """Test create_registry returns ToolRegistryInterface."""
        registry = create_registry()
        assert isinstance(registry, ToolRegistryInterface)

    def test_create_registry_returns_inmemory(self):
        """Test create_registry returns InMemoryToolRegistry."""
        registry = create_registry()
        assert isinstance(registry, InMemoryToolRegistry)

    def test_create_registry_returns_fresh_instance(self):
        """Test each call returns a new instance."""
        reg1 = create_registry()
        reg2 = create_registry()

        assert reg1 is not reg2

    @pytest.mark.asyncio
    async def test_registries_are_isolated(self):
        """Test tools registered in one registry don't appear in another."""
        reg1 = create_registry()
        reg2 = create_registry()

        # Register tool only in reg1
        await reg1.register_tool(MockTool, name="mock_tool")

        # Should exist in reg1
        tool = await reg1.get_tool("mock_tool")
        assert tool is not None

        # Should NOT exist in reg2
        tool = await reg2.get_tool("mock_tool")
        assert tool is None


class TestScopedRegistryWithProcessor:
    """Test using scoped registries with ToolProcessor."""

    @pytest.mark.asyncio
    async def test_processor_with_scoped_registry(self):
        """Test ToolProcessor works with a scoped registry."""
        registry = create_registry()
        await registry.register_tool(MockTool, name="mock_tool")

        processor = ToolProcessor(registry=registry)
        await processor.initialize()

        # Should find the tool
        tools = await processor.list_tools()
        assert "mock_tool" in tools

    @pytest.mark.asyncio
    async def test_multiple_processors_isolated(self):
        """Test multiple processors with different registries are isolated."""
        # Create two isolated registries
        reg1 = create_registry()
        reg2 = create_registry()

        # Register different tools in each
        await reg1.register_tool(MockTool, name="tool_in_reg1")
        await reg2.register_tool(AnotherMockTool, name="tool_in_reg2")

        # Create processors
        proc1 = ToolProcessor(registry=reg1)
        proc2 = ToolProcessor(registry=reg2)

        await proc1.initialize()
        await proc2.initialize()

        # Each processor should only see its own tools
        tools1 = await proc1.list_tools()
        tools2 = await proc2.list_tools()

        assert "tool_in_reg1" in tools1
        assert "tool_in_reg2" not in tools1

        assert "tool_in_reg2" in tools2
        assert "tool_in_reg1" not in tools2

    @pytest.mark.asyncio
    async def test_concurrent_scoped_processors(self):
        """Test concurrent access to different scoped processors."""
        results = {}

        async def process_with_registry(name: str, tool_class):
            registry = create_registry()
            await registry.register_tool(tool_class, name="tool")

            processor = ToolProcessor(registry=registry)
            await processor.initialize()

            tools = await processor.list_tools()
            results[name] = tools

        await asyncio.gather(
            process_with_registry("proc1", MockTool),
            process_with_registry("proc2", AnotherMockTool),
        )

        # Both should have registered their tool
        assert "tool" in results["proc1"]
        assert "tool" in results["proc2"]


class TestScopedRegistryNamespaces:
    """Test namespace isolation within scoped registries."""

    @pytest.mark.asyncio
    async def test_namespaces_isolated_per_registry(self):
        """Test namespaces in one registry don't affect another."""
        reg1 = create_registry()
        reg2 = create_registry()

        # Register in namespace "ns1" in reg1
        await reg1.register_tool(MockTool, name="tool", namespace="ns1")

        # Register in same namespace name in reg2 but different tool
        await reg2.register_tool(AnotherMockTool, name="tool", namespace="ns1")

        # Each registry should have its own version
        tool1 = await reg1.get_tool("tool", "ns1")
        tool2 = await reg2.get_tool("tool", "ns1")

        # They should be different classes
        assert tool1 is MockTool
        assert tool2 is AnotherMockTool


class TestScopedRegistryTestIsolation:
    """Test that scoped registries enable proper test isolation."""

    @pytest.mark.asyncio
    async def test_isolated_fixture_pattern_1(self):
        """First test using isolated pattern."""
        registry = create_registry()
        await registry.register_tool(MockTool, name="test_tool")

        processor = ToolProcessor(registry=registry)
        async with processor:
            tools = await processor.list_tools()
            assert "test_tool" in tools

    @pytest.mark.asyncio
    async def test_isolated_fixture_pattern_2(self):
        """Second test using isolated pattern - should be independent."""
        registry = create_registry()
        await registry.register_tool(MockTool, name="test_tool")

        processor = ToolProcessor(registry=registry)
        async with processor:
            tools = await processor.list_tools()
            assert "test_tool" in tools


class TestMultiTenantPattern:
    """Test multi-tenant usage pattern with scoped registries."""

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test tenant registries are properly isolated."""
        tenant_registries: dict[str, ToolRegistryInterface] = {}

        async def get_tenant_registry(tenant_id: str) -> ToolRegistryInterface:
            if tenant_id not in tenant_registries:
                registry = create_registry()
                tenant_registries[tenant_id] = registry
            return tenant_registries[tenant_id]

        # Register tools for tenant A
        reg_a = await get_tenant_registry("tenant_a")
        await reg_a.register_tool(MockTool, name="tenant_a_tool")

        # Register tools for tenant B
        reg_b = await get_tenant_registry("tenant_b")
        await reg_b.register_tool(AnotherMockTool, name="tenant_b_tool")

        # Verify isolation
        tools_a = await reg_a.list_tools()
        tools_b = await reg_b.list_tools()

        tool_names_a = {t.name for t in tools_a}
        tool_names_b = {t.name for t in tools_b}

        assert "tenant_a_tool" in tool_names_a
        assert "tenant_b_tool" not in tool_names_a

        assert "tenant_b_tool" in tool_names_b
        assert "tenant_a_tool" not in tool_names_b

    @pytest.mark.asyncio
    async def test_tenant_processors(self):
        """Test creating processors per tenant."""
        tenant_processors: dict[str, ToolProcessor] = {}

        async def get_tenant_processor(tenant_id: str) -> ToolProcessor:
            if tenant_id not in tenant_processors:
                registry = create_registry()
                # Register tenant-specific tools
                await registry.register_tool(MockTool, name=f"{tenant_id}_tool")
                processor = ToolProcessor(registry=registry)
                await processor.initialize()
                tenant_processors[tenant_id] = processor
            return tenant_processors[tenant_id]

        proc_a = await get_tenant_processor("tenant_a")
        proc_b = await get_tenant_processor("tenant_b")

        tools_a = await proc_a.list_tools()
        tools_b = await proc_b.list_tools()

        assert "tenant_a_tool" in tools_a
        assert "tenant_b_tool" in tools_b
        assert "tenant_b_tool" not in tools_a
        assert "tenant_a_tool" not in tools_b
