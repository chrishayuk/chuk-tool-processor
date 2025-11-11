# tests/mcp/test_setup_mcp_stdio.py
from unittest.mock import AsyncMock, Mock, patch

import pytest

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.mcp.models import MCPConfig, MCPServerConfig, MCPTransport
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

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor),
        ):
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
        with (
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create", AsyncMock()),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools"),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor") as mock_processor_class,
        ):
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

    @pytest.mark.asyncio
    async def test_setup_with_server_names_list_missing_config_file(self):
        """Test setup with server names list but no config_file raises error."""
        with pytest.raises(ValueError, match="config_file is required when servers is a list of strings"):
            await setup_mcp_stdio(
                servers=["echo", "calc"],  # List of strings without config_file
                namespace="mcp",
            )

    @pytest.mark.asyncio
    async def test_setup_with_server_dicts(self):
        """Test setup with server configuration dicts (new DX)."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo"]

        server_dicts = [
            {"name": "echo", "command": "uvx", "args": ["chuk-mcp-echo", "stdio"]},
        ]

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create_with_stdio",
                AsyncMock(return_value=mock_stream_manager),
            ) as mock_create_stdio,
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor),
        ):
            processor, stream_manager = await setup_mcp_stdio(
                servers=server_dicts,
                namespace="mcp",
            )

            assert processor == mock_processor
            assert stream_manager == mock_stream_manager
            mock_create_stdio.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_with_pydantic_models(self):
        """Test setup with MCPServerConfig Pydantic models (best DX)."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo"]

        # Create Pydantic model config
        server_configs = [
            MCPServerConfig(
                name="echo",
                transport=MCPTransport.STDIO,
                command="uvx",
                args=["chuk-mcp-echo", "stdio"],
            ),
        ]

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create_with_stdio",
                AsyncMock(return_value=mock_stream_manager),
            ) as mock_create_stdio,
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor),
        ):
            processor, stream_manager = await setup_mcp_stdio(
                servers=server_configs,
                namespace="mcp",
            )

            assert processor == mock_processor
            assert stream_manager == mock_stream_manager

            # Verify create_with_stdio was called with converted dicts
            mock_create_stdio.assert_called_once()
            call_kwargs = mock_create_stdio.call_args.kwargs
            assert "servers" in call_kwargs
            # The servers should be converted from Pydantic models to dicts
            assert isinstance(call_kwargs["servers"], list)
            assert isinstance(call_kwargs["servers"][0], dict)

    @pytest.mark.asyncio
    async def test_setup_with_mcp_config(self):
        """Test setup with MCPConfig Pydantic model (NEW clean API)."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo"]

        # Create MCPConfig with all settings
        config = MCPConfig(
            servers=[
                MCPServerConfig(
                    name="echo",
                    command="uvx",
                    args=["chuk-mcp-echo", "stdio"],
                ),
            ],
            namespace="tools",
            default_timeout=20.0,
            initialization_timeout=120.0,
            max_concurrency=10,
            enable_caching=True,
            cache_ttl=600,
            enable_rate_limiting=True,
            global_rate_limit=50,
            enable_retries=True,
            max_retries=5,
        )

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create_with_stdio",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools
            ) as mock_register,
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor
            ) as mock_processor_class,
        ):
            processor, stream_manager = await setup_mcp_stdio(config=config)

            assert processor == mock_processor
            assert stream_manager == mock_stream_manager

            # Verify register_mcp_tools was called with correct namespace
            mock_register.assert_called_once()
            assert mock_register.call_args.kwargs["namespace"] == "tools"

            # Verify ToolProcessor was created with MCPConfig settings
            mock_processor_class.assert_called_once()
            call_kwargs = mock_processor_class.call_args.kwargs
            assert call_kwargs["default_timeout"] == 20.0
            assert call_kwargs["max_concurrency"] == 10
            assert call_kwargs["enable_caching"] is True
            assert call_kwargs["cache_ttl"] == 600
            assert call_kwargs["enable_rate_limiting"] is True
            assert call_kwargs["global_rate_limit"] == 50
            assert call_kwargs["enable_retries"] is True
            assert call_kwargs["max_retries"] == 5

    @pytest.mark.asyncio
    async def test_setup_with_invalid_config_type(self):
        """Test setup with invalid config type raises TypeError."""
        with pytest.raises(TypeError, match="config must be an MCPConfig instance"):
            await setup_mcp_stdio(config={"invalid": "dict"})  # type: ignore

    @pytest.mark.asyncio
    async def test_setup_without_config_or_servers(self):
        """Test setup without config or servers raises ValueError."""
        with pytest.raises(ValueError, match="Either 'config' or 'servers' must be provided"):
            await setup_mcp_stdio()

    @pytest.mark.asyncio
    async def test_setup_with_mcp_config_with_config_file(self):
        """Test MCPConfig can include legacy config_file option."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo"]

        # MCPConfig with config_file set (legacy compatibility)
        config = MCPConfig(
            servers=[
                MCPServerConfig(
                    name="echo",
                    command="uvx",
                    args=["chuk-mcp-echo", "stdio"],
                ),
            ],
            config_file="legacy.json",  # This should be used
            namespace="mcp",
        )

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create_with_stdio",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools),
            patch("chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor),
        ):
            processor, stream_manager = await setup_mcp_stdio(config=config)

            assert processor == mock_processor
            assert stream_manager == mock_stream_manager

    @pytest.mark.asyncio
    async def test_setup_with_mcp_config_overrides_parameters(self):
        """Test MCPConfig overrides individual parameters when both provided."""
        mock_stream_manager = Mock(spec=StreamManager)
        mock_processor = Mock(spec=ToolProcessor)
        registered_tools = ["echo"]

        config = MCPConfig(
            servers=[
                MCPServerConfig(
                    name="echo",
                    command="uvx",
                    args=["chuk-mcp-echo", "stdio"],
                ),
            ],
            namespace="config_namespace",
            default_timeout=99.0,
        )

        with (
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.StreamManager.create_with_stdio",
                AsyncMock(return_value=mock_stream_manager),
            ),
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.register_mcp_tools", return_value=registered_tools
            ) as mock_register,
            patch(
                "chuk_tool_processor.mcp.setup_mcp_stdio.ToolProcessor", return_value=mock_processor
            ) as mock_processor_class,
        ):
            # Pass both config AND individual params - config should win
            processor, stream_manager = await setup_mcp_stdio(
                config=config,
                namespace="ignored_namespace",  # Should be overridden by config
                default_timeout=10.0,  # Should be overridden by config
            )

            # Verify config values were used, not the individual parameters
            mock_register.assert_called_once()
            assert mock_register.call_args.kwargs["namespace"] == "config_namespace"

            mock_processor_class.assert_called_once()
            call_kwargs = mock_processor_class.call_args.kwargs
            assert call_kwargs["default_timeout"] == 99.0
