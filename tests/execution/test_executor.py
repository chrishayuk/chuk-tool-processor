# tests/execution/test_executor.py
"""
Tests for the async-native ToolExecutor implementation.
"""
import pytest
from typing import List, Optional, Dict, Any, Tuple

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Minimal stubs
# --------------------------------------------------------------------------- #
class DummyRegistry:
    """Bare-bones registry that always returns *None* (tool not found)."""

    async def get_tool(self, name: str):
        return None


class DummyStrategy(ExecutionStrategy):
    """Records every call to *run* and returns predictable results."""

    def __init__(self) -> None:
        self.called: List[Tuple[List[ToolCall], Optional[float]]] = []

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        self.called.append((calls, timeout))
        return [
            ToolResult(tool=call.tool, result={"dummy": True}) for call in calls
        ]


class StreamingStrategy(ExecutionStrategy):
    """Strategy that implements stream_run for testing streaming."""
    
    def __init__(self) -> None:
        self.run_called = False
        self.stream_run_called = False
        
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        self.run_called = True
        return [
            ToolResult(tool=call.tool, result={"method": "run"}) for call in calls
        ]
        
    async def stream_run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ):
        self.stream_run_called = True
        for call in calls:
            yield ToolResult(tool=call.tool, result={"method": "stream_run"})
    
    @property
    def supports_streaming(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_with_custom_strategy():
    """Test that the executor properly delegates to a custom strategy."""
    registry = DummyRegistry()
    strategy = DummyStrategy()
    executor = ToolExecutor(registry, default_timeout=2.5, strategy=strategy)

    calls = [
        ToolCall(tool="tool1", arguments={}),
        ToolCall(tool="tool2", arguments={"x": 1}),
    ]

    # Override timeout on execute()
    results = await executor.execute(calls, timeout=5.0)

    # Strategy.run was called exactly once with the same list object & timeout
    assert strategy.called == [(calls, 5.0)]

    # Returned ToolResults are in 1-to-1 order with *calls*
    assert [r.tool for r in results] == ["tool1", "tool2"]
    assert all(r.result == {"dummy": True} for r in results)


@pytest.mark.asyncio
async def test_default_strategy_is_inprocess(monkeypatch):
    """
    ToolExecutor should instantiate whatever
    chuk_tool_processor.execution.strategies.inprocess_strategy.InProcessStrategy
    points to – we monkey-patch it to a test stub.
    """
    from chuk_tool_processor.execution import strategies as _strategies

    created: dict = {}

    class FakeInProcess:
        def __init__(self, registry_arg, default_timeout, **kwargs):
            created["registry"] = registry_arg
            created["timeout"] = default_timeout
            created["kwargs"] = kwargs

        async def run(
            self,
            calls: List[ToolCall],
            timeout: Optional[float] = None,
        ) -> List[ToolResult]:
            return [
                ToolResult(tool=c.tool, result="ok") for c in calls
            ]

    monkeypatch.setattr(
        _strategies.inprocess_strategy, "InProcessStrategy", FakeInProcess
    )

    registry = DummyRegistry()

    # No strategy supplied → ToolExecutor should use our FakeInProcess
    executor = ToolExecutor(registry, default_timeout=3.7)

    assert created["registry"] == registry
    assert created["timeout"] == 3.7

    results = await executor.execute([ToolCall(tool="t", arguments={})])
    assert results[0].result == "ok"


@pytest.mark.asyncio
async def test_executor_with_empty_calls():
    """Test that the executor handles empty calls correctly."""
    registry = DummyRegistry()
    strategy = DummyStrategy()
    executor = ToolExecutor(registry, default_timeout=2.5, strategy=strategy)
    
    # Empty calls should return empty results
    results = await executor.execute([])
    assert results == []
    assert len(strategy.called) == 1
    assert strategy.called[0][0] == []  # Empty calls list passed to strategy


@pytest.mark.asyncio
async def test_executor_with_strategy_kwargs():
    """Test that strategy_kwargs are passed to the strategy constructor."""
    from chuk_tool_processor.execution import strategies as _strategies
    
    created: Dict[str, Any] = {}
    
    class FakeInProcess:
        def __init__(self, registry_arg, default_timeout, **kwargs):
            created["registry"] = registry_arg
            created["timeout"] = default_timeout
            created["kwargs"] = kwargs
            
        async def run(self, calls, timeout=None):
            return [ToolResult(tool=c.tool, result="ok") for c in calls]
            
    monkeypatch.setattr(
        _strategies.inprocess_strategy, "InProcessStrategy", FakeInProcess
    )
    
    registry = DummyRegistry()
    
    # Pass strategy_kwargs to ToolExecutor
    strategy_kwargs = {"max_concurrency": 5, "custom_option": "value"}
    executor = ToolExecutor(
        registry, 
        default_timeout=2.0,
        strategy_kwargs=strategy_kwargs
    )
    
    # Verify kwargs were passed to strategy
    assert created["kwargs"] == strategy_kwargs
    
    # Execute to verify functionality
    results = await executor.execute([ToolCall(tool="test", arguments={})])
    assert len(results) == 1
    assert results[0].result == "ok"


@pytest.mark.asyncio
async def test_executor_with_registry_validation():
    """Test that the executor validates the registry parameter."""
    # Test that registry is required when no strategy is provided
    with pytest.raises(ValueError):
        ToolExecutor(registry=None, default_timeout=1.0)
    
    # Test that it works when strategy is provided (registry can be None)
    strategy = DummyStrategy()
    executor = ToolExecutor(
        registry=None,
        default_timeout=1.0,
        strategy=strategy
    )
    
    # Should work without errors
    results = await executor.execute([ToolCall(tool="test", arguments={})])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_streaming_executor():
    """Test that the executor supports streaming when strategy does."""
    registry = DummyRegistry()
    strategy = StreamingStrategy()
    
    executor = ToolExecutor(
        registry=registry,
        default_timeout=1.0,
        strategy=strategy
    )
    
    # Test supports_streaming property
    assert executor.supports_streaming is True
    
    # Test stream_execute method
    calls = [ToolCall(tool="test", arguments={})]
    results = []
    
    async for result in executor.stream_execute(calls):
        results.append(result)
    
    assert len(results) == 1
    assert results[0].tool == "test"
    assert results[0].result == {"method": "stream_run"}
    assert strategy.stream_run_called is True


@pytest.mark.asyncio
async def test_non_streaming_executor():
    """Test that non-streaming strategies work with stream_execute."""
    registry = DummyRegistry()
    strategy = DummyStrategy()  # Non-streaming strategy
    
    executor = ToolExecutor(
        registry=registry,
        default_timeout=1.0,
        strategy=strategy
    )
    
    # Test supports_streaming property
    assert executor.supports_streaming is False
    
    # Test stream_execute method (should use run internally)
    calls = [ToolCall(tool="test", arguments={})]
    results = []
    
    async for result in executor.stream_execute(calls):
        results.append(result)
    
    assert len(results) == 1
    assert results[0].tool == "test"
    assert results[0].result == {"dummy": True}
    
    # Verify it used the regular run method
    assert len(strategy.called) == 1
    assert strategy.called[0][0] == calls