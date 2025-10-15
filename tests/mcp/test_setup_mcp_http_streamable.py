# tests/mcp/test_setup_mcp_http_streamable.py
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
from chuk_tool_processor.mcp.stream_manager import StreamManager


class TestSetupMCPHTTPStreamable:
    """Test MCP HTTP Streamable setup function."""

    @pytest.mark.asyncio
    async def test_setup_mcp_http_streamable_basic(self):
        """Test complete MCP HTTP Streamable setup with basic configuration."""
        # Mock dependencies
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["weather", "geocoding"]

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=registered_tools),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor",
                return_value=mock_processor,
            ),
        ):
            servers = [
                {"name": "weather", "url": "http://weather.com"},
                {"name": "geocoding", "url": "http://geo.com"},
            ]

            processor, stream_manager = await setup_mcp_http_streamable(servers=servers, namespace="http_test")

            assert processor == mock_processor
            assert stream_manager == mock_stream_manager

    @pytest.mark.asyncio
    async def test_setup_with_custom_options(self):
        """Test setup with custom configuration options."""
        mock_stream_manager = Mock(spec=StreamManager)

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ) as mock_create,
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=["tool1"]),
            ) as mock_register,
            patch("chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor") as mock_processor_class,
        ):
            servers = [{"name": "test", "url": "http://test.com", "api_key": "test-key"}]
            server_names = {0: "custom_name"}

            processor, stream_manager = await setup_mcp_http_streamable(
                servers=servers,
                server_names=server_names,
                connection_timeout=60.0,
                default_timeout=45.0,
                max_concurrency=10,
                enable_caching=False,
                cache_ttl=900,
                enable_rate_limiting=True,
                global_rate_limit=100,
                tool_rate_limits={"tool1": (10, 60)},
                enable_retries=False,
                max_retries=5,
                namespace="custom_ns",
            )

            # Verify StreamManager.create_with_http_streamable was called with correct params
            mock_create.assert_called_once_with(
                servers=servers,
                server_names=server_names,
                connection_timeout=60.0,
                default_timeout=45.0,
            )

            # Verify register_mcp_tools was called with correct namespace
            mock_register.assert_called_once_with(stream_manager, namespace="custom_ns")

            # Verify ToolProcessor was created with correct options
            mock_processor_class.assert_called_once_with(
                default_timeout=45.0,
                max_concurrency=10,
                enable_caching=False,
                cache_ttl=900,
                enable_rate_limiting=True,
                global_rate_limit=100,
                tool_rate_limits={"tool1": (10, 60)},
                enable_retries=False,
                max_retries=5,
            )

    @pytest.mark.asyncio
    async def test_setup_with_default_namespace(self):
        """Test that default namespace 'http' is used."""
        mock_stream_manager = Mock(spec=StreamManager)

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=[]),
            ) as mock_register,
            patch("chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor"),
        ):
            servers = [{"name": "test", "url": "http://test.com"}]

            await setup_mcp_http_streamable(servers=servers)

            # Verify default namespace is used
            call_args = mock_register.call_args
            assert call_args[1]["namespace"] == "http"

    @pytest.mark.asyncio
    async def test_setup_with_empty_servers(self):
        """Test setup with empty server list."""
        mock_stream_manager = Mock(spec=StreamManager)

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=[]),
            ),
            patch("chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor"),
        ):
            servers = []

            processor, stream_manager = await setup_mcp_http_streamable(servers=servers)

            assert stream_manager == mock_stream_manager
            assert processor is not None

    @pytest.mark.asyncio
    async def test_setup_with_multiple_servers(self):
        """Test setup with multiple servers."""
        mock_stream_manager = Mock(spec=StreamManager)
        registered_tools = ["server1_tool1", "server1_tool2", "server2_tool1"]

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=registered_tools),
            ),
            patch("chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor"),
        ):
            servers = [
                {"name": "server1", "url": "http://server1.com"},
                {"name": "server2", "url": "http://server2.com"},
                {"name": "server3", "url": "http://server3.com", "api_key": "key123"},
            ]

            processor, stream_manager = await setup_mcp_http_streamable(servers=servers)

            assert stream_manager == mock_stream_manager
            assert processor is not None

    @pytest.mark.asyncio
    async def test_setup_passes_all_processor_options(self):
        """Test that all ToolProcessor configuration options are passed through."""
        mock_stream_manager = Mock(spec=StreamManager)

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=[]),
            ),
            patch("chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor") as mock_processor_class,
        ):
            servers = [{"name": "test", "url": "http://test.com"}]

            await setup_mcp_http_streamable(
                servers=servers,
                default_timeout=25.0,
                max_concurrency=5,
                enable_caching=True,
                cache_ttl=600,
                enable_rate_limiting=False,
                global_rate_limit=None,
                tool_rate_limits=None,
                enable_retries=True,
                max_retries=2,
            )

            # Verify all options were passed to ToolProcessor
            call_kwargs = mock_processor_class.call_args[1]
            assert call_kwargs["default_timeout"] == 25.0
            assert call_kwargs["max_concurrency"] == 5
            assert call_kwargs["enable_caching"] is True
            assert call_kwargs["cache_ttl"] == 600
            assert call_kwargs["enable_rate_limiting"] is False
            assert call_kwargs["global_rate_limit"] is None
            assert call_kwargs["tool_rate_limits"] is None
            assert call_kwargs["enable_retries"] is True
            assert call_kwargs["max_retries"] == 2

    @pytest.mark.asyncio
    async def test_setup_returns_tuple(self):
        """Test that setup returns tuple of (processor, stream_manager)."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.StreamManager.create_with_http_streamable",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.register_mcp_tools",
                AsyncMock(return_value=[]),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_http_streamable.ToolProcessor",
                return_value=mock_processor,
            ),
        ):
            servers = [{"name": "test", "url": "http://test.com"}]

            result = await setup_mcp_http_streamable(servers=servers)

            # Check it's a tuple
            assert isinstance(result, tuple)
            assert len(result) == 2

            # Check the elements
            processor, stream_manager = result
            assert processor == mock_processor
            assert stream_manager == mock_stream_manager
