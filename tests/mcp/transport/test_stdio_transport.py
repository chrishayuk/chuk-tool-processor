# tests/mcp/transport/test_stdio_transport.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from contextlib import AsyncExitStack

from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport


class TestStdioTransport:
    """Test StdioTransport class."""
    
    @pytest.fixture
    def mock_stdio_client(self):
        """Mock stdio client."""
        mock = Mock()
        # Mock async context manager properly
        async def async_context_manager():
            return Mock(), Mock()
        
        mock.return_value.__aenter__ = AsyncMock(return_value=(Mock(), Mock()))
        mock.return_value.__aexit__ = AsyncMock()
        return mock
    
    @pytest.fixture
    def transport(self):
        """Create StdioTransport instance."""
        return StdioTransport({"command": "test", "args": []})
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, transport, mock_stdio_client):
        """Test successful initialization."""
        # Create a properly mocked context
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(Mock(), Mock()))
        mock_context.__aexit__ = AsyncMock()
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.stdio_client', return_value=mock_context):
            with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_initialize', AsyncMock(return_value=True)):
                result = await transport.initialize()
                
                assert result is True
                assert transport.read_stream is not None
                assert transport.write_stream is not None
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self, transport):
        """Test initialization failure."""
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.stdio_client', side_effect=Exception("Failed")):
            result = await transport.initialize()
            
            assert result is False
            assert transport.read_stream is None
            assert transport.write_stream is None
    
    @pytest.mark.asyncio
    async def test_close(self, transport):
        """Test closing transport."""
        # Setup mock context stack
        mock_context = AsyncMock()
        transport._context_stack = mock_context
        
        await transport.close()
        
        mock_context.__aexit__.assert_called_once()
        assert transport._context_stack is None
    
    @pytest.mark.asyncio
    async def test_send_ping(self, transport):
        """Test sending ping."""
        transport.read_stream = Mock()
        transport.write_stream = Mock()
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_ping', AsyncMock(return_value=True)):
            result = await transport.send_ping()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_get_tools(self, transport):
        """Test getting tools."""
        transport.read_stream = Mock()
        transport.write_stream = Mock()
        
        expected_tools = [{"name": "echo"}, {"name": "calc"}]
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_list', 
                   AsyncMock(return_value={"tools": expected_tools})):
            tools = await transport.get_tools()
            assert tools == expected_tools
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test successful tool call."""
        transport.read_stream = Mock()
        transport.write_stream = Mock()
        
        response = {"result": {"value": 42}}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("calc", {"op": "add", "a": 1, "b": 2})
            
            assert result["isError"] is False
            assert result["content"] == {"value": 42}
    
    @pytest.mark.asyncio
    async def test_call_tool_error(self, transport):
        """Test tool call with error."""
        transport.read_stream = Mock()
        transport.write_stream = Mock()
        
        response = {"error": {"message": "Tool failed"}}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("calc", {})
            
            assert result["isError"] is True
            assert result["error"] == "Tool failed"
    
    @pytest.mark.asyncio
    async def test_call_tool_echo_format(self, transport):
        """Test tool call with echo server format."""
        transport.read_stream = Mock()
        transport.write_stream = Mock()
        
        response = {
            "content": [{"type": "text", "text": '{"status": "ok"}'}]
        }
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("echo", {"message": "test"})
            
            assert result["isError"] is False
            assert result["content"] == {"status": "ok"}
    
    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test calling tool without initialization."""
        result = await transport.call_tool("test", {})
        
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"