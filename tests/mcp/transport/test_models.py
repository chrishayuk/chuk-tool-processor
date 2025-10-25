# tests/mcp/transport/test_models.py
"""
Tests for MCP transport models.
"""

import pytest
from pydantic import ValidationError

from chuk_tool_processor.mcp.transport.models import HeadersConfig, ServerInfo, TimeoutConfig, TransportMetrics


class TestTimeoutConfig:
    """Test TimeoutConfig model."""

    def test_default_values(self):
        """Test default timeout values."""
        config = TimeoutConfig()
        assert config.connect == 30.0
        assert config.operation == 30.0
        assert config.quick == 5.0
        assert config.shutdown == 2.0

    def test_custom_values(self):
        """Test custom timeout values."""
        config = TimeoutConfig(connect=60.0, operation=45.0, quick=10.0, shutdown=5.0)
        assert config.connect == 60.0
        assert config.operation == 45.0
        assert config.quick == 10.0
        assert config.shutdown == 5.0

    def test_partial_custom_values(self):
        """Test partial override of timeout values."""
        config = TimeoutConfig(connect=15.0)
        assert config.connect == 15.0
        assert config.operation == 30.0  # Default
        assert config.quick == 5.0  # Default
        assert config.shutdown == 2.0  # Default

    def test_pydantic_validation(self):
        """Test Pydantic validation of timeout values."""
        # Valid values
        config = TimeoutConfig(connect=1.0, operation=2.0, quick=0.5, shutdown=0.1)
        assert config.connect == 1.0

        # Invalid type should raise validation error
        with pytest.raises(ValidationError):
            TimeoutConfig(connect="invalid")


class TestTransportMetrics:
    """Test TransportMetrics model."""

    def test_default_values(self):
        """Test default metric values."""
        metrics = TransportMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.total_time == 0.0
        assert metrics.avg_response_time == 0.0
        assert metrics.last_ping_time is None
        assert metrics.initialization_time is None
        assert metrics.connection_resets == 0
        assert metrics.stream_errors == 0
        assert metrics.connection_errors == 0
        assert metrics.recovery_attempts == 0
        assert metrics.session_discoveries == 0

    def test_custom_values(self):
        """Test custom metric values."""
        metrics = TransportMetrics(
            total_calls=10,
            successful_calls=8,
            failed_calls=2,
            total_time=5.5,
            avg_response_time=0.55,
            last_ping_time=0.1,
            initialization_time=1.2,
            connection_resets=1,
            stream_errors=3,
            connection_errors=2,
            recovery_attempts=1,
            session_discoveries=1,
        )
        assert metrics.total_calls == 10
        assert metrics.successful_calls == 8
        assert metrics.failed_calls == 2
        assert metrics.total_time == 5.5
        assert metrics.avg_response_time == 0.55
        assert metrics.last_ping_time == 0.1
        assert metrics.initialization_time == 1.2
        assert metrics.connection_resets == 1
        assert metrics.stream_errors == 3
        assert metrics.connection_errors == 2
        assert metrics.recovery_attempts == 1
        assert metrics.session_discoveries == 1

    def test_validate_assignment(self):
        """Test that validate_assignment allows mutation."""
        metrics = TransportMetrics()
        # Should allow assignment after creation
        metrics.total_calls = 5
        metrics.successful_calls = 3
        metrics.failed_calls = 2
        assert metrics.total_calls == 5
        assert metrics.successful_calls == 3
        assert metrics.failed_calls == 2

    def test_to_dict(self):
        """Test to_dict conversion."""
        metrics = TransportMetrics(total_calls=5, successful_calls=3, failed_calls=2)
        result = metrics.to_dict()
        assert isinstance(result, dict)
        assert result["total_calls"] == 5
        assert result["successful_calls"] == 3
        assert result["failed_calls"] == 2
        assert "avg_response_time" in result
        assert "last_ping_time" in result

    def test_update_call_metrics_success(self):
        """Test update_call_metrics with successful call."""
        metrics = TransportMetrics()
        metrics.total_calls = 1  # Simulate one call already counted

        metrics.update_call_metrics(response_time=1.5, success=True)

        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0
        assert metrics.total_time == 1.5
        assert metrics.avg_response_time == 1.5  # 1.5 / 1

    def test_update_call_metrics_failure(self):
        """Test update_call_metrics with failed call."""
        metrics = TransportMetrics()
        metrics.total_calls = 1  # Simulate one call already counted

        metrics.update_call_metrics(response_time=2.0, success=False)

        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 1
        assert metrics.total_time == 2.0
        assert metrics.avg_response_time == 2.0  # 2.0 / 1

    def test_update_call_metrics_multiple_calls(self):
        """Test update_call_metrics with multiple calls."""
        metrics = TransportMetrics()

        # First call
        metrics.total_calls = 1
        metrics.update_call_metrics(response_time=1.0, success=True)

        # Second call
        metrics.total_calls = 2
        metrics.update_call_metrics(response_time=2.0, success=False)

        # Third call
        metrics.total_calls = 3
        metrics.update_call_metrics(response_time=3.0, success=True)

        assert metrics.successful_calls == 2
        assert metrics.failed_calls == 1
        assert metrics.total_time == 6.0
        assert metrics.avg_response_time == 2.0  # 6.0 / 3

    def test_update_call_metrics_zero_total_calls(self):
        """Test update_call_metrics with zero total_calls."""
        metrics = TransportMetrics()
        metrics.total_calls = 0

        metrics.update_call_metrics(response_time=1.5, success=True)

        assert metrics.successful_calls == 1
        assert metrics.total_time == 1.5
        # avg_response_time should not be updated when total_calls is 0
        assert metrics.avg_response_time == 0.0


class TestServerInfo:
    """Test ServerInfo model."""

    def test_creation(self):
        """Test creating ServerInfo instance."""
        server = ServerInfo(id=1, name="test-server", tools=5, status="Up")
        assert server.id == 1
        assert server.name == "test-server"
        assert server.tools == 5
        assert server.status == "Up"

    def test_to_dict(self):
        """Test to_dict conversion."""
        server = ServerInfo(id=2, name="my-server", tools=10, status="Down")
        result = server.to_dict()
        assert isinstance(result, dict)
        assert result["id"] == 2
        assert result["name"] == "my-server"
        assert result["tools"] == 10
        assert result["status"] == "Down"

    def test_required_fields(self):
        """Test that all fields are required."""
        with pytest.raises(ValidationError):
            ServerInfo()

        with pytest.raises(ValidationError):
            ServerInfo(id=1, name="test")


class TestHeadersConfig:
    """Test HeadersConfig model."""

    def test_default_empty_headers(self):
        """Test default empty headers."""
        config = HeadersConfig()
        assert config.headers == {}

    def test_custom_headers(self):
        """Test custom headers."""
        headers = {"Authorization": "Bearer token", "X-Custom": "value"}
        config = HeadersConfig(headers=headers)
        assert config.headers == headers

    def test_get_headers(self):
        """Test get_headers returns a copy."""
        headers = {"Authorization": "Bearer token"}
        config = HeadersConfig(headers=headers)

        result = config.get_headers()
        assert result == headers

        # Modifying the result should not affect the original
        result["New-Header"] = "value"
        assert "New-Header" not in config.headers

    def test_update_headers(self):
        """Test update_headers method."""
        config = HeadersConfig(headers={"Original": "value"})

        config.update_headers({"New-Header": "new-value", "Another": "test"})

        assert config.headers["Original"] == "value"
        assert config.headers["New-Header"] == "new-value"
        assert config.headers["Another"] == "test"

    def test_update_headers_override(self):
        """Test update_headers overrides existing values."""
        config = HeadersConfig(headers={"Authorization": "old-token"})

        config.update_headers({"Authorization": "new-token"})

        assert config.headers["Authorization"] == "new-token"

    def test_has_authorization_true(self):
        """Test has_authorization when Authorization header is present."""
        config = HeadersConfig(headers={"Authorization": "Bearer token"})
        assert config.has_authorization() is True

    def test_has_authorization_false(self):
        """Test has_authorization when Authorization header is absent."""
        config = HeadersConfig(headers={"X-Custom": "value"})
        assert config.has_authorization() is False

    def test_has_authorization_empty(self):
        """Test has_authorization with empty headers."""
        config = HeadersConfig()
        assert config.has_authorization() is False

    def test_to_dict(self):
        """Test to_dict conversion."""
        headers = {"Authorization": "Bearer token", "X-Custom": "value"}
        config = HeadersConfig(headers=headers)

        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["headers"] == headers
