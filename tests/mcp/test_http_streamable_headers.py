"""Tests for HTTP Streamable transport with custom headers support."""

from unittest.mock import AsyncMock, patch

import pytest

from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport.http_streamable_transport import HTTPStreamableTransport


class TestHTTPStreamableTransportHeaders:
    """Tests for HTTPStreamableTransport custom headers functionality."""

    def test_init_with_headers(self):
        """Test transport initialization with custom headers."""
        headers = {"Authorization": "Bearer test-token", "X-Custom-Header": "custom-value"}

        transport = HTTPStreamableTransport(url="https://example.com/mcp", headers=headers)

        assert transport.configured_headers == headers
        assert "Authorization" in transport.configured_headers
        assert transport.configured_headers["Authorization"] == "Bearer test-token"

    def test_init_without_headers(self):
        """Test transport initialization without custom headers."""
        transport = HTTPStreamableTransport(url="https://example.com/mcp")

        assert transport.configured_headers == {}

    def test_headers_with_api_key(self):
        """Test that both headers and api_key can coexist."""
        headers = {"X-Custom": "value"}

        transport = HTTPStreamableTransport(url="https://example.com/mcp", api_key="test-key", headers=headers)

        assert transport.api_key == "test-key"
        assert transport.configured_headers == headers

    @pytest.mark.asyncio
    async def test_headers_used_in_requests(self):
        """Test that configured headers are used in HTTP requests."""
        headers = {"Authorization": "Bearer oauth-token"}

        with patch("chuk_tool_processor.mcp.transport.http_streamable_transport.http_client") as mock_client:
            # Mock the http_client context manager
            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
            mock_context.__aexit__ = AsyncMock(return_value=None)

            # http_client is called as a function returning a context manager
            mock_client.return_value = mock_context

            # Mock the send_initialize and send_ping functions
            with (
                patch("chuk_tool_processor.mcp.transport.http_streamable_transport.send_initialize") as mock_init,
                patch("chuk_tool_processor.mcp.transport.http_streamable_transport.send_ping") as mock_ping,
            ):
                mock_init.return_value = None
                mock_ping.return_value = True

                transport = HTTPStreamableTransport(url="https://example.com/mcp", headers=headers)

                # Initialize should use the headers
                await transport.initialize()

                # Verify http_client was called
                assert mock_client.called

                # Get the call arguments
                call_args = mock_client.call_args

                # The first argument should be StreamableHTTPParameters with headers
                http_params = call_args[0][0]
                assert hasattr(http_params, "headers")
                assert "Authorization" in http_params.headers
                assert http_params.headers["Authorization"] == "Bearer oauth-token"


class TestStreamManagerHeadersPassthrough:
    """Tests for StreamManager passing headers to HTTP transport."""

    @pytest.mark.asyncio
    async def test_headers_passthrough_to_http_transport(self):
        """Test that headers from server config are passed to HTTPStreamableTransport."""
        servers = [
            {
                "name": "test-server",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer test-token", "X-Custom": "value"},
            }
        ]

        with patch("chuk_tool_processor.mcp.stream_manager.HTTPStreamableTransport") as MockTransport:
            # Create mock transport instance
            mock_transport = AsyncMock()
            mock_transport.initialize = AsyncMock(return_value=True)
            mock_transport.send_ping = AsyncMock(return_value=True)
            mock_transport.get_tools = AsyncMock(return_value=[{"name": "test_tool", "description": "Test tool"}])

            MockTransport.return_value = mock_transport

            # Initialize stream manager
            stream_manager = StreamManager()
            await stream_manager.initialize_with_http_streamable(
                servers=servers, connection_timeout=5.0, default_timeout=5.0
            )

            # Verify HTTPStreamableTransport was called with headers
            MockTransport.assert_called_once()
            call_kwargs = MockTransport.call_args.kwargs

            assert "headers" in call_kwargs
            assert call_kwargs["headers"] == {"Authorization": "Bearer test-token", "X-Custom": "value"}

            # Verify transport was initialized
            assert mock_transport.initialize.called

    @pytest.mark.asyncio
    async def test_no_headers_still_works(self):
        """Test that servers without headers still work."""
        servers = [{"name": "test-server", "url": "https://example.com/mcp"}]

        with patch("chuk_tool_processor.mcp.stream_manager.HTTPStreamableTransport") as MockTransport:
            mock_transport = AsyncMock()
            mock_transport.initialize = AsyncMock(return_value=True)
            mock_transport.send_ping = AsyncMock(return_value=True)
            mock_transport.get_tools = AsyncMock(return_value=[])

            MockTransport.return_value = mock_transport

            stream_manager = StreamManager()
            await stream_manager.initialize_with_http_streamable(
                servers=servers, connection_timeout=5.0, default_timeout=5.0
            )

            # Should be called without headers parameter
            MockTransport.assert_called_once()
            call_kwargs = MockTransport.call_args.kwargs

            # Headers should not be in kwargs or should be empty dict
            assert call_kwargs.get("headers", {}) == {}

    @pytest.mark.asyncio
    async def test_multiple_servers_with_different_headers(self):
        """Test multiple servers with different header configurations."""
        servers = [
            {"name": "server1", "url": "https://server1.com/mcp", "headers": {"Authorization": "Bearer token1"}},
            {"name": "server2", "url": "https://server2.com/mcp", "headers": {"Authorization": "Bearer token2"}},
            {"name": "server3", "url": "https://server3.com/mcp"},
        ]

        with patch("chuk_tool_processor.mcp.stream_manager.HTTPStreamableTransport") as MockTransport:
            mock_transport = AsyncMock()
            mock_transport.initialize = AsyncMock(return_value=True)
            mock_transport.send_ping = AsyncMock(return_value=True)
            mock_transport.get_tools = AsyncMock(return_value=[])

            MockTransport.return_value = mock_transport

            stream_manager = StreamManager()
            await stream_manager.initialize_with_http_streamable(
                servers=servers, connection_timeout=5.0, default_timeout=5.0
            )

            # Should be called 3 times
            assert MockTransport.call_count == 3

            # Check each call
            calls = MockTransport.call_args_list

            # Server 1 - with headers
            assert calls[0].kwargs.get("headers") == {"Authorization": "Bearer token1"}

            # Server 2 - with different headers
            assert calls[1].kwargs.get("headers") == {"Authorization": "Bearer token2"}

            # Server 3 - no headers
            assert calls[2].kwargs.get("headers", {}) == {}


class TestOAuthHeadersIntegration:
    """Integration tests for OAuth-style headers."""

    @pytest.mark.asyncio
    async def test_oauth_bearer_token(self):
        """Test OAuth bearer token in Authorization header."""
        servers = [
            {
                "name": "oauth-server",
                "url": "https://api.example.com/mcp",
                "headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
            }
        ]

        with patch("chuk_tool_processor.mcp.stream_manager.HTTPStreamableTransport") as MockTransport:
            mock_transport = AsyncMock()
            mock_transport.initialize = AsyncMock(return_value=True)
            mock_transport.send_ping = AsyncMock(return_value=True)
            mock_transport.get_tools = AsyncMock(return_value=[])

            MockTransport.return_value = mock_transport

            stream_manager = StreamManager()
            await stream_manager.initialize_with_http_streamable(servers=servers)

            # Verify OAuth header was passed
            call_kwargs = MockTransport.call_args.kwargs
            assert "Authorization" in call_kwargs.get("headers", {})
            assert call_kwargs["headers"]["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_multiple_auth_headers(self):
        """Test multiple authentication-related headers."""
        servers = [
            {
                "name": "multi-auth-server",
                "url": "https://api.example.com/mcp",
                "headers": {"Authorization": "Bearer token", "X-API-Key": "api-key-123", "X-Session-Id": "session-abc"},
            }
        ]

        with patch("chuk_tool_processor.mcp.stream_manager.HTTPStreamableTransport") as MockTransport:
            mock_transport = AsyncMock()
            mock_transport.initialize = AsyncMock(return_value=True)
            mock_transport.send_ping = AsyncMock(return_value=True)
            mock_transport.get_tools = AsyncMock(return_value=[])

            MockTransport.return_value = mock_transport

            stream_manager = StreamManager()
            await stream_manager.initialize_with_http_streamable(servers=servers)

            # Verify all headers were passed
            call_kwargs = MockTransport.call_args.kwargs
            headers = call_kwargs.get("headers", {})

            assert headers["Authorization"] == "Bearer token"
            assert headers["X-API-Key"] == "api-key-123"
            assert headers["X-Session-Id"] == "session-abc"
