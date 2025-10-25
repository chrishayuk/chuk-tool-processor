# tests/mcp/transport/test_sse_transport.py - FIXED ASYNC CONTEXT HANDLING
"""
Tests for SSETransport class with updated consistent interface.
"""

import asyncio
import contextlib
import time
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

            with (
                patch.object(transport, "_send_request", side_effect=mock_send_request),
                patch.object(transport, "_send_notification", AsyncMock()),
            ):
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
            assert metrics["last_ping_time"] >= 0  # May be 0 in mocked tests

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
            assert metrics["avg_response_time"] >= 0  # May be 0 in mocked tests

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
        transport._metrics.total_calls = 1
        transport._update_metrics(0.5, True)  # Success

        transport._metrics.total_calls = 2  # Increment again
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
        transport._metrics.total_calls = 5
        transport._metrics.successful_calls = 4
        transport._metrics.failed_calls = 1

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
        with (
            patch.object(transport, "initialize", AsyncMock(return_value=True)),
            patch.object(transport, "close", AsyncMock()),
        ):
            async with transport as t:
                assert t is transport
            transport.initialize.assert_called_once()
            transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_init_failure(self, transport):
        """Test context manager when initialization fails."""
        with (
            patch.object(transport, "initialize", AsyncMock(return_value=False)),
            pytest.raises(RuntimeError, match="Failed to initialize SSETransport"),
        ):
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
        transport._metrics.total_calls = 10
        transport._metrics.successful_calls = 8

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

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, transport):
        """Test initialization when already initialized."""
        transport._initialized = True
        result = await transport.initialize()
        assert result is True

    @pytest.mark.asyncio
    async def test_initialize_gateway_connectivity_fails(self, transport):
        """Test initialization when gateway connectivity test fails."""
        with patch.object(transport, "_test_gateway_connectivity", AsyncMock(return_value=False)):
            result = await transport.initialize()
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_sse_status_not_200(self, transport):
        """Test initialization when SSE connection returns non-200 status."""
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

        async_context = AsyncStreamContext(mock_sse_response)
        mock_stream_client.stream = Mock(return_value=async_context)

        with (
            patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]),
            patch.object(transport, "_test_gateway_connectivity", AsyncMock(return_value=True)),
        ):
            result = await transport.initialize()
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_sse_task_dies(self, transport):
        """Test initialization when SSE task dies during session discovery."""
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        async def mock_aiter_lines():
            # Don't yield session URL, but die
            if False:
                yield

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

        async_context = AsyncStreamContext(mock_sse_response)
        mock_stream_client.stream = Mock(return_value=async_context)

        with (
            patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]),
            patch.object(transport, "_test_gateway_connectivity", AsyncMock(return_value=True)),
            patch.object(
                transport,
                "_process_sse_stream",
                AsyncMock(side_effect=Exception("SSE died")),
            ),
        ):
            result = await transport.initialize()
            await asyncio.sleep(0.2)  # Let task die
            assert result is False

    @pytest.mark.asyncio
    async def test_initialize_init_response_has_error(self, transport):
        """Test initialization when init response contains error."""
        mock_stream_client = AsyncMock()
        mock_send_client = AsyncMock()
        mock_stream_client.aclose = AsyncMock()
        mock_send_client.aclose = AsyncMock()

        async def mock_aiter_lines():
            yield "data: /messages/session?session_id=test-session"

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

        async_context = AsyncStreamContext(mock_sse_response)
        mock_stream_client.stream = Mock(return_value=async_context)

        with (
            patch("httpx.AsyncClient", side_effect=[mock_stream_client, mock_send_client]),
            patch.object(
                transport,
                "_send_request",
                AsyncMock(return_value={"error": {"message": "Init failed"}}),
            ),
            patch.object(transport, "_test_gateway_connectivity", AsyncMock(return_value=True)),
        ):
            result = await transport.initialize()
            await asyncio.sleep(0.2)
            assert result is False

    @pytest.mark.asyncio
    async def test_send_request_with_valid_timeout_param(self, transport):
        """Test send_request accepts timeout parameter."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        mock_send_client = AsyncMock()
        mock_post_response = AsyncMock()
        mock_post_response.status_code = 202
        mock_send_client.post.return_value = mock_post_response
        transport.send_client = mock_send_client

        # Test that timeout parameter doesn't cause issues
        with pytest.raises(asyncio.TimeoutError):
            await transport._send_request("test_method", {}, timeout=0.01)

    @pytest.mark.asyncio
    async def test_send_request_timeout(self, transport):
        """Test send_request with timeout."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        mock_send_client = AsyncMock()
        mock_post_response = AsyncMock()
        mock_post_response.status_code = 202
        mock_send_client.post.return_value = mock_post_response
        transport.send_client = mock_send_client

        # Don't add response to pending_responses, so it times out
        with pytest.raises(asyncio.TimeoutError):
            await transport._send_request("test_method", {}, timeout=0.1)

    @pytest.mark.asyncio
    async def test_send_request_http_error(self, transport):
        """Test send_request with HTTP error."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        mock_send_client = AsyncMock()
        mock_send_client.post.side_effect = Exception("HTTP Error")
        transport.send_client = mock_send_client

        with pytest.raises(Exception, match="HTTP Error"):
            await transport._send_request("test_method", {})

    @pytest.mark.asyncio
    async def test_close_with_metrics_logging(self, transport):
        """Test close with metrics logging."""
        transport._initialized = True
        transport._metrics.total_calls = 10
        transport._metrics.successful_calls = 8
        transport.stream_client = AsyncMock()
        transport.send_client = AsyncMock()
        transport.sse_task = None

        await transport.close()
        assert transport._initialized is False

    def test_url_normalization(self, transport):
        """Test URL normalization in constructor."""
        # Test with trailing slash
        t1 = SSETransport("http://test.com/", api_key="key")
        assert t1.url == "http://test.com"

        # Test without trailing slash
        t2 = SSETransport("http://test.com", api_key="key")
        assert t2.url == "http://test.com"

    @pytest.mark.asyncio
    async def test_call_tool_with_different_response_formats(self, transport):
        """Test call_tool with various response formats."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        # Test with error response
        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "Tool error"}}),
        ):
            result = await transport.call_tool("test", {})
            assert result["isError"] is True

        # Test with successful response
        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"result": {"content": "success"}}),
        ):
            result = await transport.call_tool("test", {})
            assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_is_connected_with_stale_session(self, transport):
        """Test is_connected with stale session."""
        transport._initialized = True
        transport._last_successful_ping = 0  # Very old
        transport.session_timeout = 1  # Short timeout

        # Should be disconnected due to stale session
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_call_tool_with_explicit_timeout(self, transport):
        """Test call_tool with explicit timeout parameter."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"result": {"content": "success"}}),
        ) as mock_send:
            await transport.call_tool("test", {}, timeout=15.0)
            # Verify timeout was passed to _send_request
            call_args = mock_send.call_args
            assert call_args[1]["timeout"] == 15.0

    @pytest.mark.asyncio
    async def test_oauth_error_detection(self, transport):
        """Test OAuth error detection helper method."""
        assert transport._is_oauth_error("invalid_token") is True
        assert transport._is_oauth_error("expired token detected") is True
        assert transport._is_oauth_error("OAuth validation failed") is True
        assert transport._is_oauth_error("unauthorized access") is True
        assert transport._is_oauth_error("token expired") is True
        assert transport._is_oauth_error("authentication failed") is True
        assert transport._is_oauth_error("invalid access token") is True
        assert transport._is_oauth_error("some other error") is False
        assert transport._is_oauth_error("") is False
        assert transport._is_oauth_error(None) is False

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_with_refresh_success(self, transport):
        """Test call_tool handles OAuth error with successful token refresh."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        # Mock OAuth refresh callback
        async def mock_oauth_refresh():
            return {"Authorization": "Bearer new-token"}

        transport.oauth_refresh_callback = mock_oauth_refresh

        # First call fails with OAuth error, second succeeds
        call_count = 0

        async def mock_send_request(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": {"message": "expired token"}}
            return {"result": {"content": [{"type": "text", "text": '{"success": true}'}]}}

        with patch.object(transport, "_send_request", side_effect=mock_send_request):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is False
            assert result["content"]["success"] is True
            assert call_count == 2
            assert transport.configured_headers["Authorization"] == "Bearer new-token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_without_callback(self, transport):
        """Test call_tool handles OAuth error without refresh callback."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"
        transport.oauth_refresh_callback = None

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "expired token"}}),
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "expired token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_refresh_fails(self, transport):
        """Test call_tool when OAuth refresh callback raises exception."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        async def mock_oauth_refresh():
            raise Exception("Refresh service unavailable")

        transport.oauth_refresh_callback = mock_oauth_refresh

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "expired token"}}),
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "expired token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_refresh_no_auth_header(self, transport):
        """Test call_tool when OAuth refresh doesn't return Authorization header."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        async def mock_oauth_refresh():
            return {"X-Custom": "header"}

        transport.oauth_refresh_callback = mock_oauth_refresh

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "expired token"}}),
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "expired token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_refresh_returns_none(self, transport):
        """Test call_tool when OAuth refresh returns None."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        async def mock_oauth_refresh():
            return None

        transport.oauth_refresh_callback = mock_oauth_refresh

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "expired token"}}),
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "expired token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_retry_also_fails(self, transport):
        """Test call_tool when retry after OAuth refresh also fails."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        async def mock_oauth_refresh():
            return {"Authorization": "Bearer new-token"}

        transport.oauth_refresh_callback = mock_oauth_refresh

        # Both calls fail with OAuth error
        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "expired token"}}),
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "expired token"

    @pytest.mark.asyncio
    async def test_call_tool_oauth_error_retry_different_error(self, transport):
        """Test call_tool when retry fails with different error."""
        transport._initialized = True
        transport.message_url = "http://test.com/messages/test"

        async def mock_oauth_refresh():
            return {"Authorization": "Bearer new-token"}

        transport.oauth_refresh_callback = mock_oauth_refresh

        call_count = 0

        async def mock_send_request(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": {"message": "expired token"}}
            return {"error": {"message": "tool not found"}}

        with patch.object(transport, "_send_request", side_effect=mock_send_request):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is True
            assert result["error"] == "tool not found"

    @pytest.mark.asyncio
    async def test_list_resources_with_error(self, transport):
        """Test list_resources with error response."""
        transport._initialized = True

        with patch.object(transport, "_send_request", AsyncMock(side_effect=Exception("List error"))):
            result = await transport.list_resources()
            assert result == {}

    @pytest.mark.asyncio
    async def test_list_prompts_with_error(self, transport):
        """Test list_prompts with error response."""
        transport._initialized = True

        with patch.object(transport, "_send_request", AsyncMock(side_effect=Exception("List error"))):
            result = await transport.list_prompts()
            assert result == {}

    def test_repr_with_session(self, transport):
        """Test __repr__ with active session."""
        transport._initialized = True
        transport.session_id = "test-session-123"
        transport._metrics.total_calls = 20
        transport._metrics.successful_calls = 18

        repr_str = repr(transport)
        assert "SSETransport" in repr_str
        assert "status=initialized" in repr_str
        assert "calls: 20" in repr_str
        assert "success: 90.0%" in repr_str

    @pytest.mark.asyncio
    async def test_process_sse_stream_endpoint_event_full_url(self, transport):
        """Test processing SSE stream with endpoint event containing full URL."""
        mock_response = AsyncMock()

        async def mock_lines():
            yield "event: endpoint"
            yield "data: http://test.com/sse/message?sessionId=test-456"

        mock_response.aiter_lines = mock_lines
        transport.sse_response = mock_response

        task = asyncio.create_task(transport._process_sse_stream())
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert transport.message_url == "http://test.com/sse/message?sessionId=test-456"
        assert transport.session_id == "test-456"

    @pytest.mark.asyncio
    async def test_process_sse_stream_endpoint_event_relative_path(self, transport):
        """Test processing SSE stream with endpoint event containing relative path."""
        mock_response = AsyncMock()

        async def mock_lines():
            yield "event: endpoint"
            yield "data: /sse/message?session_id=test-789"

        mock_response.aiter_lines = mock_lines
        transport.sse_response = mock_response

        task = asyncio.create_task(transport._process_sse_stream())
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert transport.message_url == "http://test.com/sse/message?session_id=test-789"
        assert transport.session_id == "test-789"

    @pytest.mark.asyncio
    async def test_process_sse_stream_old_format_without_session_id(self, transport):
        """Test processing SSE stream with old format without session_id parameter."""
        mock_response = AsyncMock()

        async def mock_lines():
            yield "data: /messages/somepath"

        mock_response.aiter_lines = mock_lines
        transport.sse_response = mock_response

        task = asyncio.create_task(transport._process_sse_stream())
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert transport.message_url == "http://test.com/messages/somepath"
        assert transport.session_id is not None  # Should have generated a UUID

    @pytest.mark.asyncio
    async def test_process_sse_stream_keepalive_pings(self, transport):
        """Test processing SSE stream ignores keepalive pings."""
        mock_response = AsyncMock()

        async def mock_lines():
            yield "data: ping"
            yield "data: {}"
            yield "data: []"

        mock_response.aiter_lines = mock_lines
        transport.sse_response = mock_response

        task = asyncio.create_task(transport._process_sse_stream())
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # No session should be discovered
        assert transport.message_url is None

    @pytest.mark.asyncio
    async def test_is_connected_with_grace_period(self, transport):
        """Test is_connected returns True during grace period."""
        transport._initialized = True
        transport.session_id = "test-session"
        transport._initialization_time = time.time()
        transport._connection_grace_period = 30.0

        # Should be connected during grace period
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_is_connected_after_grace_period_with_failures(self, transport):
        """Test is_connected returns False after grace period with failures."""
        transport._initialized = True
        transport.session_id = "test-session"
        transport._initialization_time = time.time() - 60.0  # 60 seconds ago
        transport._connection_grace_period = 30.0
        transport._consecutive_failures = 5
        transport._max_consecutive_failures = 5

        # Should be disconnected after grace period with max failures
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_with_sse_task_exception(self, transport):
        """Test is_connected handles SSE task with exception."""
        transport._initialized = True
        transport.session_id = "test-session"

        # Create a completed task with an exception
        async def failing_task():
            raise RuntimeError("SSE task failed")

        transport.sse_task = asyncio.create_task(failing_task())
        await asyncio.sleep(0.1)  # Let task fail

        # Should detect task failure
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_with_recent_successful_ping(self, transport):
        """Test is_connected returns True with recent successful ping."""
        transport._initialized = True
        transport.session_id = "test-session"
        transport._initialization_time = time.time() - 60.0  # Outside grace period
        transport._last_successful_ping = time.time() - 10.0  # 10 seconds ago

        # Should be connected with recent successful operation
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_send_request_with_202_accepted(self, transport):
        """Test _send_request handles 202 Accepted response."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 202
        transport.send_client.post.return_value = mock_response

        async def simulate_response():
            await asyncio.sleep(0.1)
            req_id = next(iter(transport.pending_requests))
            transport.pending_requests[req_id].set_result({"jsonrpc": "2.0", "id": req_id, "result": "async result"})

        asyncio.create_task(simulate_response())

        result = await transport._send_request("tools/call", {"name": "test"})
        assert result["result"] == "async result"

    @pytest.mark.asyncio
    async def test_send_request_with_non_200_non_202_status(self, transport):
        """Test _send_request handles non-200/202 status codes."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 500
        transport.send_client.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="HTTP request failed with status: 500"):
            await transport._send_request("tools/call", {"name": "test"})

    @pytest.mark.asyncio
    async def test_send_notification_success(self, transport):
        """Test sending notification successfully."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 202
        transport.send_client.post.return_value = mock_response

        await transport._send_notification("test_notification", {"param": "value"})
        transport.send_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_failure(self, transport):
        """Test sending notification with non-success status."""
        transport.message_url = "http://test.com/messages/test"
        transport.send_client = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 500
        transport.send_client.post.return_value = mock_response

        # Should log warning but not raise
        await transport._send_notification("test_notification", {})

    @pytest.mark.asyncio
    async def test_list_resources_with_error_response(self, transport):
        """Test list_resources handles error response."""
        transport._initialized = True

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "Resources not supported"}}),
        ):
            result = await transport.list_resources()
            assert result == {}

    @pytest.mark.asyncio
    async def test_list_prompts_with_error_response(self, transport):
        """Test list_prompts handles error response."""
        transport._initialized = True

        with patch.object(
            transport,
            "_send_request",
            AsyncMock(return_value={"error": {"message": "Prompts not supported"}}),
        ):
            result = await transport.list_prompts()
            assert result == {}

    @pytest.mark.asyncio
    async def test_cleanup_with_pending_futures(self, transport):
        """Test cleanup cancels pending request futures."""
        future1 = asyncio.Future()
        future2 = asyncio.Future()
        transport.pending_requests = {"req1": future1, "req2": future2}

        await transport._cleanup()

        assert future1.cancelled()
        assert future2.cancelled()
        assert transport.pending_requests == {}

    @pytest.mark.asyncio
    async def test_cleanup_with_stream_context_error(self, transport):
        """Test cleanup handles stream context exit error."""
        transport.sse_stream_context = AsyncMock()
        transport.sse_stream_context.__aexit__.side_effect = Exception("Exit error")

        # Should not raise, just log
        await transport._cleanup()

    def test_get_metrics_includes_health_info(self, transport):
        """Test get_metrics includes health information."""
        transport._initialized = True
        transport.session_id = "test-session"
        transport._consecutive_failures = 2
        transport._initialization_time = time.time()

        metrics = transport.get_metrics()

        assert "is_connected" in metrics
        assert "consecutive_failures" in metrics
        assert "max_consecutive_failures" in metrics
        assert "grace_period_active" in metrics
        assert metrics["consecutive_failures"] == 2

    def test_reset_metrics_preserves_some_values(self, transport):
        """Test reset_metrics preserves certain metric values."""
        transport._metrics.last_ping_time = 1.5
        transport._metrics.initialization_time = 2.0
        transport._metrics.session_discoveries = 3
        transport._metrics.total_calls = 10

        transport.reset_metrics()

        assert transport._metrics.last_ping_time == 1.5
        assert transport._metrics.initialization_time == 2.0
        assert transport._metrics.session_discoveries == 3
        assert transport._metrics.total_calls == 0
