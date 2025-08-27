# tests/mcp/test_setup_mcp_stdio.py
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.mcp.stream_manager import StreamManager


class TestSetupMCPStdio:
    """Test MCP stdio setup function."""

    @pytest.mark.asyncio
    async def test_setup_mcp_stdio(self):
        """Test complete MCP stdio setup."""
        # Mock dependencies
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo", "calc"]

        with patch(
            "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create", AsyncMock(return_value=mock_stream_manager)
        ), patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools):
            with patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor):
                processor, stream_manager = await setup_mcp_stdio(
                    config_file="test.json",
                    servers=["echo"],
                    namespace="mcp",
                    enable_caching=True,
                    enable_retries=True,
                )

                assert processor == mock_processor
                assert stream_manager == mock_stream_manager

    @pytest.mark.asyncio
    async def test_setup_with_custom_options(self):
        """Test setup with custom configuration options."""
        with patch("chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create", AsyncMock()):
            with patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools"):
                with patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor") as mock_processor_class:
                    await setup_mcp_stdio(
                        config_file="test.json",
                        servers=["echo"],
                        default_timeout=30.0,
                        max_concurrency=5,
                        cache_ttl=600,
                        enable_rate_limiting=True,
                        global_rate_limit=100,
                        max_retries=5,
                    )

                    # Verify ToolProcessor was created with correct options
                    mock_processor_class.assert_called_once()
                    call_kwargs = mock_processor_class.call_args.kwargs
                    assert call_kwargs["default_timeout"] == 30.0
                    assert call_kwargs["max_concurrency"] == 5
                    assert call_kwargs["cache_ttl"] == 600
                    assert call_kwargs["enable_rate_limiting"] is True
                    assert call_kwargs["global_rate_limit"] == 100
                    assert call_kwargs["max_retries"] == 5
