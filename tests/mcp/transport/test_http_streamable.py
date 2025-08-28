# tests/mcp/transport/test_http_streamable_transport.py
"""
Tests for HTTPStreamableTransport class with consistent interface.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.mcp.transport.http_streamable_transport import HTTPStreamableTransport


class TestHTTPStreamableTransport:
    """Test HTTPStreamableTransport class with consistent interface."""

    @pytest.fixture
    def transport(self):
        """Create HTTPStreamableTransport instance with consistent parameters."""
        return HTTPStreamableTransport(
            "http://test.com",
            api_key="api_key",
            connection_timeout=30.0,
            default_timeout=30.0,
            session_id="test-session",
            enable_metrics=True,
        )

    @pytest.fixture
    def transport_no_metrics(self):
        """Create HTTPStreamableTransport instance with metrics disabled."""
        return HTTPStreamableTransport("http://test.com", enable_metrics=False)

    def test_init_url_normalization(self):
        """Test URL normalization to /mcp endpoint."""
        # URL without /mcp gets it added
        transport = HTTPStreamableTransport("http://test.com")
        assert transport.url == "http://test.com/mcp"

        # URL with /mcp is preserved
        transport = HTTPStreamableTransport("http://test.com/mcp")
        assert transport.url == "http://test.com/mcp"

        # URL with trailing slash handled correctly
        transport = HTTPStreamableTransport("http://test.com/")
        assert transport.url == "http://test.com/mcp"

    def test_init_parameters(self, transport):
        """Test initialization with consistent parameters."""
        assert transport.url == "http://test.com/mcp"
        assert transport.api_key == "api_key"
        assert transport.session_id == "test-session"
        assert transport.enable_metrics is True
        assert transport.default_timeout == 30.0
        assert transport.connection_timeout == 30.0

    @pytest.mark.asyncio
    async def test_initialize_success(self, transport):
        """Test successful HTTP Streamable transport initialization with metrics tracking."""
        mock_context = AsyncMock()
        mock_streams = (Mock(), Mock())  # (read_stream, write_stream)

        with (
            patch("chuk_tool_processor.mcp.transport.http_streamable_transport.http_client", return_value=mock_context),
            patch(
                "chuk_tool_processor.mcp.transport.http_streamable_transport.send_ping", AsyncMock(return_value=True)
            ),
        ):
            mock_context.__aenter__.return_value = mock_streams

            result = await transport.initialize()

            assert result is True
            assert transport._initialized is True
            assert transport._read_stream == mock_streams[0]
            assert transport._write_stream == mock_streams[1]

            # Check metrics were updated
            metrics = transport.get_metrics()
            assert metrics["initialization_time"] > 0
            assert metrics["last_ping_time"] > 0

    @pytest.mark.asyncio
    async def test_initialize_ping_fails(self, transport):
        """Test HTTP Streamable initialization when ping fails but connection succeeds."""
        mock_context = AsyncMock()
        mock_streams = (Mock(), Mock())

        with (
            patch("chuk_tool_processor.mcp.transport.http_streamable_transport.http_client", return_value=mock_context),
            patch(
                "chuk_tool_processor.mcp.transport.http_streamable_transport.send_ping", AsyncMock(return_value=False)
            ),
        ):
            mock_context.__aenter__.return_value = mock_streams

            result = await transport.initialize()

            # Still considered initialized even if ping fails
            assert result is True
            assert transport._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_timeout(self, transport):
        """Test HTTP Streamable transport initialization timeout."""
        mock_context = AsyncMock()

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.http_client", return_value=mock_context
        ):
            # Simulate timeout during context entry
            mock_context.__aenter__.side_effect = TimeoutError()

            result = await transport.initialize()

            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test HTTP Streamable ping when initialized with metrics tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_ping", AsyncMock(return_value=True)
        ):
            result = await transport.send_ping()
            assert result is True

            # Check ping metrics were updated
            metrics = transport.get_metrics()
            assert metrics["last_ping_time"] > 0

    @pytest.mark.asyncio
    async def test_send_ping_not_initialized(self, transport):
        """Test HTTP Streamable ping when not initialized."""
        assert transport._initialized is False
        result = await transport.send_ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_ping_exception(self, transport):
        """Test HTTP Streamable ping with exception and metrics tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_ping",
            AsyncMock(side_effect=Exception("Stream error")),
        ):
            result = await transport.send_ping()
            assert result is False

            # Check stream error metrics
            metrics = transport.get_metrics()
            assert metrics["stream_errors"] == 1

    def test_is_connected(self, transport):
        """Test connection status check (consistent method)."""
        # not initialized
        assert transport.is_connected() is False
        # initialized but no streams
        transport._initialized = True
        assert transport.is_connected() is False
        # fully connected
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        assert transport.is_connected() is True

    @pytest.mark.asyncio
    async def test_get_tools_success(self, transport):
        """Test HTTP Streamable get tools when initialized with performance tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        expected_tools = [{"name": "search"}, {"name": "research"}]

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_list",
            AsyncMock(return_value={"tools": expected_tools}),
        ):
            tools = await transport.get_tools()
            assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_tools_list_response(self, transport):
        """Test HTTP Streamable get tools when response is a list."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        expected_tools = [{"name": "search"}]

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_list",
            AsyncMock(return_value=expected_tools),
        ):
            tools = await transport.get_tools()
            assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_tools_not_initialized(self, transport):
        """Test HTTP Streamable get tools when not initialized."""
        assert transport._initialized is False
        tools = await transport.get_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test HTTP Streamable call tool when initialized with metrics tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        response = {"result": {"content": [{"type": "text", "text": '{"answer": "success"}'}]}}

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_call",
            AsyncMock(return_value=response),
        ):
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
        """Test HTTP Streamable call tool with custom timeout parameter."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        response = {"result": {"content": "success"}}

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_call",
            AsyncMock(return_value=response),
        ) as mock_send:
            result = await transport.call_tool("search", {"query": "test"}, timeout=15.0)
            assert result["isError"] is False

            # Verify the call was made with correct parameters
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test HTTP Streamable call tool when not initialized."""
        assert transport._initialized is False
        result = await transport.call_tool("test", {})
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self, transport):
        """Test HTTP Streamable call tool with timeout and metrics tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_call",
            AsyncMock(side_effect=asyncio.TimeoutError),
        ):
            result = await transport.call_tool("search", {}, timeout=1.0)
            assert result["isError"] is True
            assert "timed out after 1.0s" in result["error"]

            # Check timeout failure metrics
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_call_tool_exception(self, transport):
        """Test HTTP Streamable call tool with exception and metrics tracking."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_call",
            AsyncMock(side_effect=Exception("Stream broken")),
        ):
            result = await transport.call_tool("search", {})
            assert result["isError"] is True
            assert "Stream broken" in result["error"]

            # Check failure metrics including stream error
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["failed_calls"] == 1
            assert metrics["stream_errors"] == 1

    @pytest.mark.asyncio
    async def test_metrics_functionality(self, transport):
        """Test metrics get and reset functionality."""
        # Initial metrics
        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["successful_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["avg_response_time"] == 0.0
        assert metrics["stream_errors"] == 0

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
        transport_no_metrics._read_stream = Mock()
        transport_no_metrics._write_stream = Mock()

        # Metrics should still be available but not actively updated during operations
        assert transport_no_metrics.enable_metrics is False
        metrics = transport_no_metrics.get_metrics()
        assert isinstance(metrics, dict)

    @pytest.mark.asyncio
    async def test_list_resources_success(self, transport):
        """Test listing resources when initialized."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        expected_resources = {"resources": [{"name": "resource1"}]}

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_resources_list",
            AsyncMock(return_value=expected_resources),
        ):
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
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        expected_prompts = {"prompts": [{"name": "prompt1"}]}

        with patch(
            "chuk_tool_processor.mcp.transport.http_streamable_transport.send_prompts_list",
            AsyncMock(return_value=expected_prompts),
        ):
            result = await transport.list_prompts()
            assert result == expected_prompts

    @pytest.mark.asyncio
    async def test_close_success(self, transport):
        """Test HTTP Streamable close when initialized with metrics logging."""
        transport._initialized = True
        # Add some metrics to test logging
        transport._metrics["total_calls"] = 5
        transport._metrics["successful_calls"] = 4
        transport._metrics["failed_calls"] = 1

        mock_context = AsyncMock()
        transport._http_context = mock_context

        await transport.close()

        assert transport._initialized is False
        assert transport._http_context is None
        assert transport._read_stream is None
        assert transport._write_stream is None
        mock_context.__aexit__.assert_called_once_with(None, None, None)

    @pytest.mark.asyncio
    async def test_close_no_context(self, transport):
        """Test HTTP Streamable close when no context exists."""
        transport._initialized = False
        await transport.close()
        assert transport._initialized is False

    def test_get_streams(self, transport):
        """Test getting streams for backward compatibility."""
        # No streams when not initialized
        assert transport.get_streams() == []

        # Streams available when initialized
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()
        streams = transport.get_streams()
        assert len(streams) == 1
        assert streams[0] == (transport._read_stream, transport._write_stream)

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
            pytest.raises(RuntimeError, match="Failed to initialize HTTPStreamableTransport"),
        ):
            async with transport:
                pass

    def test_repr_consistent_format(self, transport):
        """Test string representation follows consistent format."""
        # Not initialized
        repr_str = repr(transport)
        assert "HTTPStreamableTransport" in repr_str
        assert "status=not initialized" in repr_str
        assert "url=http://test.com/mcp" in repr_str

        # Initialized with metrics
        transport._initialized = True
        transport._metrics["total_calls"] = 10
        transport._metrics["successful_calls"] = 8

        repr_str = repr(transport)
        assert "status=initialized" in repr_str
        assert "calls: 10" in repr_str
        assert "success: 80.0%" in repr_str

    @pytest.mark.asyncio
    async def test_response_normalization(self, transport):
        """Test that response normalization uses base class methods."""
        transport._initialized = True
        transport._read_stream = Mock()
        transport._write_stream = Mock()

        # Test various response formats using base class normalization
        test_cases = [
            # Standard MCP content format
            {
                "result": {"content": [{"type": "text", "text": '{"result": "success"}'}]},
                "expected": {"isError": False, "content": {"result": "success"}},
            },
            # Plain text content
            {
                "result": {"content": [{"type": "text", "text": "plain text"}]},
                "expected": {"isError": False, "content": "plain text"},
            },
            # Direct result
            {"result": {"value": 42}, "expected": {"isError": False, "content": {"value": 42}}},
            # Error response
            {"error": {"message": "Tool failed"}, "expected": {"isError": True, "error": "Tool failed"}},
        ]

        for case in test_cases:
            # FIXED: Use correct path without slash
            with patch(
                "chuk_tool_processor.mcp.transport.http_streamable_transport.send_tools_call",
                AsyncMock(return_value=case),
            ):
                result = await transport.call_tool("test", {})
                assert result == case["expected"]

    def test_http_parameters_creation(self, transport):
        """Test that HTTP parameters are created correctly."""
        # This test verifies the StreamableHTTPParameters are constructed properly
        # We can't easily test the actual construction without mocking the entire
        # http_client call, but we can verify the transport stores the right values
        assert transport.url == "http://test.com/mcp"
        assert transport.api_key == "api_key"
        assert transport.session_id == "test-session"
        assert transport.connection_timeout == 30.0
        assert transport.default_timeout == 30.0
