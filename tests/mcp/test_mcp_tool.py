# tests/mcp/test_mcp_tool.py
import pytest
from unittest.mock import Mock, AsyncMock

from chuk_tool_processor.mcp.mcp_tool import MCPTool
from chuk_tool_processor.mcp.stream_manager import StreamManager


class TestMCPTool:
    """Test MCPTool class."""
    
    @pytest.fixture
    def mock_stream_manager(self):
        """Mock StreamManager instance."""
        mock = Mock(spec=StreamManager)
        mock.call_tool = AsyncMock()
        return mock
    
    @pytest.fixture
    def mcp_tool(self, mock_stream_manager):
        """Create MCPTool instance."""
        return MCPTool("echo", mock_stream_manager)
    
    @pytest.mark.asyncio
    async def test_execute_success(self, mcp_tool, mock_stream_manager):
        """Test successful tool execution."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Hello World"
        }
        
        # Execute
        result = await mcp_tool.execute(message="Hello")
        
        # Verify
        assert result == "Hello World"
        mock_stream_manager.call_tool.assert_called_once_with(
            tool_name="echo",
            arguments={"message": "Hello"}
        )
    
    @pytest.mark.asyncio
    async def test_execute_error(self, mcp_tool, mock_stream_manager):
        """Test tool execution with error."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": True,
            "error": "Connection failed"
        }
        
        # Execute and verify error
        with pytest.raises(RuntimeError, match="Connection failed"):
            await mcp_tool.execute(message="Hello")
    
    @pytest.mark.asyncio
    async def test_execute_unknown_error(self, mcp_tool, mock_stream_manager):
        """Test tool execution with unknown error."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": True
        }
        
        # Execute and verify default error message
        with pytest.raises(RuntimeError, match="Unknown error"):
            await mcp_tool.execute(message="Hello")
    
    @pytest.mark.asyncio
    async def test_execute_transport_error(self, mcp_tool, mock_stream_manager):
        """Test tool call with transport error."""
        # Simulate transport error
        mock_stream_manager.call_tool.side_effect = Exception("Transport error")
        
        # Should catch and reraise as RuntimeError
        with pytest.raises(Exception, match="Transport error"):
            await mcp_tool.execute(message="test")