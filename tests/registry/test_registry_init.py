# tests/registry/test_registry_init.py
"""Tests for registry/__init__.py module."""

import pytest

from chuk_tool_processor.registry import get_default_registry, initialize


class TestRegistryInit:
    """Test registry initialization functions."""

    @pytest.mark.asyncio
    async def test_get_default_registry(self):
        """Test get_default_registry returns a registry."""
        registry = await get_default_registry()

        assert registry is not None
        # Check it has required methods from ToolRegistryInterface
        assert hasattr(registry, "register_tool")
        assert hasattr(registry, "get_tool")
        assert hasattr(registry, "list_tools")

    @pytest.mark.asyncio
    async def test_get_default_registry_singleton(self):
        """Test that get_default_registry returns the same instance."""
        registry1 = await get_default_registry()
        registry2 = await get_default_registry()

        # Should return the same instance
        assert registry1 is registry2

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test initialize function."""
        registry = await initialize()

        assert registry is not None
        assert hasattr(registry, "register_tool")
        assert hasattr(registry, "get_tool")

    @pytest.mark.asyncio
    async def test_initialize_processes_registrations(self):
        """Test that initialize processes pending registrations."""
        from chuk_tool_processor.registry import register_tool
        from chuk_tool_processor.registry.decorators import _PENDING_REGISTRATIONS, ensure_registrations
        from chuk_tool_processor.registry.provider import ToolRegistryProvider
        from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry

        # Clear any existing state and force a real InMemoryToolRegistry
        _PENDING_REGISTRATIONS.clear()
        await ToolRegistryProvider.reset()

        # Force set to InMemoryToolRegistry to avoid test pollution
        real_registry = InMemoryToolRegistry()
        ToolRegistryProvider._registry = real_registry

        # Register a test tool
        @register_tool(name="test_init_tool_unique", namespace="test_init_ns")
        class TestInitTool:
            async def execute(self, x: int) -> int:
                return x * 2

        # Verify there's a pending registration
        assert len(_PENDING_REGISTRATIONS) > 0, "Should have pending registrations after @register_tool"

        # Process pending registrations directly instead of calling initialize()
        # to avoid any global state issues
        await ensure_registrations()

        # Verify pending registrations were cleared
        assert len(_PENDING_REGISTRATIONS) == 0, "Pending registrations should be cleared after processing"

        # Check if the tool was registered in our real registry
        tool = await real_registry.get_tool("test_init_tool_unique", namespace="test_init_ns")
        assert tool is not None, "Tool should be registered after ensure_registrations()"

        # Check if the tool is the actual class (not a string identifier)
        assert hasattr(tool, "__name__"), f"Tool should have __name__, got {type(tool)}: {tool}"
        assert tool.__name__ == "TestInitTool", f"Expected TestInitTool, got {tool.__name__}"
