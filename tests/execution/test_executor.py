# tests/execution/test_executor.py
"""
Unit tests for the ToolExecutor class.
"""
import asyncio
from typing import Dict, List, Any, Optional, AsyncIterator
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# Common Mock Registry for tests
class MockRegistry:
    """Mock registry that implements the async ToolRegistryInterface."""
    
    def __init__(self, tools: Dict[str, Any] = None):
        self._tools = tools or {}

    async def get_tool(self, name: str, namespace: str = "default") -> Optional[Any]:
        """Async version of get_tool to match the ToolRegistryInterface."""
        return self._tools.get(name)
        
    async def get_metadata(self, name: str, namespace: str = "default") -> Optional[Any]:
        """Mock metadata retrieval."""
        if name in self._tools:
            return {"description": f"Mock metadata for {name}", "supports_streaming": False}
        return None
        
    async def list_tools(self, namespace: Optional[str] = None) -> list:
        """Mock list_tools method."""
        return [(namespace or "default", name) for name in self._tools.keys()]
# --------------------------------------------------------------------------- #
# Mock execution strategies for testing
# --------------------------------------------------------------------------- #

class DummyStrategy(ExecutionStrategy):
    """
    Simple non-streaming execution strategy for testing.
    
    This strategy just returns successful results for all calls.
    """
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """Execute all calls and return success results."""
        return [
            ToolResult(
                tool=call.tool,
                result=f"Result for {call.tool}",
                error=None,
            )
            for call in calls
        ]
        
    @property
    def supports_streaming(self) -> bool:
        """This strategy doesn't support streaming."""
        return False


class StreamingStrategy(ExecutionStrategy):
    """
    Mock streaming execution strategy for testing.
    
    This strategy supports both run and stream_run methods.
    """
    
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """Execute all calls and return success results."""
        return [
            ToolResult(
                tool=call.tool,
                result=f"Result for {call.tool}",
                error=None,
            )
            for call in calls
        ]
        
    async def stream_run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> AsyncIterator[ToolResult]:
        """Stream results one by one."""
        for call in calls:
            yield ToolResult(
                tool=call.tool,
                result=f"Streamed result for {call.tool}",
                error=None,
            )
            await asyncio.sleep(0.01)  # Small delay for realism
            
    @property
    def supports_streaming(self) -> bool:
        """This strategy supports streaming."""
        return True


class ErrorStrategy(ExecutionStrategy):
    """
    Strategy that always returns errors for testing error handling.
    """
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """Execute all calls and return error results."""
        return [
            ToolResult(
                tool=call.tool,
                result=None,
                error=f"Error for {call.tool}",
            )
            for call in calls
        ]


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def registry():
    """Create an empty registry for testing."""
    return MockRegistry()


@pytest.fixture
def dummy_strategy():
    """Create a simple strategy that returns success results."""
    return DummyStrategy()


@pytest.fixture
def streaming_strategy():
    """Create a strategy that supports streaming."""
    return StreamingStrategy()


@pytest.fixture
def error_strategy():
    """Create a strategy that returns errors."""
    return ErrorStrategy()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_executor_initialization(registry):
    """Test that the executor initializes correctly."""
    # Test with explicit strategy
    strategy = DummyStrategy()
    executor = ToolExecutor(
        registry=registry,
        default_timeout=5.0,
        strategy=strategy
    )
    
    assert executor.registry == registry
    assert executor.default_timeout == 5.0
    assert executor.strategy == strategy
    
    # Test with strategy_kwargs
    with patch("chuk_tool_processor.execution.tool_executor._inprocess_mod.InProcessStrategy") as mock_strategy:
        mock_strategy.return_value = DummyStrategy()
        executor = ToolExecutor(
            registry=registry,
            default_timeout=10.0,
            strategy_kwargs={"max_concurrency": 3}
        )
        
        # Verify InProcessStrategy was called with the right args
        mock_strategy.assert_called_once()
        args, kwargs = mock_strategy.call_args
        assert kwargs["default_timeout"] == 10.0
        assert kwargs["max_concurrency"] == 3


@pytest.mark.asyncio
async def test_executor_with_empty_calls(registry, dummy_strategy):
    """Test that executor handles empty calls list properly."""
    executor = ToolExecutor(
        registry=registry,
        strategy=dummy_strategy
    )
    
    # Execute with empty list
    results = await executor.execute([])
    
    # Should return empty list, not None
    assert isinstance(results, list)
    assert len(results) == 0
    
    # Test streaming with empty list
    results = []
    async for result in executor.stream_execute([]):
        results.append(result)
        
    assert len(results) == 0


@pytest.mark.asyncio
async def test_executor_with_strategy_kwargs():
    """Test that strategy_kwargs are properly passed."""
    # Mock InProcessStrategy
    with patch("chuk_tool_processor.execution.tool_executor._inprocess_mod.InProcessStrategy") as mock_strategy:
        mock_strategy.return_value = DummyStrategy()
        
        # Create executor with strategy kwargs
        registry = MockRegistry()
        executor = ToolExecutor(
            registry=registry,
            default_timeout=1.0,
            strategy_kwargs={"max_concurrency": 5, "custom_option": "value"}
        )
        
        # Verify InProcessStrategy was called with the kwargs
        mock_strategy.assert_called_once()
        _, kwargs = mock_strategy.call_args
        assert kwargs.get("max_concurrency") == 5
        assert kwargs.get("custom_option") == "value"


@pytest.mark.asyncio
async def test_executor_execute(registry, dummy_strategy):
    """Test that execute method works correctly."""
    executor = ToolExecutor(
        registry=registry,
        strategy=dummy_strategy
    )
    
    # Create some test calls
    calls = [
        ToolCall(tool="tool1", arguments={"x": 1}),
        ToolCall(tool="tool2", arguments={"y": 2}),
    ]
    
    # Execute calls
    results = await executor.execute(calls)
    
    # Verify results
    assert len(results) == 2
    assert results[0].tool == "tool1"
    assert results[0].error is None
    assert results[0].result == "Result for tool1"
    assert results[1].tool == "tool2"
    assert results[1].error is None
    assert results[1].result == "Result for tool2"


@pytest.mark.asyncio
async def test_streaming_executor(registry, streaming_strategy):
    """Test that the executor supports streaming when strategy does."""
    executor = ToolExecutor(
        registry=registry,
        default_timeout=1.0,
        strategy=streaming_strategy
    )

    # Test supports_streaming property
    assert executor.supports_streaming is True
    
    # Test stream_execute method
    calls = [
        ToolCall(tool="tool1", arguments={"x": 1}),
        ToolCall(tool="tool2", arguments={"y": 2}),
    ]
    
    results = []
    async for result in executor.stream_execute(calls):
        results.append(result)
        
    # Verify results
    assert len(results) == 2
    assert results[0].tool == "tool1"
    assert "Streamed" in results[0].result
    assert results[1].tool == "tool2"
    assert "Streamed" in results[1].result


@pytest.mark.asyncio
async def test_non_streaming_executor(registry, dummy_strategy):
    """Test that non-streaming strategies work with stream_execute."""
    executor = ToolExecutor(
        registry=registry,
        default_timeout=1.0,
        strategy=dummy_strategy
    )

    # Test supports_streaming property
    assert executor.supports_streaming is False
    
    # Test stream_execute method still works
    calls = [
        ToolCall(tool="tool1", arguments={"x": 1}),
        ToolCall(tool="tool2", arguments={"y": 2}),
    ]
    
    results = []
    async for result in executor.stream_execute(calls):
        results.append(result)
        
    # Verify results (we get them all, just not streamed)
    assert len(results) == 2
    assert results[0].tool == "tool1"
    assert results[0].result == "Result for tool1"
    assert results[1].tool == "tool2"
    assert results[1].result == "Result for tool2"


@pytest.mark.asyncio
async def test_executor_timeout_handling(registry):
    """Test that executor handles timeouts correctly."""
    # Create a strategy that simulates timeouts
    class TimeoutStrategy(ExecutionStrategy):
        async def run(self, calls, timeout):
            # Always return timeout errors
            return [
                ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Timeout after {timeout}s",
                )
                for call in calls
            ]
    
    executor = ToolExecutor(
        registry=registry,
        default_timeout=2.0,
        strategy=TimeoutStrategy()
    )
    
    # Test with default timeout
    results = await executor.execute([ToolCall(tool="test")])
    assert "Timeout after 2.0s" in results[0].error
    
    # Test with custom timeout
    results = await executor.execute([ToolCall(tool="test")], timeout=5.0)
    assert "Timeout after 5.0s" in results[0].error


@pytest.mark.asyncio
async def test_executor_shutdown(registry, streaming_strategy):
    """Test executor shutdown method if strategy supports it."""
    # Add shutdown method to strategy
    streaming_strategy.shutdown = AsyncMock()
    
    executor = ToolExecutor(
        registry=registry,
        strategy=streaming_strategy
    )
    
    # Call shutdown
    await executor.shutdown()
    
    # Verify shutdown was called on strategy
    streaming_strategy.shutdown.assert_called_once()
    
    # Test with strategy that doesn't support shutdown
    executor = ToolExecutor(
        registry=registry,
        strategy=DummyStrategy()  # No shutdown method
    )
    
    # Should not raise any errors
    await executor.shutdown()