# tests/mcp/transport/test_stdio_transport.py - FIXED METRICS TEST
"""
Tests for StdioTransport class with consistent interface.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from chuk_mcp.transports.stdio.parameters import StdioParameters

from chuk_tool_processor.mcp.transport.stdio_transport import StdioTransport


class TestStdioTransport:
    """Test StdioTransport class with consistent interface."""

    @pytest.fixture
    def transport(self):
        """Create StdioTransport instance with consistent parameters."""
        server_params = {"command": "python", "args": ["-m", "test_server"], "env": {"TEST": "true"}}
        return StdioTransport(server_params, connection_timeout=30.0, default_timeout=30.0, enable_metrics=True)

    @pytest.fixture
    def transport_no_metrics(self):
        """Create StdioTransport instance with metrics disabled."""
        server_params = {"command": "python", "args": ["-m", "test_server"]}
        return StdioTransport(server_params, enable_metrics=False)

    def test_init_with_dict_params(self, transport):
        """Test initialization with dictionary parameters."""
        assert isinstance(transport.server_params, StdioParameters)
        assert transport.server_params.command == "python"
        assert transport.server_params.args == ["-m", "test_server"]
        assert transport.enable_metrics is True
        assert transport.default_timeout == 30.0

    def test_init_with_stdio_parameters(self):
        """Test initialization with StdioParameters object."""
        params = StdioParameters(command="test", args=["arg1"])
        transport = StdioTransport(params)
        assert transport.server_params is params
        assert transport.enable_metrics is True  # default

    @pytest.mark.asyncio
    async def test_initialize_success(self, transport):
        """Test successful STDIO transport initialization with metrics tracking."""
        mock_context = AsyncMock()
        mock_streams = (Mock(), Mock())  # (read_stream, write_stream)

        with (
            patch("chuk_tool_processor.mcp.transport.stdio_transport.stdio_client", return_value=mock_context),
            patch("chuk_tool_processor.mcp.transport.stdio_transport.send_initialize", AsyncMock(return_value=True)),
        ):
            mock_context.__aenter__.return_value = mock_streams

            result = await transport.initialize()

            assert result is True
            assert transport._initialized is True
            assert transport._streams == mock_streams

            # Check metrics were updated
            metrics = transport.get_metrics()
            assert metrics["initialization_time"] >= 0  # May be 0 in mocked tests

    @pytest.mark.asyncio
    async def test_initialize_timeout(self, transport):
        """Test STDIO transport initialization timeout."""
        mock_context = AsyncMock()

        with patch("chuk_tool_processor.mcp.transport.stdio_transport.stdio_client", return_value=mock_context):
            # Simulate timeout during context entry
            mock_context.__aenter__.side_effect = TimeoutError()

            result = await transport.initialize()

            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_send_initialize_fails(self, transport):
        """Test STDIO transport initialization when send_initialize fails."""
        mock_context = AsyncMock()
        mock_streams = (Mock(), Mock())

        with (
            patch("chuk_tool_processor.mcp.transport.stdio_transport.stdio_client", return_value=mock_context),
            patch("chuk_tool_processor.mcp.transport.stdio_transport.send_initialize", AsyncMock(return_value=False)),
        ):
            mock_context.__aenter__.return_value = mock_streams

            result = await transport.initialize()

            assert result is False
            assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_send_ping_success(self, transport):
        """Test STDIO ping when initialized with metrics tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        with patch("chuk_tool_processor.mcp.transport.stdio_transport.send_ping", AsyncMock(return_value=True)):
            result = await transport.send_ping()
            assert result is True

            # Check ping metrics were updated
            metrics = transport.get_metrics()
            assert metrics["last_ping_time"] >= 0  # May be 0 in mocked tests

    @pytest.mark.asyncio
    async def test_send_ping_not_initialized(self, transport):
        """Test STDIO ping when not initialized."""
        assert transport._initialized is False
        result = await transport.send_ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_ping_exception(self, transport):
        """Test STDIO ping with exception and metrics tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_ping",
            AsyncMock(side_effect=Exception("Pipe error")),
        ):
            result = await transport.send_ping()
            assert result is False

            # Check pipe error metrics
            metrics = transport.get_metrics()
            assert metrics["pipe_errors"] == 1

    def test_is_connected(self, transport):
        """Test connection status check (consistent method)."""
        # not initialized
        assert transport.is_connected() is False
        # initialized
        transport._initialized = True
        transport._streams = (Mock(), Mock())
        assert transport.is_connected() is True
        # initialized but no streams
        transport._streams = None
        assert transport.is_connected() is False

    @pytest.mark.asyncio
    async def test_get_tools_success(self, transport):
        """Test STDIO get tools when initialized with performance tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        expected_tools = [{"name": "search"}, {"name": "research"}]

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_list",
            AsyncMock(return_value={"tools": expected_tools}),
        ):
            tools = await transport.get_tools()
            assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_tools_list_response(self, transport):
        """Test STDIO get tools when response is a list."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        expected_tools = [{"name": "search"}]

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_list", AsyncMock(return_value=expected_tools)
        ):
            tools = await transport.get_tools()
            assert tools == expected_tools

    @pytest.mark.asyncio
    async def test_get_tools_not_initialized(self, transport):
        """Test STDIO get tools when not initialized."""
        assert transport._initialized is False
        tools = await transport.get_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_call_tool_success(self, transport):
        """Test STDIO call tool when initialized with metrics tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        # Test the STDIO-specific string preservation behavior
        response = {"result": {"content": [{"type": "text", "text": "42"}]}}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call", AsyncMock(return_value=response)
        ):
            result = await transport.call_tool("search", {"query": "test"})
            assert result["isError"] is False
            assert result["content"] == "42"  # String preserved for STDIO

            # Check metrics were updated
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["successful_calls"] == 1
            assert metrics["avg_response_time"] >= 0  # May be 0 in mocked tests

    @pytest.mark.asyncio
    async def test_call_tool_with_timeout(self, transport):
        """Test STDIO call tool with custom timeout parameter."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        response = {"result": {"content": "success"}}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call", AsyncMock(return_value=response)
        ) as mock_send:
            result = await transport.call_tool("search", {"query": "test"}, timeout=15.0)
            assert result["isError"] is False

            # Verify the call was made with correct parameters
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self, transport):
        """Test STDIO call tool when not initialized."""
        assert transport._initialized is False
        result = await transport.call_tool("test", {})
        assert result["isError"] is True
        assert result["error"] == "Transport not initialized"

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self, transport):
        """Test STDIO call tool with timeout and metrics tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call",
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
        """Test STDIO call tool with exception and metrics tracking."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call",
            AsyncMock(side_effect=Exception("Pipe broken")),
        ):
            result = await transport.call_tool("search", {})
            assert result["isError"] is True
            assert "Pipe broken" in result["error"]

            # Check failure metrics including pipe error
            metrics = transport.get_metrics()
            assert metrics["total_calls"] == 1
            assert metrics["failed_calls"] == 1
            assert metrics["pipe_errors"] == 1

    @pytest.mark.asyncio
    async def test_metrics_functionality(self, transport):
        """Test metrics get and reset functionality - FIXED."""
        # Initial metrics
        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["successful_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["avg_response_time"] == 0.0
        assert metrics["pipe_errors"] == 0

        # FIXED: Simulate actual tool calls to test metrics
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        # Simulate successful call
        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call",
            AsyncMock(return_value={"result": {"content": "success"}}),
        ):
            await transport.call_tool("test", {})

        # Simulate failed call
        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_tools_call",
            AsyncMock(side_effect=Exception("error")),
        ):
            await transport.call_tool("test", {})

        metrics = transport.get_metrics()
        assert metrics["total_calls"] == 2
        assert metrics["successful_calls"] == 1
        assert metrics["failed_calls"] == 1
        assert metrics["avg_response_time"] >= 0  # May be 0 in mocked tests

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
        transport_no_metrics._streams = (Mock(), Mock())

        # Metrics should still be available but not actively updated during operations
        assert transport_no_metrics.enable_metrics is False
        metrics = transport_no_metrics.get_metrics()
        assert isinstance(metrics, dict)

    def test_stdio_specific_content_extraction(self, transport):
        """Test STDIO-specific content extraction with string preservation."""
        # Test numeric string preservation (STDIO-specific behavior)
        content = [{"type": "text", "text": "42"}]
        result = transport._extract_stdio_content(content)
        assert result == "42"  # Preserved as string

        # Test decimal string preservation
        content = [{"type": "text", "text": "3.14"}]
        result = transport._extract_stdio_content(content)
        assert result == "3.14"  # Preserved as string

        # Test JSON object parsing
        content = [{"type": "text", "text": '{"key": "value"}'}]
        result = transport._extract_stdio_content(content)
        assert result == {"key": "value"}  # Parsed as JSON

        # Test non-numeric string
        content = [{"type": "text", "text": "hello"}]
        result = transport._extract_stdio_content(content)
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_list_resources_success(self, transport):
        """Test listing resources when initialized."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        expected_resources = {"resources": [{"name": "resource1"}]}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_resources_list",
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
        transport._streams = (Mock(), Mock())

        expected_prompts = {"prompts": [{"name": "prompt1"}]}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_prompts_list",
            AsyncMock(return_value=expected_prompts),
        ):
            result = await transport.list_prompts()
            assert result == expected_prompts

    @pytest.mark.asyncio
    async def test_read_resource(self, transport):
        """Test reading a specific resource."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        expected_resource = {"content": "resource data"}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_resources_read",
            AsyncMock(return_value=expected_resource),
        ):
            result = await transport.read_resource("test://resource")
            assert result == expected_resource

    @pytest.mark.asyncio
    async def test_get_prompt(self, transport):
        """Test getting a specific prompt."""
        transport._initialized = True
        transport._streams = (Mock(), Mock())

        expected_prompt = {"messages": [{"role": "user", "content": "test"}]}

        with patch(
            "chuk_tool_processor.mcp.transport.stdio_transport.send_prompts_get",
            AsyncMock(return_value=expected_prompt),
        ):
            result = await transport.get_prompt("test_prompt", {"arg": "value"})
            assert result == expected_prompt

    @pytest.mark.asyncio
    async def test_close_success(self, transport):
        """Test STDIO close when initialized with metrics logging."""
        transport._initialized = True
        # Add some metrics to test logging
        transport._metrics["total_calls"] = 5
        transport._metrics["successful_calls"] = 4
        transport._metrics["failed_calls"] = 1

        mock_context = AsyncMock()
        transport._context = mock_context

        await transport.close()

        assert transport._initialized is False
        assert transport._context is None
        assert transport._streams is None
        mock_context.__aexit__.assert_called_once_with(None, None, None)

    @pytest.mark.asyncio
    async def test_close_no_context(self, transport):
        """Test STDIO close when no context exists."""
        transport._initialized = False
        await transport.close()
        assert transport._initialized is False

    def test_get_streams(self, transport):
        """Test getting streams for backward compatibility."""
        # No streams when not initialized
        assert transport.get_streams() == []

        # Streams available when initialized
        mock_streams = (Mock(), Mock())
        transport._streams = mock_streams
        assert transport.get_streams() == [mock_streams]

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
            pytest.raises(RuntimeError, match="Failed to initialize StdioTransport"),
        ):
            async with transport:
                pass

    def test_repr_consistent_format(self, transport):
        """Test string representation follows consistent format - FIXED."""
        # Not initialized
        repr_str = repr(transport)
        assert "StdioTransport" in repr_str
        assert "status=not initialized" in repr_str
        assert "command=python" in repr_str  # FIXED: Now matches expected format

        # Initialized with metrics
        transport._initialized = True
        transport._metrics["total_calls"] = 10
        transport._metrics["successful_calls"] = 8

        repr_str = repr(transport)
        assert "status=initialized" in repr_str
        assert "calls: 10" in repr_str
        assert "success: 80.0%" in repr_str
