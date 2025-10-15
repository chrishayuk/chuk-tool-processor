# tests/models/test_execution_strategy.py
import pytest

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class ConcreteStrategy(ExecutionStrategy):
    """Concrete implementation for testing."""

    async def run(self, calls: list[ToolCall], timeout: float | None = None) -> list[ToolResult]:
        """Execute calls and return results."""
        results = []
        for call in calls:
            result = ToolResult(tool=call.tool, result={"executed": True, "timeout": timeout}, error=None)
            results.append(result)
        return results


class StreamingStrategy(ExecutionStrategy):
    """Streaming implementation for testing."""

    async def run(self, calls: list[ToolCall], timeout: float | None = None) -> list[ToolResult]:
        """Execute calls and return results."""
        results = []
        for call in calls:
            result = ToolResult(tool=call.tool, result={"executed": True, "streaming": True}, error=None)
            results.append(result)
        return results

    @property
    def supports_streaming(self) -> bool:
        """Override to indicate streaming support."""
        return True


@pytest.mark.asyncio
async def test_concrete_strategy_run():
    """Test running a concrete strategy."""
    strategy = ConcreteStrategy()
    calls = [
        ToolCall(tool="tool1", arguments={"arg": "value1"}),
        ToolCall(tool="tool2", arguments={"arg": "value2"}),
    ]

    results = await strategy.run(calls)

    assert len(results) == 2
    assert results[0].tool == "tool1"
    assert results[1].tool == "tool2"
    assert results[0].result == {"executed": True, "timeout": None}
    assert results[1].result == {"executed": True, "timeout": None}


@pytest.mark.asyncio
async def test_concrete_strategy_run_with_timeout():
    """Test running strategy with timeout."""
    strategy = ConcreteStrategy()
    calls = [ToolCall(tool="tool1")]

    results = await strategy.run(calls, timeout=30.0)

    assert len(results) == 1
    assert results[0].result == {"executed": True, "timeout": 30.0}


@pytest.mark.asyncio
async def test_concrete_strategy_run_empty_calls():
    """Test running strategy with empty call list."""
    strategy = ConcreteStrategy()
    results = await strategy.run([])

    assert results == []


@pytest.mark.asyncio
async def test_default_stream_run():
    """Test default stream_run implementation."""
    strategy = ConcreteStrategy()
    calls = [
        ToolCall(tool="tool1"),
        ToolCall(tool="tool2"),
        ToolCall(tool="tool3"),
    ]

    results = []
    async for result in strategy.stream_run(calls):
        results.append(result)

    assert len(results) == 3
    assert results[0].tool == "tool1"
    assert results[1].tool == "tool2"
    assert results[2].tool == "tool3"


@pytest.mark.asyncio
async def test_stream_run_with_timeout():
    """Test stream_run with timeout parameter."""
    strategy = ConcreteStrategy()
    calls = [ToolCall(tool="tool1")]

    results = []
    async for result in strategy.stream_run(calls, timeout=15.0):
        results.append(result)

    assert len(results) == 1
    assert results[0].result == {"executed": True, "timeout": 15.0}


@pytest.mark.asyncio
async def test_stream_run_empty_calls():
    """Test stream_run with empty call list."""
    strategy = ConcreteStrategy()

    results = []
    async for result in strategy.stream_run([]):
        results.append(result)

    assert results == []


def test_supports_streaming_default():
    """Test default supports_streaming property."""
    strategy = ConcreteStrategy()
    assert strategy.supports_streaming is False


def test_supports_streaming_override():
    """Test overridden supports_streaming property."""
    strategy = StreamingStrategy()
    assert strategy.supports_streaming is True


@pytest.mark.asyncio
async def test_streaming_strategy_run():
    """Test streaming strategy run method."""
    strategy = StreamingStrategy()
    calls = [ToolCall(tool="stream_tool")]

    results = await strategy.run(calls)

    assert len(results) == 1
    assert results[0].result == {"executed": True, "streaming": True}


@pytest.mark.asyncio
async def test_streaming_strategy_stream_run():
    """Test streaming strategy with stream_run."""
    strategy = StreamingStrategy()
    calls = [
        ToolCall(tool="stream1"),
        ToolCall(tool="stream2"),
    ]

    results = []
    async for result in strategy.stream_run(calls):
        results.append(result)

    assert len(results) == 2
    assert all(r.result["streaming"] is True for r in results)


@pytest.mark.asyncio
async def test_multiple_strategies():
    """Test that different strategies can coexist."""
    concrete = ConcreteStrategy()
    streaming = StreamingStrategy()

    assert concrete.supports_streaming is False
    assert streaming.supports_streaming is True

    calls = [ToolCall(tool="test")]

    concrete_results = await concrete.run(calls)
    streaming_results = await streaming.run(calls)

    # Verify results differ based on strategy
    assert concrete_results[0].result.get("streaming") is None
    assert streaming_results[0].result["streaming"] is True
