# tests/mcp/transport/test_sse_transport.py
"""
Tests for SSETransport class.
"""
import asyncio
import json
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
    async def test_initialize_success(self, transport):
        """Test successful SSE transport initialization."""
        # Use a plain Mock for stream_client so .stream() returns our DummyContext directly
        mock_stream_client = Mock()
        mock_send_client = AsyncMock()

        # Properly formatted SSE lines
        async def mock_aiter_lines():
            yield "data: /messages/session?session_id=test-session-123"
            yield "data: {\"jsonrpc\": \"2.0\", \"id\": \"init-id\", \"result\": {\"protocolVersion\": \"2024-11-05\"}}"
            yield "data: ping"

        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 200
        mock_sse_response.aiter_lines = mock_aiter_lines

        class DummyContext:
            async def __aenter__(self):
                return mock_sse_response
            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_stream_client.stream.return_value = DummyContext()

        mock_post_response = AsyncMock()
        mock_post_response.status_code = 202
        mock_send_client.post.return_value = mock_post_response

        with patch('httpx.AsyncClient', side_effect=[mock_stream_client, mock_send_client]):
            async def mock_send_request(method, params, timeout=None):
                if method == "initialize":
                    return {"jsonrpc": "2.0", "id": "init-id", "result": {"protocolVersion": "2024-11-05"}}
                return {"result": {}}

            with patch.object(transport, '_send_request', side_effect=mock_send_request):
                with patch.object(transport, '_send_notification', AsyncMock()):
                    result = await transport.initialize()
                    # Give the background task time to extract session
                    await asyncio.sleep(0.2)

                    assert result is True
                    assert transport._initialized is True
                    assert transport.session_id == "test-session-123"
                    assert transport.message_url == "http://test.com/messages/session?session_id=test-session-123"

    @pytest.mark.asyncio
    async def test_initialize_sse_connection_failure(self, transport):
        """Test SSE transport initialization with connection failure."""
        mock_stream_client = Mock()
        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 500

        class DummyContext:
            async def __aenter__(self):
                return mock_sse_response
            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_stream_client.stream.return_value = DummyContext()

        with patch('httpx.AsyncClient', return_value=mock_stream_client):
            result = await transport.initialize()
            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_no_session_info(self, transport):
        """Test SSE transport initialization when no session info received."""
        mock_stream_client = Mock()

        async def mock_aiter_lines():
            yield "data: ping"
            yield "data: some other data"

        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 200
        mock_sse_response.aiter_lines = mock_aiter_lines

        class DummyContext:
            async def __aenter__(self):
                return mock_sse_response
            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_stream_client.stream.return_value = DummyContext()

        with patch('httpx.AsyncClient', return_value=mock_stream_client):
            result = await transport.initialize()
            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test SSE ping when initialized."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        with patch.object(transport, '_send_request', AsyncMock(return_value={"result": {"tools": []}})):
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
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        expected_tools = [{"name": "search"}, {"name": "research"}]
        response = {"result": {"tools": expected_tools}}

        with patch.object(transport, '_send_request', AsyncMock(return_value=response)):
            tools = await transport.get_tools()
            assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_tools_not_initialized(self, transport):
        """Test SSE get tools when not initialized."""
        assert transport._initialized is False
        tools = await transport.get_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_get_tools_error_response(self, transport):
        """Test SSE get tools with error response."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"error": {"message": "Failed to get tools"}}

        with patch.object(transport, '_send_request', AsyncMock(return_value=response)):
            tools = await transport.get_tools()
            assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test SSE call tool when initialized."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"result": {"content": [{"type": "text", "text": '{"answer": "success"}'}]}}

        with patch.object(transport, '_send_request', AsyncMock(return_value=response)):
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
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"error": {"message": "Tool failed"}}

        with patch.object(transport, '_send_request', AsyncMock(return_value=response)):
            result = await transport.call_tool("search", {})
            assert result["isError"] is True
            assert result["error"] == "Tool failed"

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self, transport):
        """Test SSE call tool with timeout."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        with patch.object(transport, '_send_request', AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await transport.call_tool("search", {}, timeout=1.0)
            assert result["isError"] is True
            assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_send_request_success(self, transport):
        """Test sending request and receiving async response."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 202
        transport.send_client.post.return_value = mock_response

        async def simulate_response():
            await asyncio.sleep(0.1)
            req_id = next(iter(transport.pending_requests))
            transport.pending_requests[req_id].set_result({"jsonrpc": "2.0", "id": req_id, "result": {"success": True}})

        asyncio.create_task(simulate_response())

        result = await transport._send_request("test_method", {"param": "value"})
        assert "result" in result
        assert result["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_send_request_immediate_response(self, transport):
        """Test sending request with immediate response."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"jsonrpc": "2.0", "id": "123", "result": {"immediate": True}})
        transport.send_client.post.return_value = mock_response

        result = await transport._send_request("test_method", {})
        assert result["result"]["immediate"] is True

    @pytest.mark.asyncio
    async def test_send_notification(self, transport):
        """Test sending notification."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()
        transport.send_client.post = AsyncMock()

        await transport._send_notification("test_notification", {"data": "value"})
        transport.send_client.post.assert_called_once()
        _, kwargs = transport.send_client.post.call_args
        assert kwargs["json"]["method"] == "test_notification"
        assert "id" not in kwargs["json"]

    @pytest.mark.asyncio
    async def test_process_sse_stream(self, transport):
        """Test processing SSE stream."""
        mock_response = AsyncMock()

        async def mock_lines():
            yield "data: /messages/session?session_id=test-123"
            yield "data: "
            yield "data: ping"
            yield 'data: {"jsonrpc": "2.0", "id": "req-1", "result": {"test": true}}'
            yield "data: invalid json {"

        mock_response.aiter_lines = mock_lines
        transport.sse_response = mock_response

        future = asyncio.get_event_loop().create_future()
        transport.pending_requests["req-1"] = future

        task = asyncio.create_task(transport._process_sse_stream())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert transport.session_id == "test-123"
        assert transport.message_url == "http://test.com/messages/session?session_id=test-123"
        assert future.done()
        assert future.result()["result"]["test"] is True

    @pytest.mark.asyncio
    async def test_close_success(self, transport):
        """Test SSE close when initialized."""
        transport._initialized = True
        transport.sse_task = asyncio.create_task(asyncio.sleep(10))
        transport.sse_stream_context = AsyncMock()
        transport.sse_stream_context.__aexit__ = AsyncMock(return_value=None)
        transport.stream_client = AsyncMock()
        transport.stream_client.aclose = AsyncMock(return_value=None)
        transport.send_client = AsyncMock()
        transport.send_client.aclose = AsyncMock(return_value=None)

        await transport.close()

        assert transport._initialized is False
        assert transport.session_id is None
        assert transport.message_url is None
        assert transport.pending_requests == {}
        transport.stream_client.aclose.assert_called_once()
        transport.send_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_context(self, transport):
        """Test SSE close when no context exists."""
        transport._initialized = False
        await transport.close()
        assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_list_resources_success(self, transport):
        """Test listing resources when initialized."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        expected_resources = {"resources": [{"name": "resource1"}]}

        with patch.object(transport, '_send_request', AsyncMock(return_value={"result": expected_resources})):
            result = await transport.list_resources()
            assert result == expected_resources

    @pytest.mark.asyncio
    async def test_list_resources_not_initialized(self, transport):
        """Test listing resources when not initialized."""
        transport._initialized = False
        result = await transport.list_resources()
        assert result == {}

    @pytest.mark.asyncio
    async def test_list_prompts_success(self, transport):
        """Test listing prompts when initialized."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        expected_prompts = {"prompts": [{"name": "prompt1"}]}

        with patch.object(transport, '_send_request', AsyncMock(return_value={"result": expected_prompts})):
            result = await transport.list_prompts()
            assert result == expected_prompts

    @pytest.mark.asyncio
    async def test_list_prompts_not_initialized(self, transport):
        """Test listing prompts when not initialized."""
        transport._initialized = False
        result = await transport.list_prompts()
        assert result == {}

    def test_get_streams(self, transport):
        """Test getting streams returns empty list."""
        assert transport.get_streams() == []

    def test_is_connected(self, transport):
        """Test connection status check."""
        # not initialized
        assert transport.is_connected() is False
        # initialized but no session
        transport._initialized = True
        assert transport.is_connected() is False
        # fully connected
        transport.session_id = "test-session"
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_context_manager_success(self, transport):
        """Test using transport as context manager."""
        with patch.object(transport, 'initialize', AsyncMock(return_value=True)):
            with patch.object(transport, 'close', AsyncMock()):
                async with transport as t:
                    assert t is transport
                transport.initialize.assert_called_once()
                transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_init_failure(self, transport):
        """Test context manager when initialization fails."""
        with patch.object(transport, 'initialize', AsyncMock(return_value=False)):
            with pytest.raises(RuntimeError, match="Failed to initialize SSE transport"):
                async with transport:
                    pass

    def test_repr(self, transport):
        """Test string representation."""
        repr_str = repr(transport)
        assert "not initialized" in repr_str
        assert "http://test.com" in repr_str
        assert "session=None" in repr_str

        transport._initialized = True
        transport.session_id = "test-123"
        repr_str = repr(transport)
        assert "initialized" in repr_str
        assert "session=test-123" in repr_str

    def test_get_headers(self, transport):
        """Test header generation."""
        # With API key
        headers = transport._get_headers()
        assert headers["Authorization"] == "Bearer api_key"
        # Without API key
        transport_no_key = SSETransport("http://test.com")
        headers = transport_no_key._get_headers()
        assert "Authorization" not in headers
