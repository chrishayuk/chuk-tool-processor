# tests/mcp/transport/test_stdio_transport.py
"""
tests for StdioTransport class.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from contextlib import AsyncExitStack

from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport


class TestStdioTransport:
    """Test StdioTransport class with proper mocking."""
    
    @pytest.fixture
    def mock_stdio_client(self):
        """Mock stdio client."""
        mock = Mock()
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
        mock_streams = (Mock(), Mock())
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock()
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.stdio_client', return_value=mock_context):
            with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_initialize', AsyncMock(return_value=True)):
                result = await transport.initialize()
                
                assert result is True
                assert transport._streams is not None
                assert transport._initialized is True
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self, transport):
        """Test initialization failure."""
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.stdio_client', side_effect=Exception("Failed")):
            result = await transport.initialize()
            
            assert result is False
            assert transport._streams is None
            assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_close(self, transport):
        """Test closing transport based on actual implementation."""
        # Mock a context that was created during initialization
        mock_context = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        
        transport._context = mock_context
        transport._initialized = True
        
        await transport.close()
        
        # Verify the context manager was properly closed
        mock_context.__aexit__.assert_called_once()
        assert transport._context is None
        assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_close_no_context(self, transport):
        """Test closing transport when no context exists."""
        transport._context = None
        transport._initialized = False
        
        # Should not raise an error
        await transport.close()
        
        assert transport._context is None
        assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test sending ping when initialized."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_ping', AsyncMock(return_value=True)):
            result = await transport.send_ping()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_ping_not_initialized(self, transport):
        """Test sending ping when not initialized."""
        # Don't initialize the transport
        assert transport._initialized is False
        
        result = await transport.send_ping()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_tools_success(self, transport):
        """Test getting tools when initialized."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        expected_tools = [{"name": "echo"}, {"name": "calc"}]
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_list', 
                   AsyncMock(return_value={"tools": expected_tools})):
            tools = await transport.get_tools()
            assert tools == expected_tools
    
    @pytest.mark.asyncio
    async def test_get_tools_not_initialized(self, transport):
        """Test getting tools when not initialized."""
        assert transport._initialized is False
        
        tools = await transport.get_tools()
        assert tools == []
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test successful tool call."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        response = {"result": {"content": [{"type": "text", "text": "42"}]}}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("calc", {"op": "add", "a": 1, "b": 2})
            
            assert result["isError"] is False
            assert result["content"] == "42"
    
    @pytest.mark.asyncio
    async def test_call_tool_error(self, transport):
        """Test tool call with error."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        response = {"error": {"message": "Tool failed"}}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("calc", {})
            
            assert result["isError"] is True
            assert result["error"] == "Tool failed"
    
    @pytest.mark.asyncio
    async def test_call_tool_echo_format(self, transport):
        """Test tool call with echo server format."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        response = {
            "result": {
                "content": [{"type": "text", "text": '{"status": "ok"}'}]
            }
        }
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("echo", {"message": "test"})
            
            assert result["isError"] is False
            assert result["content"] == {"status": "ok"}
    
    @pytest.mark.asyncio
    async def test_call_tool_echo_format_invalid_json(self, transport):
        """Test tool call with echo server format but invalid JSON."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        response = {
            "result": {
                "content": [{"type": "text", "text": 'invalid json'}]
            }
        }
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("echo", {"message": "test"})
            
            assert result["isError"] is False
            assert result["content"] == 'invalid json'  # Falls back to raw text
    
    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test calling tool without initialization."""
        assert transport._initialized is False
        
        result = await transport.call_tool("test", {})
        
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"
    
    @pytest.mark.asyncio
    async def test_call_tool_exception_handling(self, transport):
        """Test tool call with exception during execution."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call', 
                   AsyncMock(side_effect=Exception("Connection failed"))):
            result = await transport.call_tool("test", {})
            
            assert result["isError"] is True
            assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_list_resources(self, transport):
        """Test listing resources."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock())
        transport._initialized = True
        
        expected_resources = {"resources": [{"name": "resource1"}]}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_resources_list', 
                   AsyncMock(return_value=expected_resources)):
            result = await transport.list_resources()
            assert result == expected_resources

    @pytest.mark.asyncio
    async def test_list_prompts(self, transport):
        """Test listing prompts."""
        # Mock successful initialization
        transport._streams = (Mock(), Mock()) 
        transport._initialized = True
        
        expected_prompts = {"prompts": [{"name": "prompt1"}]}
        
        with patch('chuk_tool_processor.mcp.transport.stdio_transport.send_prompts_list',
                   AsyncMock(return_value=expected_prompts)):
            result = await transport.list_prompts()
            assert result == expected_prompts