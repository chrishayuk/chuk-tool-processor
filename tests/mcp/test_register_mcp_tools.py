# tests/mcp/test_register_mcp_tools.py
import pytest
from unittest.mock import Mock, patch

from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class TestRegisterMCPTools:
    """Test MCP tools registration."""
    
    @pytest.fixture
    def mock_registry(self):
        """Mock tool registry."""
        mock = Mock(spec=ToolRegistryInterface)
        mock.register_tool = Mock()
        return mock
    
    @pytest.fixture
    def mock_stream_manager(self):
        """Mock stream manager."""
        mock = Mock(spec=StreamManager)
        tools = [
            {"name": "echo", "description": "Echo tool", "inputSchema": {}},
            {"name": "calc", "description": "Calculator", "inputSchema": {}}
        ]
        mock.get_all_tools = Mock(return_value=tools)
        return mock
    
    def test_register_tools(self, mock_registry, mock_stream_manager):
        """Test registering MCP tools."""
        # Mock the registry provider
        with patch('chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry', return_value=mock_registry):
            registered = register_mcp_tools(mock_stream_manager, namespace="mcp")
            
            # Check registration calls
            assert len(registered) == 2
            assert "echo" in registered
            assert "calc" in registered
            
            # Verify register_tool was called with correct args
            assert mock_registry.register_tool.call_count == 4  # 2 tools x 2 registrations each
            
            # Check that tools were registered in both namespaces
            call_args = mock_registry.register_tool.call_args_list
            
            # Check tools are registered as both "tool" and "namespace.tool"
            tool_names = []
            for call in call_args:
                # Extract name parameter from the call
                args, kwargs = call
                # The name is the second positional argument 
                # or in kwargs with key 'name'
                if 'name' in kwargs:
                    tool_names.append(kwargs['name'])
                elif len(args) > 1:
                    tool_names.append(args[1])
            
            assert "echo" in tool_names
            assert "mcp.echo" in tool_names
            assert "calc" in tool_names
            assert "mcp.calc" in tool_names
    
    def test_register_with_invalid_tool(self, mock_registry, mock_stream_manager):
        """Test handling invalid tool definitions."""
        tools = [
            {"description": "No name"},  # Missing name
            {"name": "", "description": "Empty name"}  # Empty name
        ]
        mock_stream_manager.get_all_tools = Mock(return_value=tools)
        
        with patch('chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry', return_value=mock_registry):
            registered = register_mcp_tools(mock_stream_manager)
            
            assert len(registered) == 0
            assert mock_registry.register_tool.call_count == 0
    
    def test_empty_tools_registration(self, mock_registry):
        """Test registering with no tools."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_stream_manager.get_all_tools = Mock(return_value=[])
        
        with patch('chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry', return_value=mock_registry):
            registered = register_mcp_tools(mock_stream_manager)
            
            assert len(registered) == 0
            assert mock_registry.register_tool.call_count == 0
    
    def test_duplicate_tool_names(self, mock_registry):
        """Test registering tools with duplicate names."""
        mock_stream_manager = Mock(spec=StreamManager)
        tools = [
            {"name": "echo", "description": "First echo"},
            {"name": "echo", "description": "Second echo"}  # Duplicate
        ]
        mock_stream_manager.get_all_tools = Mock(return_value=tools)
        
        with patch('chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry', return_value=mock_registry):
            registered = register_mcp_tools(mock_stream_manager)
            
            # Should register both (last one overwrites)
            assert len(registered) == 2  # Count includes duplicates
            # Each tool is registered twice (once in mcp namespace, once in default namespace)
            # But due to duplicates, we expect 4 calls total (2 tools x 2 namespaces)
            assert mock_registry.register_tool.call_count == 4  # 2 tools x 2 namespaces