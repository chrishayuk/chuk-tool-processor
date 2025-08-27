# tests/mcp/test_stream_manager.py
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport import MCPBaseTransport, StdioTransport


class TestStreamManager:
    """Test StreamManager class."""

    @pytest.fixture
    def mock_transport(self):
        """Mock transport instance."""
        mock = Mock(spec=StdioTransport)
        mock.initialize = AsyncMock(return_value=True)
        mock.send_ping = AsyncMock(return_value=True)
        mock.get_tools = AsyncMock(return_value=[])
        mock.call_tool = AsyncMock()
        mock.close = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_create_with_stdio(self, mock_transport):
        """Test StreamManager creation with stdio transport."""
        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport", return_value=mock_transport):
            with patch("chuk_tool_processor.mcp.stream_manager.load_config", AsyncMock()):
                manager = await StreamManager.create(config_file="test.json", servers=["echo"], transport_type="stdio")

                assert "echo" in manager.transports
                assert manager.transports["echo"] == mock_transport

    @pytest.mark.asyncio
    async def test_create_with_sse(self, mock_transport):
        """Test StreamManager creation with SSE transport."""
        with patch("chuk_tool_processor.mcp.stream_manager.SSETransport", return_value=mock_transport):
            manager = await StreamManager.create_with_sse(servers=[{"name": "weather", "url": "http://test.com"}])

            assert "weather" in manager.transports
            assert manager.transports["weather"] == mock_transport

    @pytest.mark.asyncio
    async def test_initialize_with_tools(self, mock_transport):
        """Test StreamManager initialization with tools."""
        tools = [{"name": "echo", "description": "Echo tool"}, {"name": "calc", "description": "Calculator tool"}]
        mock_transport.get_tools.return_value = tools

        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport", return_value=mock_transport):
            with patch("chuk_tool_processor.mcp.stream_manager.load_config", AsyncMock()):
                manager = await StreamManager.create(
                    config_file="test.json", servers=["server"], transport_type="stdio"
                )

                all_tools = manager.get_all_tools()
                assert len(all_tools) == 2
                assert all_tools[0]["name"] == "echo"
                assert manager.get_server_for_tool("echo") == "server"

    @pytest.mark.asyncio
    async def test_call_tool(self, mock_transport):
        """Test calling tool through StreamManager."""
        mock_transport.call_tool.return_value = {"result": "OK"}

        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport", return_value=mock_transport):
            with patch("chuk_tool_processor.mcp.stream_manager.load_config", AsyncMock()):
                manager = await StreamManager.create(
                    config_file="test.json", servers=["server"], transport_type="stdio"
                )

                # Map tool to server
                manager.tool_to_server_map["echo"] = "server"

                result = await manager.call_tool("echo", {"message": "test"})
                assert result == {"result": "OK"}

                mock_transport.call_tool.assert_called_once_with("echo", {"message": "test"})

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self):
        """Test calling non-existent tool."""
        manager = StreamManager()
        result = await manager.call_tool("unknown", {})

        assert result["isError"] is True
        assert "No server found" in result["error"]

    @pytest.mark.asyncio
    async def test_close_all_transports(self, mock_transport):
        """Test closing all transports."""
        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport", return_value=mock_transport):
            with patch("chuk_tool_processor.mcp.stream_manager.load_config", AsyncMock()):
                manager = await StreamManager.create(
                    config_file="test.json", servers=["server1", "server2"], transport_type="stdio"
                )

                await manager.close()

                # Check that close was called on all transports
                assert mock_transport.close.call_count == 2

    @pytest.mark.asyncio
    async def test_initialization_error(self):
        """Test StreamManager initialization failure."""
        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport") as mock_transport_cls:
            # Mock transport initialization failure
            mock_transport_cls.return_value.initialize = AsyncMock(return_value=False)

            # This should not raise, but log errors
            manager = await StreamManager.create(
                config_file="test.json", servers=["failing_server"], transport_type="stdio"
            )

            # Verify server wasn't added due to initialization failure
            assert "failing_server" not in manager.transports
            assert len(manager.server_info) == 0

    @pytest.mark.asyncio
    async def test_server_down(self):
        """Test StreamManager with server that's down."""
        mock_transport = Mock(spec=MCPBaseTransport)
        mock_transport.initialize = AsyncMock(return_value=True)
        mock_transport.send_ping = AsyncMock(return_value=False)  # Server down
        mock_transport.get_tools = AsyncMock(return_value=[])
        mock_transport.close = AsyncMock()

        with patch("chuk_tool_processor.mcp.stream_manager.StdioTransport", return_value=mock_transport):
            # Mock load_config to avoid file error
            with patch(
                "chuk_tool_processor.mcp.stream_manager.load_config", AsyncMock(return_value={"config": "test"})
            ):
                manager = await StreamManager.create(
                    config_file="test.json", servers=["down_server"], transport_type="stdio"
                )

                # Server should be marked as down in info
                server_info = manager.get_server_info()
                assert len(server_info) == 1
                assert server_info[0]["status"] == "Down"
