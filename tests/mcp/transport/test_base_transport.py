# tests/mcp/transport/test_base_transport.py
"""
Tests for MCPBaseTransport abstract base class.
"""

import pytest

from chuk_tool_processor.mcp.transport.base_transport import MCPBaseTransport


class ConcreteTransport(MCPBaseTransport):
    """Concrete implementation for testing."""

    def __init__(self, fail_init=False):
        self._initialized = False
        self._fail_init = fail_init
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
        }
        self.enable_metrics = True

    async def initialize(self) -> bool:
        if self._fail_init:
            return False
        self._initialized = True
        return True

    async def close(self) -> None:
        self._initialized = False

    async def send_ping(self) -> bool:
        return self._initialized

    def is_connected(self) -> bool:
        return self._initialized

    async def get_tools(self) -> list[dict]:
        return [{"name": "test_tool"}]

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float | None = None) -> dict:
        return {"isError": False, "content": "success"}

    async def list_resources(self) -> dict:
        return {"resources": []}

    async def list_prompts(self) -> dict:
        return {"prompts": []}

    def get_metrics(self) -> dict:
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
        }


class TestMCPBaseTransport:
    """Test MCPBaseTransport abstract base class."""

    def test_get_streams_default(self):
        """Test default get_streams returns empty list."""
        transport = ConcreteTransport()
        assert transport.get_streams() == []

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        """Test context manager with successful initialization."""
        transport = ConcreteTransport()
        async with transport as t:
            assert t is transport
            assert t._initialized is True

        # Should be closed after exit
        assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_context_manager_failure(self):
        """Test context manager when initialization fails."""
        transport = ConcreteTransport(fail_init=True)

        with pytest.raises(RuntimeError, match="Failed to initialize ConcreteTransport"):
            async with transport:
                pass

    def test_normalize_mcp_response_with_error(self):
        """Test normalizing response with error field."""
        transport = ConcreteTransport()

        # Dict error with message
        response = {"error": {"message": "Test error", "code": 123}}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": True, "error": "Test error"}

        # String error
        response = {"error": "Simple error"}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": True, "error": "Simple error"}

    def test_normalize_mcp_response_with_result_content(self):
        """Test normalizing response with result containing content."""
        transport = ConcreteTransport()

        response = {"result": {"content": [{"type": "text", "text": "result"}]}}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": False, "content": "result"}

    def test_normalize_mcp_response_with_result_direct(self):
        """Test normalizing response with direct result."""
        transport = ConcreteTransport()

        response = {"result": {"data": "value"}}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": False, "content": {"data": "value"}}

    def test_normalize_mcp_response_with_direct_content(self):
        """Test normalizing response with direct content field."""
        transport = ConcreteTransport()

        response = {"content": [{"type": "text", "text": "direct"}]}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": False, "content": "direct"}

    def test_normalize_mcp_response_fallback(self):
        """Test normalizing response with no standard fields."""
        transport = ConcreteTransport()

        response = {"custom": "data"}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": False, "content": {"custom": "data"}}

    def test_extract_mcp_content_empty_list(self):
        """Test extracting content from empty list."""
        transport = ConcreteTransport()

        assert transport._extract_mcp_content([]) == []
        assert transport._extract_mcp_content(None) is None
        assert transport._extract_mcp_content("string") == "string"

    def test_extract_mcp_content_single_text_plain(self):
        """Test extracting plain text content."""
        transport = ConcreteTransport()

        content = [{"type": "text", "text": "plain text"}]
        result = transport._extract_mcp_content(content)
        assert result == "plain text"

    def test_extract_mcp_content_single_text_json(self):
        """Test extracting JSON text content."""
        transport = ConcreteTransport()

        content = [{"type": "text", "text": '{"key": "value"}'}]
        result = transport._extract_mcp_content(content)
        assert result == {"key": "value"}

    def test_extract_mcp_content_single_non_text(self):
        """Test extracting non-text content."""
        transport = ConcreteTransport()

        content = [{"type": "image", "data": "base64data"}]
        result = transport._extract_mcp_content(content)
        assert result == {"type": "image", "data": "base64data"}

    def test_extract_mcp_content_multiple_items(self):
        """Test extracting multiple content items."""
        transport = ConcreteTransport()

        content = [{"type": "text", "text": "item1"}, {"type": "text", "text": "item2"}]
        result = transport._extract_mcp_content(content)
        assert result == content

    def test_repr_not_initialized(self):
        """Test __repr__ when not initialized."""
        transport = ConcreteTransport()
        repr_str = repr(transport)
        assert "ConcreteTransport" in repr_str
        assert "status=not initialized" in repr_str

    @pytest.mark.asyncio
    async def test_repr_initialized(self):
        """Test __repr__ when initialized."""
        transport = ConcreteTransport()
        await transport.initialize()

        repr_str = repr(transport)
        assert "ConcreteTransport" in repr_str
        assert "status=initialized" in repr_str

    def test_repr_with_metrics(self):
        """Test __repr__ with metrics."""
        transport = ConcreteTransport()
        transport._initialized = True
        transport._metrics["total_calls"] = 10
        transport._metrics["successful_calls"] = 8

        repr_str = repr(transport)
        assert "calls: 10" in repr_str
        assert "success: 80.0%" in repr_str


class ConcreteTransportWithUrl(ConcreteTransport):
    """Concrete transport with URL for repr testing."""

    def __init__(self):
        super().__init__()
        self.url = "http://example.com"


class ConcreteTransportWithServerParams(ConcreteTransport):
    """Concrete transport with server params for repr testing."""

    def __init__(self):
        super().__init__()

        class ServerParams:
            command = "test_command"

        self.server_params = ServerParams()


class TestMCPBaseTransportRepr:
    """Test __repr__ with different transport configurations."""

    def test_repr_with_url(self):
        """Test __repr__ with URL."""
        transport = ConcreteTransportWithUrl()
        repr_str = repr(transport)
        assert "url=http://example.com" in repr_str

    def test_repr_with_server_params(self):
        """Test __repr__ with server params."""
        transport = ConcreteTransportWithServerParams()
        repr_str = repr(transport)
        assert "command=test_command" in repr_str

    def test_repr_with_metrics_disabled(self):
        """Test __repr__ when metrics are disabled."""
        transport = ConcreteTransport()
        transport.enable_metrics = False
        transport._initialized = True

        repr_str = repr(transport)
        assert "calls:" not in repr_str
        assert "success:" not in repr_str


class IncompleteTransport(MCPBaseTransport):
    """Transport that only partially implements abstract methods."""

    async def initialize(self) -> bool:
        pass

    async def close(self) -> None:
        pass

    async def send_ping(self) -> bool:
        pass

    def is_connected(self) -> bool:
        pass

    async def get_tools(self) -> list[dict]:
        pass

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float | None = None) -> dict:
        pass

    async def list_resources(self) -> dict:
        pass

    async def list_prompts(self) -> dict:
        pass

    def get_metrics(self) -> dict:
        pass

    def reset_metrics(self) -> None:
        pass


class TestMCPBaseTransportAbstractMethods:
    """Test abstract method implementations."""

    @pytest.mark.asyncio
    async def test_abstract_methods_return_none(self):
        """Test that abstract method pass statements can be executed."""
        transport = IncompleteTransport()

        # Test all abstract methods
        result = await transport.initialize()
        assert result is None

        await transport.close()

        result = await transport.send_ping()
        assert result is None

        result = transport.is_connected()
        assert result is None

        result = await transport.get_tools()
        assert result is None

        result = await transport.call_tool("test", {})
        assert result is None

        result = await transport.list_resources()
        assert result is None

        result = await transport.list_prompts()
        assert result is None

        result = transport.get_metrics()
        assert result is None

        transport.reset_metrics()
        # reset_metrics has no return value


class TestMCPBaseTransportEdgeCases:
    """Test edge cases in response normalization."""

    def test_normalize_mcp_response_error_without_message(self):
        """Test normalizing error response without message field."""
        transport = ConcreteTransport()

        # Dict error without message
        response = {"error": {"code": 123}}
        normalized = transport._normalize_mcp_response(response)
        assert normalized == {"isError": True, "error": "Unknown error"}

    def test_extract_mcp_content_single_dict_without_type(self):
        """Test extracting content from dict without type field."""
        transport = ConcreteTransport()

        # Single item without type field
        content = [{"data": "value"}]
        result = transport._extract_mcp_content(content)
        assert result == {"data": "value"}


class TestMCPBaseTransportRecovery:
    """Test default _attempt_recovery() implementation."""

    @pytest.mark.asyncio
    async def test_attempt_recovery_success(self):
        """Test default recovery: close + reinitialize succeeds."""
        transport = ConcreteTransport()
        await transport.initialize()
        assert transport._initialized is True

        # Simulate a broken state then recover
        transport._initialized = False
        transport._fail_init = False
        result = await transport._attempt_recovery()

        assert result is True
        assert transport._initialized is True

    @pytest.mark.asyncio
    async def test_attempt_recovery_failure(self):
        """Test default recovery when reinitialize fails."""
        transport = ConcreteTransport(fail_init=True)

        result = await transport._attempt_recovery()

        assert result is False
        assert transport._initialized is False

    @pytest.mark.asyncio
    async def test_attempt_recovery_exception(self):
        """Test default recovery when close raises an exception."""
        transport = ConcreteTransport()
        await transport.initialize()

        # Make close raise an exception
        async def bad_close():
            raise RuntimeError("close exploded")

        transport.close = bad_close

        result = await transport._attempt_recovery()
        assert result is False
