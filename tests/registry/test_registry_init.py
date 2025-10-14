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
        from chuk_tool_processor.registry.decorators import _PENDING_REGISTRATIONS
        from chuk_tool_processor.registry.provider import ToolRegistryProvider

        # Clear any existing state
        _PENDING_REGISTRATIONS.clear()

        # Get a fresh registry for this test
        await ToolRegistryProvider.reset()

        # Register a test tool
        @register_tool(name="test_init_tool_unique", namespace="test_init_ns")
        class TestInitTool:
            async def execute(self, x: int) -> int:
                return x * 2

        # Verify there's a pending registration
        assert len(_PENDING_REGISTRATIONS) > 0

        # Initialize should process this registration
        registry = await initialize()

        # Check if the tool was registered
        tool = await registry.get_tool("test_init_tool_unique", namespace="test_init_ns")
        assert tool is not None
        # Check if the tool is a class or has __name__ attribute
        assert hasattr(tool, "__name__"), f"Tool should have __name__, got {type(tool)}: {tool}"
        assert tool.__name__ == "TestInitTool"
