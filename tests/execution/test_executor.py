import pytest
import asyncio
from typing import List, Optional

import pytest

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy

# Dummy registry to satisfy interface
class DummyRegistry:
    def get_tool(self, name: str):
        return None

# Dummy strategy implementing ExecutionStrategy
class DummyStrategy(ExecutionStrategy):
    def __init__(self):
        self.called: List = []

    async def run(self, calls: List[ToolCall], timeout: Optional[float] = None) -> List[ToolResult]:
        # record parameters and return dummy results
        self.called.append((calls, timeout))
        return [ToolResult(tool=call.tool, result={"dummy": True}) for call in calls]

@pytest.mark.asyncio
async def test_execute_with_custom_strategy():
    registry = DummyRegistry()
    dummy = DummyStrategy()
    executor = ToolExecutor(registry=registry, default_timeout=2.5, strategy=dummy)

    calls = [ToolCall(tool="tool1", arguments={}), ToolCall(tool="tool2", arguments={"x": 1})]
    # call with explicit timeout override
    results = await executor.execute(calls, timeout=5.0)

    # Strategy.run should have been called once with the provided calls and timeout
    assert len(dummy.called) == 1
    called_calls, called_timeout = dummy.called[0]
    assert called_calls is calls
    assert called_timeout == 5.0

    # Results should be a list of ToolResult corresponding to each call
    assert isinstance(results, list)
    assert all(isinstance(r, ToolResult) for r in results)
    assert [r.tool for r in results] == ["tool1", "tool2"]
    assert all(r.result == {"dummy": True} for r in results)

@pytest.mark.asyncio
async def test_default_strategy_used(monkeypatch):
    registry = DummyRegistry()
    # Patch InProcessStrategy to return our DummyStrategy
    from chuk_tool_processor.execution.strategies import inprocess_strategy

    created = {}
    class FakeInProcess:
        def __init__(self, registry_arg, default_timeout, max_concurrency=None):
            # record init args
            created['registry'] = registry_arg
            created['timeout'] = default_timeout

        async def run(self, calls: List[ToolCall], timeout: Optional[float] = None) -> List[ToolResult]:
            # return a predictable result
            return [ToolResult(tool=c.tool, result="ok") for c in calls]

    monkeypatch.setattr(inprocess_strategy, 'InProcessStrategy', FakeInProcess)

    # Create executor without providing a strategy
    executor = ToolExecutor(registry=registry, default_timeout=3.7)

    # Ensure our FakeInProcess was instantiated
    assert created['registry'] is registry
    assert created['timeout'] == 3.7

    calls = [ToolCall(tool="t", arguments={})]
    results = await executor.execute(calls)

    # Verify results come from FakeInProcess.run
    assert len(results) == 1
    assert results[0].tool == "t"
    assert results[0].result == "ok"
