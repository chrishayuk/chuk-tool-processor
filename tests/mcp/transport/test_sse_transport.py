# tests/mcp/transport/test_sse_transport.py
"""
tests for SSETransport class.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch

from chuk_tool_processor.mcp.transport.sse_transport import SSETransport


class TestSSETransport:
    """Test SSETransport class with proper mocking."""
    
    @pytest.fixture
    def transport(self):
        """Create SSETransport instance."""
        return SSETransport("http://test.com", "api_key")
    
    @pytest.mark.asyncio
    async def test_initialize_with_chuk_mcp_available(self, transport):
        """Test SSE transport initialization when chuk-mcp is available."""
        # Mock successful SSE client initialization
        mock_context = AsyncMock()
        mock_streams = (Mock(), Mock())
        mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_context.__aexit__ = AsyncMock()
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_SSE_SUPPORT', True):
            with patch('chuk_tool_processor.mcp.transport.sse_transport.sse_client', return_value=mock_context):
                with patch('chuk_tool_processor.mcp.transport.sse_transport.send_ping', AsyncMock(return_value=True)):
                    result = await transport.initialize()
                    
                    assert result is True
                    assert transport._initialized is True
    
    @pytest.mark.asyncio
    async def test_initialize_without_chuk_mcp(self, transport):
        """Test SSE transport initialization when chuk-mcp is not available."""
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_SSE_SUPPORT', False):
            result = await transport.initialize()
            
            assert result is False
            assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self, transport):
        """Test SSE transport initialization with connection failure."""
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_SSE_SUPPORT', True):
            with patch('chuk_tool_processor.mcp.transport.sse_transport.sse_client', side_effect=Exception("Connection failed")):
                result = await transport.initialize()
                
                assert result is False
                assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test SSE ping when initialized."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.send_ping', AsyncMock(return_value=True)):
            result = await transport.send_ping()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_ping_not_initialized(self, transport):
        """Test SSE ping when not initialized."""
        assert transport._initialized is False
        
        result = await transport.send_ping()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_tools_success(self, transport):
        """Test SSE get tools when initialized."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        expected_tools = [{"name": "search"}, {"name": "research"}]
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.send_tools_list', 
                   AsyncMock(return_value={"tools": expected_tools})):
            tools = await transport.get_tools()
            assert tools == expected_tools
    
    @pytest.mark.asyncio
    async def test_get_tools_not_initialized(self, transport):
        """Test SSE get tools when not initialized."""
        assert transport._initialized is False
        
        tools = await transport.get_tools()
        assert tools == []
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test SSE call tool when initialized."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        response = {"result": {"content": [{"type": "text", "text": '{"answer": "success"}'}]}}
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("search", {"query": "test"})
            
            assert result["isError"] is False
            assert result["content"]["answer"] == "success"
    
    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test SSE call tool when not initialized."""
        assert transport._initialized is False
        
        result = await transport.call_tool("test", {})
        
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"
    
    @pytest.mark.asyncio
    async def test_call_tool_error_response(self, transport):
        """Test SSE call tool with error response."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        response = {"error": {"message": "Tool failed"}}
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.send_tools_call', 
                   AsyncMock(return_value=response)):
            result = await transport.call_tool("search", {})
            
            assert result["isError"] is True
            assert result["error"] == "Tool failed"
    
    @pytest.mark.asyncio
    async def test_close_success(self, transport):
        """Test SSE close when initialized."""
        # Mock successful initialization
        mock_context = AsyncMock()
        mock_context.__aexit__ = AsyncMock()
        
        transport._sse_context = mock_context
        transport._initialized = True
        
        await transport.close()
        
        # Verify the context manager was properly closed
        mock_context.__aexit__.assert_called_once()
        assert transport._sse_context is None
        assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_close_no_context(self, transport):
        """Test SSE close when no context exists."""
        transport._sse_context = None
        transport._initialized = False
        
        # Should not raise an error
        await transport.close()
        
        assert transport._sse_context is None
        assert transport._initialized is False
    
    @pytest.mark.asyncio
    async def test_list_resources_success(self, transport):
        """Test listing resources when initialized."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        expected_resources = {"resources": [{"name": "resource1"}]}
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_RESOURCES_PROMPTS', True):
            with patch('chuk_tool_processor.mcp.transport.sse_transport.send_resources_list', 
                       AsyncMock(return_value=expected_resources)):
                result = await transport.list_resources()
                assert result == expected_resources
    
    @pytest.mark.asyncio
    async def test_list_resources_not_available(self, transport):
        """Test listing resources when feature not available."""
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_RESOURCES_PROMPTS', False):
            result = await transport.list_resources()
            assert result == {}
    
    @pytest.mark.asyncio
    async def test_list_prompts_success(self, transport):
        """Test listing prompts when initialized."""
        # Mock successful initialization
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        expected_prompts = {"prompts": [{"name": "prompt1"}]}
        
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_RESOURCES_PROMPTS', True):
            with patch('chuk_tool_processor.mcp.transport.sse_transport.send_prompts_list',
                       AsyncMock(return_value=expected_prompts)):
                result = await transport.list_prompts()
                assert result == expected_prompts
    
    @pytest.mark.asyncio
    async def test_list_prompts_not_available(self, transport):
        """Test listing prompts when feature not available."""
        with patch('chuk_tool_processor.mcp.transport.sse_transport.HAS_RESOURCES_PROMPTS', False):
            result = await transport.list_prompts()
            assert result == {}
    
    def test_get_streams(self, transport):
        """Test getting streams for backward compatibility."""
        # Test when not initialized
        streams = transport.get_streams()
        assert streams == []
        
        # Test when initialized
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        streams = transport.get_streams()
        assert len(streams) == 1
        assert streams[0] == (transport._read_stream, transport._write_stream)
    
    def test_is_connected(self, transport):
        """Test connection status check."""
        # Test when not initialized
        assert transport.is_connected() is False
        
        # Test when initialized
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        transport._initialized = True
        
        assert transport.is_connected() is True
    
    def test_repr(self, transport):
        """Test string representation."""
        # Test when not initialized
        repr_str = repr(transport)
        assert "not initialized" in repr_str
        assert "http://test.com" in repr_str
        
        # Test when initialized
        transport._initialized = True
        repr_str = repr(transport)
        assert "initialized" in repr_str