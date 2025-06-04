# tests/mcp/test_register_mcp_tools.py
import pytest
from unittest.mock import Mock, patch, AsyncMock

from chuk_tool_processor.mcp.register_mcp_tools import register_mcp_tools
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class TestRegisterMCPTools:
    """Tests for async‐native MCP-tool registration."""

    # ------------------------------------------------------------------ #
    # fixtures                                                           #
    # ------------------------------------------------------------------ #
    @pytest.fixture
    def mock_registry(self):
        reg = Mock(spec=ToolRegistryInterface)
        reg.register_tool = AsyncMock()         # async in real impl
        return reg

    @pytest.fixture
    def mock_stream_manager(self):
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {"name": "echo", "description": "Echo tool", "inputSchema": {}},
                {"name": "calc", "description": "Calculator", "inputSchema": {}},
            ]
        )
        return mgr

    # ------------------------------------------------------------------ #
    # helpers                                                            #
    # ------------------------------------------------------------------ #
    def _patch_registry(self, mock_registry):
        """
        Convenience wrapper - returns a context-manager that replaces
        ``ToolRegistryProvider.get_registry`` with an *async* mock.
        """
        return patch(
            "chuk_tool_processor.mcp.register_mcp_tools.ToolRegistryProvider.get_registry",
            new=AsyncMock(return_value=mock_registry),
        )

    # ------------------------------------------------------------------ #
    # happy-path                                                         #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_register_tools(self, mock_registry, mock_stream_manager):
        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mock_stream_manager, namespace="mcp")

        assert registered == ["echo", "calc"]

        # each tool ↦ two registrations (namespace + default)
        assert mock_registry.register_tool.call_count == 4
        names = [kwargs["name"] for _, kwargs in mock_registry.register_tool.call_args_list]
        assert {"echo", "mcp.echo", "calc", "mcp.calc"} <= set(names)

    # ------------------------------------------------------------------ #
    # edge-cases                                                         #
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_register_with_invalid_tool(self, mock_registry, mock_stream_manager):
        mock_stream_manager.get_all_tools.return_value = [
            {"description": "no name"},
            {"name": "", "description": "empty name"},
        ]
        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mock_stream_manager)

        assert registered == []
        mock_registry.register_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_tools_registration(self, mock_registry):
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(return_value=[])

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr)

        assert registered == []
        mock_registry.register_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_tool_names(self, mock_registry):
        mgr = Mock(spec=StreamManager)
        mgr.get_all_tools = Mock(
            return_value=[
                {"name": "echo", "description": "first"},
                {"name": "echo", "description": "second"},
            ]
        )

        with self._patch_registry(mock_registry):
            registered = await register_mcp_tools(mgr)

        # duplicates are kept in the return value
        assert registered == ["echo", "echo"]
        # still two physical tools → 4 registrations
        assert mock_registry.register_tool.call_count == 4
