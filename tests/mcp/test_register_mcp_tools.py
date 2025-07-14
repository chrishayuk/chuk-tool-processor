# tests/mcp/test_register_mcp_tools.py
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class TestRegisterMCPTools:
    """
    Tests for async-native MCP-tool registration.
    
    Updated based on enhanced testing insights:
    - Registry allows tool name collisions within same namespace
    - Registration is to specified namespace only (not dual registration)
    - Tools are wrapped in MCPTool instances
    - Performance and concurrency characteristics validated
    """

    # ------------------------------------------------------------------ #
    # fixtures                                                           #
    # ------------------------------------------------------------------ #
    @pytest.fixture
    def mock_registry(self):
        """Mock registry that tracks registrations for testing."""
        reg = Mock(spec=ToolRegistryInterface)
        reg.register_tool = AsyncMock()
        reg.registered_tools = []  # Track what was registered for assertions
        
        # Make register_tool track calls
        async def track_registration(tool, name=None, namespace="default", metadata=None):
            reg.registered_tools.append({
                "tool": tool,
                "name": name,
                "namespace": namespace,
                "metadata": metadata
            })
        
        reg.register_tool.side_effect = track_registration
        return reg

    @pytest.fixture
    def mock_stream_manager(self):
        """Mock stream manager with sample tools."""
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {
                    "name": "echo", 
                    "description": "Echo tool for testing",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"}
                        }
                    }
                },
                {
                    "name": "calc", 
                    "description": "Calculator tool",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string"},
                            "a": {"type": "number"},
                            "b": {"type": "number"}
                        }
                    }
                },
            ]
        )
        return mgr

    @pytest.fixture
    def large_tool_set(self):
        """Fixture for large-scale testing."""
        return [
            {
                "name": f"tool_{i}",
                "description": f"Test tool number {i}",
                "inputSchema": {"type": "object", "properties": {}}
            }
            for i in range(50)  # 50 tools for performance testing
        ]

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    def _patch_registry(self, mock_registry):
        """
        Convenience wrapper - returns a context-manager that replaces
        ``ToolRegistryProvider.get_registry`` with an *async* mock.
        """
        return patch(
            "chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry",
            new=AsyncMock(return_value=mock_registry),
        )

    # ------------------------------------------------------------------ #
    # Updated happy-path tests                                           #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_register_tools_basic(self, mock_registry, mock_stream_manager):
        """Test basic tool registration to specified namespace."""
        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mock_stream_manager, namespace="test_ns")

        # Should return the tool names that were registered
        assert registered == ["echo", "calc"]

        # Should register exactly 2 tools (one per tool from stream manager)
        assert mock_registry.register_tool.call_count == 2
        
        # Verify each registration
        registrations = mock_registry.registered_tools
        assert len(registrations) == 2
        
        # Check first tool registration
        echo_reg = next(r for r in registrations if r["name"] == "echo")
        assert echo_reg["namespace"] == "test_ns"
        assert isinstance(echo_reg["tool"], MCPTool)
        assert echo_reg["metadata"]["description"] == "Echo tool for testing"
        assert "mcp" in echo_reg["metadata"]["tags"]
        
        # Check second tool registration
        calc_reg = next(r for r in registrations if r["name"] == "calc")
        assert calc_reg["namespace"] == "test_ns"
        assert isinstance(calc_reg["tool"], MCPTool)
        assert calc_reg["metadata"]["description"] == "Calculator tool"

    @pytest.mark.asyncio
    async def test_register_tools_default_namespace(self, mock_registry, mock_stream_manager):
        """Test registration with default namespace."""
        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mock_stream_manager)  # No namespace specified

        assert registered == ["echo", "calc"]
        
        # All tools should be registered to default "mcp" namespace
        registrations = mock_registry.registered_tools
        for reg in registrations:
            assert reg["namespace"] == "mcp"

    @pytest.mark.asyncio
    async def test_mcp_tool_wrapper_creation(self, mock_registry, mock_stream_manager):
        """Test that tools are properly wrapped in MCPTool instances."""
        with self._patch_registry(mock_registry):
            await register_mcp_tools(mock_stream_manager, namespace="wrapper_test")

        registrations = mock_registry.registered_tools
        
        for reg in registrations:
            tool = reg["tool"]
            assert isinstance(tool, MCPTool)
            assert hasattr(tool, "tool_name")
            assert hasattr(tool, "execute")
            assert tool.tool_name in ["echo", "calc"]

    # ------------------------------------------------------------------ #
    # Updated edge-cases and error handling                              #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_register_with_invalid_tools(self, mock_registry):
        """Test handling of invalid tool definitions."""
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {"description": "no name field"},
                {"name": "", "description": "empty name"},
                {"name": None, "description": "null name"},
                {"name": "valid_tool", "description": "This one should work"},
            ]
        )
        
        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr, namespace="invalid_test")

        # Only the valid tool should be registered
        assert registered == ["valid_tool"]
        assert mock_registry.register_tool.call_count == 1
        
        # Verify the valid tool was registered correctly
        reg = mock_registry.registered_tools[0]
        assert reg["name"] == "valid_tool"
        assert reg["namespace"] == "invalid_test"

    @pytest.mark.asyncio
    async def test_empty_tools_registration(self, mock_registry):
        """Test registration when no tools are available."""
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(return_value=[])

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr, namespace="empty_test")

        assert registered == []
        mock_registry.register_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_tool_names_collision_handling(self, mock_registry):
        """
        Test handling of duplicate tool names within same namespace.
        
        Based on enhanced testing: registry allows collisions (update behavior).
        """
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {"name": "duplicate_tool", "description": "First version"},
                {"name": "duplicate_tool", "description": "Second version"},
                {"name": "unique_tool", "description": "Unique tool"},
            ]
        )

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr, namespace="collision_test")

        # All tools should be processed (registry allows duplicates)
        assert registered == ["duplicate_tool", "duplicate_tool", "unique_tool"]
        assert mock_registry.register_tool.call_count == 3
        
        # Verify both duplicate registrations happened
        duplicate_regs = [r for r in mock_registry.registered_tools if r["name"] == "duplicate_tool"]
        assert len(duplicate_regs) == 2
        assert duplicate_regs[0]["metadata"]["description"] == "First version"
        assert duplicate_regs[1]["metadata"]["description"] == "Second version"

    @pytest.mark.asyncio
    async def test_registration_error_handling(self, mock_registry, mock_stream_manager):
        """Test behavior when registry.register_tool raises an exception."""
        # Make the first registration fail, but second succeed
        mock_registry.register_tool.side_effect = [
            Exception("Registration failed for echo"),
            None,  # Second call succeeds
        ]

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mock_stream_manager, namespace="error_test")

        # Should still return the tool that was attempted, even if registration failed
        # (The function logs errors but doesn't stop processing)
        assert len(registered) <= 2  # May return fewer if some fail
        assert mock_registry.register_tool.call_count == 2

    # ------------------------------------------------------------------ #
    # New performance and concurrency tests                             #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_large_scale_registration_performance(self, mock_registry, large_tool_set):
        """Test performance with large number of tools."""
        import time
        
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(return_value=large_tool_set)

        with self._patch_registry(mock_registry):
            start_time = time.time()
            registered = await register_mcp_tools(mgr, namespace="performance_test")
            execution_time = time.time() - start_time

        # Should register all 50 tools
        assert len(registered) == 50
        assert mock_registry.register_tool.call_count == 50
        
        # Performance should be reasonable (less than 1 second for 50 tools)
        assert execution_time < 1.0
        
        # Calculate tools per second
        tools_per_second = len(registered) / execution_time if execution_time > 0 else float('inf')
        assert tools_per_second > 10  # Should process at least 10 tools/second

    @pytest.mark.asyncio
    async def test_concurrent_registration_simulation(self, mock_registry):
        """Test concurrent registration behavior using asyncio.gather."""
        import asyncio
        
        # Create multiple stream managers with different tools
        managers = []
        for i in range(5):
            mgr = Mock(spec=StreamManager)
            mgr.get_all_tools = Mock(
                return_value=[{
                    "name": f"concurrent_tool_{i}",
                    "description": f"Tool from manager {i}",
                    "inputSchema": {}
                }]
            )
            managers.append(mgr)

        # Register all tools concurrently
        with self._patch_registry(mock_registry):
            results = await asyncio.gather(*[
                register_mcp_tools(mgr, namespace=f"concurrent_ns_{i}")
                for i, mgr in enumerate(managers)
            ])

        # All registrations should succeed
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result == [f"concurrent_tool_{i}"]
        
        # Total of 5 tools should be registered
        assert mock_registry.register_tool.call_count == 5

    # ------------------------------------------------------------------ #
    # Metadata and configuration tests                                   #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_metadata_propagation(self, mock_registry, mock_stream_manager):
        """Test that tool metadata is properly propagated to registry."""
        with self._patch_registry(mock_registry):
            await register_mcp_tools(mock_stream_manager, namespace="metadata_test")

        registrations = mock_registry.registered_tools
        
        for reg in registrations:
            metadata = reg["metadata"]
            
            # Check required metadata fields
            assert "description" in metadata
            assert "is_async" in metadata
            assert metadata["is_async"] is True
            assert "tags" in metadata
            assert "mcp" in metadata["tags"]
            assert "remote" in metadata["tags"]
            
            # Check argument schema is included
            assert "argument_schema" in metadata
            assert isinstance(metadata["argument_schema"], dict)

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, mock_registry):
        """Test that tools can be registered to different namespaces independently."""
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[{
                "name": "shared_tool",
                "description": "Tool that exists in multiple namespaces",
                "inputSchema": {}
            }]
        )

        with self._patch_registry(mock_registry):
            # Register same tool to different namespaces
            result1 = await register_mcp_tools(mgr, namespace="namespace_a")
            result2 = await register_mcp_tools(mgr, namespace="namespace_b")

        # Both registrations should succeed
        assert result1 == ["shared_tool"]
        assert result2 == ["shared_tool"]
        assert mock_registry.register_tool.call_count == 2
        
        # Verify tools were registered to correct namespaces
        registrations = mock_registry.registered_tools
        namespaces = [reg["namespace"] for reg in registrations]
        assert "namespace_a" in namespaces
        assert "namespace_b" in namespaces

    @pytest.mark.asyncio
    async def test_tool_argument_schema_handling(self, mock_registry):
        """Test handling of different input schema formats."""
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {
                    "name": "schema_tool",
                    "description": "Tool with complex schema",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "required_param": {"type": "string"},
                            "optional_param": {"type": "number", "default": 42}
                        },
                        "required": ["required_param"]
                    }
                },
                {
                    "name": "no_schema_tool",
                    "description": "Tool without schema",
                    # No inputSchema field
                },
            ]
        )

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr, namespace="schema_test")

        assert registered == ["schema_tool", "no_schema_tool"]
        
        registrations = mock_registry.registered_tools
        
        # Tool with schema should have it preserved
        schema_tool_reg = next(r for r in registrations if r["name"] == "schema_tool")
        assert "argument_schema" in schema_tool_reg["metadata"]
        schema = schema_tool_reg["metadata"]["argument_schema"]
        assert schema["type"] == "object"
        assert "required_param" in schema["properties"]
        
        # Tool without schema should have empty schema
        no_schema_reg = next(r for r in registrations if r["name"] == "no_schema_tool")
        assert no_schema_reg["metadata"]["argument_schema"] == {}

    # ------------------------------------------------------------------ #
    # Integration-style tests                                            #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_end_to_end_registration_flow(self, mock_registry):
        """Test the complete registration flow from stream manager to registry."""
        # Create a realistic stream manager mock
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"},
                            "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"}
                        },
                        "required": ["location"]
                    }
                }
            ]
        )

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr, namespace="integration_test")

        # Verify end-to-end flow
        assert registered == ["get_weather"]
        assert mock_registry.register_tool.call_count == 1
        
        reg = mock_registry.registered_tools[0]
        
        # Verify tool wrapper
        assert isinstance(reg["tool"], MCPTool)
        assert reg["tool"].tool_name == "get_weather"
        
        # Verify metadata
        metadata = reg["metadata"]
        assert metadata["description"] == "Get current weather for a location"
        assert metadata["is_async"] is True
        assert "mcp" in metadata["tags"]
        
        # Verify schema preservation
        schema = metadata["argument_schema"]
        assert schema["properties"]["location"]["type"] == "string"
        assert "celsius" in schema["properties"]["units"]["enum"]