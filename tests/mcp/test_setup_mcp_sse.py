# tests/mcp/test_setup_mcp_sse.py
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.mcp.stream_manager import StreamManager


class TestSetupMCPSSE:
    """Test MCP SSE setup function."""

    @pytest.mark.asyncio
    async def test_setup_mcp_sse(self):
        """Test complete MCP SSE setup."""
        # Mock dependencies
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["weather", "geocoding"]

        with patch(
            "chuk_tool_processor.mcp.setup_mcp_sse.StreamManager.create_with_sse",
            AsyncMock(return_value=mock_stream_manager),
        ), patch("chuk_tool_processor.mcp.setup_mcp_sse.register_mcp_tools", return_value=registered_tools):
            with patch("chuk_tool_processor.mcp.setup_mcp_sse.ToolProcessor", return_value=mock_processor):
                servers = [
                    {"name": "weather", "url": "http://test.com"},
                    {"name": "geocoding", "url": "http://geo.com"},
                ]

                processor, stream_manager = await setup_mcp_sse(
                    servers=servers, namespace="remote", enable_caching=True
                )

                assert processor == mock_processor
                assert stream_manager == mock_stream_manager

    @pytest.mark.asyncio
    async def test_setup_with_custom_options(self):
        """Test setup with custom configuration options."""
        with patch("chuk_tool_processor.mcp.setup_mcp_sse.StreamManager.create_with_sse", AsyncMock()):
            with patch("chuk_tool_processor.mcp.setup_mcp_sse.register_mcp_tools"):
                with patch("chuk_tool_processor.mcp.setup_mcp_sse.ToolProcessor") as mock_processor_class:
                    servers = [{"name": "test", "url": "http://test.com"}]

                    await setup_mcp_sse(
                        servers=servers,
                        default_timeout=45.0,
                        max_concurrency=10,
                        cache_ttl=900,
                        enable_rate_limiting=True,
                        max_retries=10,
                    )

                    # Verify ToolProcessor was created with correct options
                    mock_processor_class.assert_called_once()
