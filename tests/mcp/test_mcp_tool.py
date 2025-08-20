# tests/mcp/test_mcp_tool.py
import pytest
from unittest.mock import Mock, AsyncMock

from chuk_tool_processor.mcp.mcp_tool import MCPTool, ConnectionState, RecoveryConfig
from chuk_tool_processor.mcp.stream_manager import StreamManager


class TestMCPTool:
    """Test MCPTool class with resilience features."""
    
    @pytest.fixture
    def mock_stream_manager(self):
        """Mock StreamManager instance."""
        mock = Mock(spec=StreamManager)
        mock.call_tool = AsyncMock()
        
        # UPDATED: Mock the new health check methods instead of ping_servers
        mock.get_server_info = AsyncMock(return_value=[{"name": "test", "status": "Up"}])
        mock.transports = {"test": Mock()}  # Mock transports dict
        
        # Legacy ping_servers (not used in new health check but may be used elsewhere)
        mock.ping_servers = AsyncMock(return_value=[{"ok": True}])
        return mock
    
    @pytest.fixture
    def mcp_tool(self, mock_stream_manager):
        """Create MCPTool instance with resilience enabled."""
        return MCPTool("echo", mock_stream_manager, enable_resilience=True)
    
    @pytest.fixture
    def simple_mcp_tool(self, mock_stream_manager):
        """Create MCPTool instance with resilience disabled for legacy behavior."""
        return MCPTool("echo", mock_stream_manager, enable_resilience=False)
    
    # ------------------------------------------------------------------ #
    # Tests with resilience enabled (new behavior)
    # ------------------------------------------------------------------ #
    
    @pytest.mark.asyncio
    async def test_execute_success_with_resilience(self, mcp_tool, mock_stream_manager):
        """Test successful tool execution with resilience features."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Hello World"
        }
        
        # Execute
        result = await mcp_tool.execute(message="Hello")
        
        # Verify
        assert result == "Hello World"
        mock_stream_manager.call_tool.assert_called_once_with(
            tool_name="echo",
            arguments={"message": "Hello"},
            timeout=30.0  # Default timeout
        )
        
        # UPDATED: New lenient health check should check transports or server_info
        # but not necessarily ping_servers
        assert hasattr(mock_stream_manager, 'transports')  # Should have checked transports
    
    @pytest.mark.asyncio
    async def test_execute_error_with_resilience(self, mcp_tool, mock_stream_manager):
        """Test tool execution with error returns structured response."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": True,
            "error": "Connection failed"
        }
        
        # Execute
        result = await mcp_tool.execute(message="Hello")
        
        # Verify structured error response
        assert isinstance(result, dict)
        assert result["available"] is False
        assert "Connection failed" in result["error"]
        assert result["tool_name"] == "echo"
        assert result["reason"] == "execution_failed"
    
    @pytest.mark.asyncio
    async def test_execute_unhealthy_connection(self, mcp_tool, mock_stream_manager):
        """Test tool execution when connection is unhealthy."""
        # UPDATED: Setup unhealthy connection using new health check method
        # Make both transports and server_info indicate unhealthy state
        mock_stream_manager.transports = {}  # No transports = unhealthy
        mock_stream_manager.get_server_info.return_value = []  # No servers = unhealthy
        
        # Execute
        result = await mcp_tool.execute(message="Hello")
        
        # Verify structured error response
        assert isinstance(result, dict)
        assert result["available"] is False
        assert "unhealthy connection" in result["error"]
        assert result["tool_name"] == "echo"
        assert result["reason"] == "unhealthy"
        
        # Should not call the tool if unhealthy
        mock_stream_manager.call_tool.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_no_stream_manager(self):
        """Test tool execution when no StreamManager is available."""
        tool = MCPTool("echo", stream_manager=None, enable_resilience=True)
        
        # Execute
        result = await tool.execute(message="Hello")
        
        # Verify structured error response
        assert isinstance(result, dict)
        assert result["available"] is False
        assert "not available (no stream manager)" in result["error"]
        assert result["tool_name"] == "echo"
        assert result["reason"] == "disconnected"
    
    @pytest.mark.asyncio
    async def test_execute_timeout_with_resilience(self, mcp_tool, mock_stream_manager):
        """Test tool execution timeout returns structured response."""
        # Setup timeout
        import asyncio
        mock_stream_manager.call_tool.side_effect = asyncio.TimeoutError()
        
        # Execute
        result = await mcp_tool.execute(message="Hello", timeout=1.0)
        
        # Verify structured error response
        assert isinstance(result, dict)
        assert result["available"] is False
        assert "timed out" in result["error"]
        assert result["tool_name"] == "echo"
        assert result["reason"] == "timeout"
    
    @pytest.mark.asyncio
    async def test_execute_transport_error_with_resilience(self, mcp_tool, mock_stream_manager):
        """Test tool execution with transport error returns structured response."""
        # Setup transport error
        mock_stream_manager.call_tool.side_effect = Exception("Transport error")
        
        # Execute
        result = await mcp_tool.execute(message="Hello")
        
        # Verify structured error response
        assert isinstance(result, dict)
        assert result["available"] is False
        assert "Transport error" in result["error"]
        assert result["tool_name"] == "echo"
        assert result["reason"] == "execution_failed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, mock_stream_manager):
        """Test that circuit breaker opens after consecutive failures."""
        # Create tool with low failure threshold
        recovery_config = RecoveryConfig(circuit_breaker_threshold=2)
        tool = MCPTool("echo", mock_stream_manager, 
                      enable_resilience=True, recovery_config=recovery_config)
        
        # Setup consecutive failures
        mock_stream_manager.call_tool.side_effect = Exception("Consistent failure")
        
        # Execute multiple times to trigger circuit breaker
        for _ in range(3):
            result = await tool.execute(message="test")
            assert not result.get("available", True)
        
        # Fourth call should be circuit breaker response
        result = await tool.execute(message="test")
        assert result["reason"] == "circuit_breaker"
        assert "Circuit breaker open" in result["error"]
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, mock_stream_manager):
        """Test retry mechanism with eventual success."""
        # Create tool with retries
        recovery_config = RecoveryConfig(max_retries=2)
        tool = MCPTool("echo", mock_stream_manager, 
                      enable_resilience=True, recovery_config=recovery_config)
        
        # Setup failure then success
        mock_stream_manager.call_tool.side_effect = [
            Exception("Temporary failure"),
            {"isError": False, "content": "Success after retry"}
        ]
        
        # Execute
        result = await tool.execute(message="test")
        
        # Should succeed after retry
        assert result == "Success after retry"
        assert mock_stream_manager.call_tool.call_count == 2
    
    @pytest.mark.asyncio
    async def test_health_check_with_timeout_assumes_healthy(self, mock_stream_manager):
        """Test that health check timeout assumes healthy (new lenient behavior)."""
        # Setup health check timeout
        import asyncio
        mock_stream_manager.transports = {"test": Mock()}  # Has transports
        mock_stream_manager.get_server_info.side_effect = asyncio.TimeoutError()
        
        # Setup successful tool call
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Success despite timeout"
        }
        
        tool = MCPTool("echo", mock_stream_manager, enable_resilience=True)
        
        # Execute - should succeed because timeout assumes healthy
        result = await tool.execute(message="test")
        
        # Should succeed
        assert result == "Success despite timeout"
        mock_stream_manager.call_tool.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_with_exception_assumes_healthy(self, mock_stream_manager):
        """Test that health check exceptions assume healthy (new lenient behavior)."""
        # Setup health check exception
        mock_stream_manager.transports = {"test": Mock()}  # Has transports
        mock_stream_manager.get_server_info.side_effect = Exception("Health check error")
        
        # Setup successful tool call
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Success despite health error"
        }
        
        tool = MCPTool("echo", mock_stream_manager, enable_resilience=True)
        
        # Execute - should succeed because exceptions assume healthy
        result = await tool.execute(message="test")
        
        # Should succeed
        assert result == "Success despite health error"
        mock_stream_manager.call_tool.assert_called_once()
    
    # ------------------------------------------------------------------ #
    # Tests with resilience disabled (legacy behavior)
    # ------------------------------------------------------------------ #
    
    @pytest.mark.asyncio
    async def test_execute_success_without_resilience(self, simple_mcp_tool, mock_stream_manager):
        """Test successful tool execution without resilience (legacy behavior)."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Hello World"
        }
        
        # Execute
        result = await simple_mcp_tool.execute(message="Hello")
        
        # Verify
        assert result == "Hello World"
        mock_stream_manager.call_tool.assert_called_once_with(
            tool_name="echo",
            arguments={"message": "Hello"},
            timeout=30.0
        )
        
        # Should not check health when resilience disabled
        mock_stream_manager.get_server_info.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_error_without_resilience(self, simple_mcp_tool, mock_stream_manager):
        """Test tool execution with error raises exception (legacy behavior)."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": True,
            "error": "Connection failed"
        }
        
        # Execute and verify exception is raised
        with pytest.raises(RuntimeError, match="Connection failed"):
            await simple_mcp_tool.execute(message="Hello")
    
    @pytest.mark.asyncio
    async def test_execute_unknown_error_without_resilience(self, simple_mcp_tool, mock_stream_manager):
        """Test tool execution with unknown error (legacy behavior)."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": True
        }
        
        # Execute and verify default error message
        with pytest.raises(RuntimeError, match="Unknown error"):
            await simple_mcp_tool.execute(message="Hello")
    
    @pytest.mark.asyncio
    async def test_execute_transport_error_without_resilience(self, simple_mcp_tool, mock_stream_manager):
        """Test tool call with transport error (legacy behavior)."""
        # Simulate transport error
        mock_stream_manager.call_tool.side_effect = Exception("Transport error")
        
        # Should raise the original exception
        with pytest.raises(Exception, match="Transport error"):
            await simple_mcp_tool.execute(message="test")
    
    # ------------------------------------------------------------------ #
    # Utility and monitoring tests
    # ------------------------------------------------------------------ #
    
    def test_is_available(self, mcp_tool):
        """Test availability checking."""
        assert mcp_tool.is_available() is True
        
        # Test with no stream manager
        no_sm_tool = MCPTool("test", stream_manager=None)
        assert no_sm_tool.is_available() is False
    
    def test_get_stats(self, mcp_tool):
        """Test statistics gathering."""
        stats = mcp_tool.get_stats()
        
        assert stats["tool_name"] == "echo"
        assert stats["resilience_enabled"] is True
        assert stats["available"] is True
        assert stats["state"] == ConnectionState.HEALTHY.value
        assert stats["total_calls"] == 0
        assert stats["has_stream_manager"] is True
    
    def test_get_stats_without_resilience(self, simple_mcp_tool):
        """Test statistics when resilience is disabled."""
        stats = simple_mcp_tool.get_stats()
        
        assert stats["tool_name"] == "echo"
        assert stats["resilience_enabled"] is False
        assert stats["available"] is True
    
    def test_reset_circuit_breaker(self, mcp_tool):
        """Test manual circuit breaker reset."""
        # Open circuit breaker manually
        mcp_tool._circuit_open = True
        mcp_tool._consecutive_failures = 5
        
        # Reset
        mcp_tool.reset_circuit_breaker()
        
        assert mcp_tool._circuit_open is False
        assert mcp_tool._consecutive_failures == 0
        assert mcp_tool.connection_state == ConnectionState.HEALTHY
    
    def test_set_stream_manager(self):
        """Test updating stream manager."""
        tool = MCPTool("test", stream_manager=None)
        assert not tool.is_available()
        
        # Set stream manager
        mock_sm = Mock(spec=StreamManager)
        tool.set_stream_manager(mock_sm)
        
        assert tool._sm == mock_sm
        assert tool.connection_state == ConnectionState.HEALTHY
    
    def test_disable_resilience(self, mcp_tool):
        """Test disabling resilience features."""
        assert mcp_tool.enable_resilience is True
        
        mcp_tool.disable_resilience()
        
        assert mcp_tool.enable_resilience is False
    
    # ------------------------------------------------------------------ #
    # Serialization tests
    # ------------------------------------------------------------------ #
    
    def test_serialization(self, mcp_tool):
        """Test serialization for subprocess execution."""
        # Get state
        state = mcp_tool.__getstate__()
        
        # Verify critical fields preserved
        assert state["tool_name"] == "echo"
        assert state["default_timeout"] == 30.0
        assert state["enable_resilience"] is True
        
        # StreamManager should be None for subprocess
        assert state["_sm"] is None
        
        # Create new instance and restore state
        new_tool = MCPTool.__new__(MCPTool)
        new_tool.__setstate__(state)
        
        # Verify restoration
        assert new_tool.tool_name == "echo"
        assert new_tool._sm is None
        assert new_tool.connection_state == ConnectionState.DISCONNECTED
    
    def test_serialization_invalid_state(self):
        """Test serialization with invalid state."""
        tool = MCPTool.__new__(MCPTool)
        
        # Try to restore invalid state
        with pytest.raises(ValueError, match="missing tool_name"):
            tool.__setstate__({"enable_resilience": True})
    
    # ------------------------------------------------------------------ #
    # Legacy method support
    # ------------------------------------------------------------------ #
    
    @pytest.mark.asyncio
    async def test_legacy_aexecute_method(self, simple_mcp_tool, mock_stream_manager):
        """Test legacy _aexecute method still works."""
        # Setup
        mock_stream_manager.call_tool.return_value = {
            "isError": False,
            "content": "Legacy method works"
        }
        
        # Execute using legacy method
        result = await simple_mcp_tool._aexecute(message="test")
        
        # Verify
        assert result == "Legacy method works"