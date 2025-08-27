# tests/mcp/transport/test_sse_transport.py - FIXED ASYNC CONTEXT HANDLING
"""
Tests for SSETransport class with updated consistent interface.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.mcp.transport.sse_transport import SSETransport


class TestSSETransport:
    """Test SSETransport class with proper mocking and consistent interface."""

    @pytest.fixture
    def transport(self):
        """Create SSETransport instance with consistent parameters."""
        return SSETransport(
            "http://test.com", api_key="api_key", connection_timeout=30.0, default_timeout=30.0, enable_metrics=True
        )

    @pytest.fixture
    def transport_no_metrics(self):
        """Create SSETransport instance with metrics disabled."""
        return SSETransport("http://test.com", api_key="api_key", enable_metrics=False)

    @pytest.mark.asyncio
    async def test_initialize_success(self, transport):
        """Test successful SSE transport initialization with metrics tracking."""
        # Create proper async mock clients
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        # Properly formatted SSE lines
        async def mock_aiter_lines():
            yield "data: /messages/session?session_id=test-session-123"
            yield 'data: {"jsonrpc": "2.0", "id": "init-id", "result": {"protocolVersion": "2024-11-05"}}'
            yield "data: ping"

        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 200
        mock_sse_response.aiter_lines = mock_aiter_lines

        # CRITICAL FIX: Create proper async context manager that returns immediately
        class AsyncStreamContext:
            def __init__(self, response):
                self.response = response

            async def __aenter__(self):
                return self.response

            async def __aexit__(self, exc_type, exc, tb):
                pass

        # CRITICAL FIX: Mock stream_client.stream to return the context directly, not a coroutine
        # The SSE transport expects stream() to return a context manager immediately
        async_context = AsyncStreamContext(mock_sse_response)
        mock_stream_client.stream = Mock(return_value=async_context)  # Use Mock, not AsyncMock

        mock_post_response = AsyncMock()
        mock_post_response.status_code = 202
        mock_send_client.post.return_value = mock_post_response

        with patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]):

            async def mock_send_request(method, params, timeout=None):
                if method == "initialize":
                    return {"jsonrpc": "2.0", "id": "init-id", "result": {"protocolVersion": "2024-11-05"}}
                return {"result": {}}

            with patch.object(transport, "_send_request", side_effect=mock_send_request):
                with patch.object(transport, "_send_notification", AsyncMock()):
                    result = await transport.initialize()
                    # Give the background task time to extract session
                    await asyncio.sleep(0.2)

                    assert result is True
                    assert transport._initialized is True
                    assert transport.session_id == "test-session-123"
                    assert transport.message_url == "http://test.com/messages/session?session_id=test-session-123"

                    # Check metrics were updated
                    metrics = transport.get_metrics()
                    assert metrics["initialization_time"] > 0
                    assert metrics["session_discoveries"] == 1

    @pytest.mark.asyncio
    async def test_initialize_sse_connection_failure(self, transport):
        """Test SSE transport initialization with connection failure."""
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 500

        class AsyncStreamContext:
            def __init__(self, response):
                self.response = response

            async def __aenter__(self):
                return self.response

            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_stream_client.stream.return_value = AsyncStreamContext(mock_sse_response)

        with patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]):
            result = await transport.initialize()
            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_no_session_info(self, transport):
        """Test SSE transport initialization when no session info received."""
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        async def mock_aiter_lines():
            yield "data: ping"
            yield "data: some other data"

        mock_sse_response = AsyncMock()
        mock_sse_response.status_code = 200
        mock_sse_response.aiter_lines = mock_aiter_lines

        class AsyncStreamContext:
            def __init__(self, response):
                self.response = response

            async def __aenter__(self):
                return self.response

            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_stream_client.stream.return_value = AsyncStreamContext(mock_sse_response)

        with patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]):
            result = await transport.initialize()
            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test SSE ping when initialized with metrics tracking."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        with patch.object(transport, "_send_request", AsyncMock(return_value={"result": {"tools": []}})):
            result = await transport.send_ping()
            assert result is True

            # Check ping metrics were updated
            metrics = transport.get_metrics()
            assert metrics["last_ping_time"] > 0

    @pytest.mark.asyncio
    async def test_send_ping_not_initialized(self, transport):
        """Test SSE ping when not initialized."""
        assert transport._initialized is False
        result = await transport.send_ping()
        assert result is False

    def test_is_connected(self, transport):
        """Test connection status check (new consistent method)."""
        # not initialized
        assert transport.is_connected() is False
        # initialized but no session
        transport._initialized = True
        assert transport.is_connected() is False
        # fully connected
        transport.session_id = "test-session"
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_get_tools_success(self, transport):
        """Test SSE get tools when initialized with performance tracking."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        expected_tools = [{"name": "search"}, {"name": "research"}]
        response = {"result": {"tools": expected_tools}}

        with patch.object(transport, "_send_request", AsyncMock(return_value=response)):
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

        with patch.object(transport, "_send_request", AsyncMock(return_value=response)):
            tools = await transport.get_tools()
            assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test SSE call tool when initialized with metrics tracking."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"result": {"content": [{"type": "text", "text": '{"answer": "success"}'}]}}

        with patch.object(transport, "_send_request", AsyncMock(return_value=response)):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is False
            assert result["content"]["answer"] == "success"

            # Check metrics were updated
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["successful_calls"] == 1
            assert metrics["avg_response_time"] > 0

    @pytest.mark.asyncio
    async def test_call_tool_with_timeout(self, transport):
        """Test SSE call tool with custom timeout parameter."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"result": {"content": [{"type": "text", "text": "success"}]}}

        with patch.object(transport, "_send_request", AsyncMock(return_value=response)) as mock_send:
            result = await transport.call_tool("search", {"query": "test"}, timeout=15.0)
            assert result["isError"] is False

            # Verify timeout was passed to _send_request
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["timeout"] == 15.0

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test SSE call tool when not initialized."""
        assert transport._initialized is False
        result = await transport.call_tool("test", {})
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self, transport):
        """Test SSE call tool with error response and metrics tracking."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        response = {"error": {"message": "Tool failed"}}

        with patch.object(transport, "_send_request", AsyncMock(return_value=response)):
            result = await transport.call_tool("search", {})
            assert result["isError"] is True
            assert result["error"] == "Tool failed"

            # Check failure metrics were updated
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self, transport):
        """Test SSE call tool with timeout and metrics tracking."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        with patch.object(transport, "_send_request", AsyncMock(side_effect=asyncio.TimeoutError)):
            result = await transport.call_tool("search", {}, timeout=1.0)
            assert result["isError"] is True
            assert "timed out" in result["error"].lower()

            # Check timeout failure metrics
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_metrics_functionality(self, transport):
        """Test metrics get and reset functionality."""
        # Initial metrics
        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["successful_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["avg_response_time"] == 0.0

        # Manually increment total_calls first to prevent division by zero
        transport._metrics["total_calls"] = 1
        transport._update_metrics(0.5, True)  # Success

        transport._metrics["total_calls"] = 2  # Increment again
        transport._update_metrics(1.0, False)  # Failure

        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 2
        assert metrics["successful_calls"] == 1
        assert metrics["failed_calls"] == 1
        assert metrics["total_time"] == 1.5
        assert metrics["avg_response_time"] == 0.75

        # Test reset
        transport.reset_metrics()
        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["successful_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["avg_response_time"] == 0.0

    @pytest.mark.asyncio
    async def test_metrics_disabled(self, transport_no_metrics):
        """Test transport behavior with metrics disabled."""
        transport_no_metrics._initialized = True
        transport_no_metrics.message_url = "http://test.com/messages/test"

        # Metrics should still be available but not actively updated during operations
        assert transport_no_metrics.enable_metrics is False
        metrics = transport_no_metrics.get_metrics()
        assert isinstance(metrics, dict)

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
        """Test processing SSE stream with metrics tracking."""
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
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert transport.session_id == "test-123"
        assert transport.message_url == "http://test.com/messages/session?session_id=test-123"
        assert future.done()
        assert future.result()["result"]["test"] is True

    @pytest.mark.asyncio
    async def test_close_success(self, transport):
        """Test SSE close when initialized with metrics logging."""
        transport._initialized = True
        # Add some metrics to test logging
        transport._metrics["total_calls"] = 5
        transport._metrics["successful_calls"] = 4
        transport._metrics["failed_calls"] = 1

        transport.sse_task = asyncio.create_task(asyncio.sleep(10))
        transport.sse_stream_context = AsyncMock()
        transport.sse_stream_context.__aexit__ = AsyncMock(return_value=None)

        # Create mock clients and save references before calling close
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        transport.stream_client = mock_stream_client
        transport.send_client = mock_send_client

        await transport.close()

        assert transport._initialized is False
        assert transport.session_id is None
        assert transport.message_url is None
        assert transport.pending_requests == {}
        # These should work now since we saved references
        mock_stream_client.aclose.assert_called_once()
        mock_send_client.aclose.assert_called_once()

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

        with patch.object(transport, "_send_request", AsyncMock(return_value={"result": expected_resources})):
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

        with patch.object(transport, "_send_request", AsyncMock(return_value={"result": expected_prompts})):
            result = await transport.list_prompts()
            assert result == expected_prompts

    @pytest.mark.asyncio
    async def test_list_prompts_not_initialized(self, transport):
        """Test listing prompts when not initialized."""
        transport._initialized = False
        result = await transport.list_prompts()
        assert result == {}

    def test_get_streams(self, transport):
        """Test getting streams returns empty list (SSE doesn't expose streams)."""
        assert transport.get_streams() == []

    @pytest.mark.asyncio
    async def test_context_manager_success(self, transport):
        """Test using transport as context manager."""
        with patch.object(transport, "initialize", AsyncMock(return_value=True)):
            with patch.object(transport, "close", AsyncMock()):
                async with transport as t:
                    assert t is transport
                transport.initialize.assert_called_once()
                transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_init_failure(self, transport):
        """Test context manager when initialization fails."""
        with patch.object(transport, "initialize", AsyncMock(return_value=False)):
            with pytest.raises(RuntimeError, match="Failed to initialize SSETransport"):
                async with transport:
                    pass

    def test_repr_consistent_format(self, transport):
        """Test string representation follows consistent format."""
        # Not initialized
        repr_str = repr(transport)
        assert "SSETransport" in repr_str
        assert "status=not initialized" in repr_str
        assert "url=http://test.com" in repr_str

        # Initialized with metrics
        transport._initialized = True
        transport.session_id = "test-123"
        transport._metrics["total_calls"] = 10
        transport._metrics["successful_calls"] = 8

        repr_str = repr(transport)
        assert "status=initialized" in repr_str
        assert "calls: 10" in repr_str
        assert "success: 80.0%" in repr_str

    def test_get_headers(self, transport):
        """Test header generation with consistent patterns."""
        # With API key
        headers = transport._get_headers()
        assert headers["Authorization"] == "Bearer api_key"

        # With custom headers
        transport_custom = SSETransport(
            "http://test.com", headers={"Custom-Header": "value", "Authorization": "old-auth"}
        )
        headers = transport_custom._get_headers()
        assert headers["Custom-Header"] == "value"
        # API key should not override since none provided
        assert headers.get("Authorization") == "old-auth"

        # Without API key
        transport_no_key = SSETransport("http://test.com")
        headers = transport_no_key._get_headers()
        assert "Authorization" not in headers

    def test_construct_sse_url(self, transport):
        """Test SSE URL construction logic."""
        # URL without /sse
        url = transport._construct_sse_url("http://test.com")
        assert url == "http://test.com/sse"

        # URL already with /sse
        url = transport._construct_sse_url("http://test.com/sse")
        assert url == "http://test.com/sse"

        # URL with trailing slash
        url = transport._construct_sse_url("http://test.com/")
        assert url == "http://test.com/sse"

    @pytest.mark.asyncio
    async def test_response_normalization(self, transport):
        """Test that response normalization uses base class methods."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        # Test various response formats
        test_cases = [
            # Standard MCP content format
            {
                "input": {"result": {"content": [{"type": "text", "text": '{"result": "success"}'}]}},
                "expected": {"isError": False, "content": {"result": "success"}},
            },
            # Plain text content
            {
                "input": {"result": {"content": [{"type": "text", "text": "plain text"}]}},
                "expected": {"isError": False, "content": "plain text"},
            },
            # Direct result
            {"input": {"result": {"value": 42}}, "expected": {"isError": False, "content": {"value": 42}}},
        ]

        for case in test_cases:
            with patch.object(transport, "_send_request", AsyncMock(return_value=case["input"])):
                result = await transport.call_tool("test", {})
                assert result == case["expected"]
