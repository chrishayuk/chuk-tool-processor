#!/usr/bin/env python
# tests/mcp/test_models.py
"""Tests for MCP models (MCPServerConfig)."""

import pytest
from pydantic import ValidationError

from chuk_tool_processor.mcp.models import MCPServerConfig, MCPTransport


class TestMCPTransport:
    """Test MCPTransport enum."""

    def test_transport_types(self):
        """Test all transport types exist."""
        assert MCPTransport.STDIO == "stdio"
        assert MCPTransport.SSE == "sse"
        assert MCPTransport.HTTP == "http"


class TestMCPServerConfig:
    """Test MCPServerConfig model."""

    # ------------------------------------------------------------------ #
    # STDIO tests
    # ------------------------------------------------------------------ #

    def test_stdio_config_valid(self):
        """Test valid STDIO configuration."""
        config = MCPServerConfig(
            name="test-stdio",
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "mcp_server"],
        )
        assert config.name == "test-stdio"
        assert config.transport == MCPTransport.STDIO
        assert config.command == "python"
        assert config.args == ["-m", "mcp_server"]

    def test_stdio_config_missing_command(self):
        """Test STDIO config without command raises error."""
        with pytest.raises(ValidationError, match="command is required"):
            MCPServerConfig(
                name="test-stdio",
                transport=MCPTransport.STDIO,
            )

    def test_stdio_config_with_env(self):
        """Test STDIO config with environment variables."""
        config = MCPServerConfig(
            name="test-stdio",
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "mcp_server"],
            env={"FOO": "bar", "BAZ": "qux"},
        )
        assert config.env == {"FOO": "bar", "BAZ": "qux"}

    def test_stdio_to_dict(self):
        """Test STDIO config to_dict() conversion."""
        config = MCPServerConfig(
            name="test-stdio",
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "mcp_server"],
        )
        result = config.to_dict()
        assert result == {
            "name": "test-stdio",
            "command": "python",
            "args": ["-m", "mcp_server"],
        }

    def test_stdio_to_dict_with_env(self):
        """Test STDIO config to_dict() with environment variables."""
        config = MCPServerConfig(
            name="test-stdio",
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "mcp_server"],
            env={"PATH": "/usr/bin"},
        )
        result = config.to_dict()
        assert result == {
            "name": "test-stdio",
            "command": "python",
            "args": ["-m", "mcp_server"],
            "env": {"PATH": "/usr/bin"},
        }

    # ------------------------------------------------------------------ #
    # SSE tests
    # ------------------------------------------------------------------ #

    def test_sse_config_valid(self):
        """Test valid SSE configuration."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
        )
        assert config.name == "test-sse"
        assert config.transport == MCPTransport.SSE
        assert config.url == "http://localhost:8000/sse"
        assert config.timeout == 10.0
        assert config.sse_read_timeout == 300.0

    def test_sse_config_missing_url(self):
        """Test SSE config without URL raises error."""
        with pytest.raises(ValidationError, match="url is required"):
            MCPServerConfig(
                name="test-sse",
                transport=MCPTransport.SSE,
            )

    def test_sse_config_with_headers(self):
        """Test SSE config with headers."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
            headers={"X-Custom": "value"},
        )
        assert config.headers == {"X-Custom": "value"}

    def test_sse_config_extracts_api_key_from_auth_header(self):
        """Test SSE config extracts API key from Authorization header."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
            headers={"Authorization": "Bearer test-api-key-123"},
        )
        assert config.api_key == "test-api-key-123"

    def test_sse_config_no_api_key_extraction_without_bearer(self):
        """Test SSE config doesn't extract API key without Bearer prefix."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
            headers={"Authorization": "Basic test-credentials"},
        )
        assert config.api_key is None

    def test_sse_to_dict(self):
        """Test SSE config to_dict() conversion."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
            headers={"X-Custom": "value"},
        )
        result = config.to_dict()
        assert result == {
            "name": "test-sse",
            "url": "http://localhost:8000/sse",
            "headers": {"X-Custom": "value"},
            "timeout": 10.0,
            "sse_read_timeout": 300.0,
        }

    def test_sse_to_dict_with_api_key(self):
        """Test SSE config to_dict() includes API key when set."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000/sse",
            api_key="explicit-key-123",
        )
        result = config.to_dict()
        assert "api_key" in result
        assert result["api_key"] == "explicit-key-123"

    # ------------------------------------------------------------------ #
    # HTTP tests
    # ------------------------------------------------------------------ #

    def test_http_config_valid(self):
        """Test valid HTTP configuration."""
        config = MCPServerConfig(
            name="test-http",
            transport=MCPTransport.HTTP,
            url="http://localhost:8000/api",
        )
        assert config.name == "test-http"
        assert config.transport == MCPTransport.HTTP
        assert config.url == "http://localhost:8000/api"

    def test_http_config_missing_url(self):
        """Test HTTP config without URL raises error."""
        with pytest.raises(ValidationError, match="url is required"):
            MCPServerConfig(
                name="test-http",
                transport=MCPTransport.HTTP,
            )

    def test_http_config_with_session_id(self):
        """Test HTTP config with session ID."""
        config = MCPServerConfig(
            name="test-http",
            transport=MCPTransport.HTTP,
            url="http://localhost:8000/api",
            session_id="session-123",
        )
        assert config.session_id == "session-123"

    def test_http_to_dict(self):
        """Test HTTP config to_dict() conversion."""
        config = MCPServerConfig(
            name="test-http",
            transport=MCPTransport.HTTP,
            url="http://localhost:8000/api",
            headers={"X-API-Key": "key"},
        )
        result = config.to_dict()
        assert result == {
            "name": "test-http",
            "url": "http://localhost:8000/api",
            "headers": {"X-API-Key": "key"},
            "timeout": 10.0,
        }
        # HTTP should NOT include sse_read_timeout
        assert "sse_read_timeout" not in result

    def test_http_to_dict_with_session_id(self):
        """Test HTTP config to_dict() includes session ID when set."""
        config = MCPServerConfig(
            name="test-http",
            transport=MCPTransport.HTTP,
            url="http://localhost:8000/api",
            session_id="session-456",
        )
        result = config.to_dict()
        assert "session_id" in result
        assert result["session_id"] == "session-456"

    def test_http_to_dict_with_api_key(self):
        """Test HTTP config to_dict() includes API key when set."""
        config = MCPServerConfig(
            name="test-http",
            transport=MCPTransport.HTTP,
            url="http://localhost:8000/api",
            headers={"Authorization": "Bearer my-key-789"},
        )
        result = config.to_dict()
        assert "api_key" in result
        assert result["api_key"] == "my-key-789"

    # ------------------------------------------------------------------ #
    # Edge cases
    # ------------------------------------------------------------------ #

    def test_default_transport_is_stdio(self):
        """Test default transport type is STDIO."""
        config = MCPServerConfig(
            name="test",
            command="python",
        )
        assert config.transport == MCPTransport.STDIO

    def test_custom_timeout_values(self):
        """Test custom timeout values."""
        config = MCPServerConfig(
            name="test-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:8000",
            timeout=20.0,
            sse_read_timeout=600.0,
        )
        assert config.timeout == 20.0
        assert config.sse_read_timeout == 600.0
