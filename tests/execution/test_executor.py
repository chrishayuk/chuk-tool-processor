# tests/execution/test_executor.py
import pytest
from typing import List, Optional

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Minimal stubs
# --------------------------------------------------------------------------- #
class DummyRegistry:
    """Bare-bones registry that always returns *None* (tool not found)."""

    def get_tool(self, name: str):
        return None


class DummyStrategy(ExecutionStrategy):
    """Records every call to *run* and returns predictable results."""

    def __init__(self) -> None:
        self.called: List[tuple[list[ToolCall], Optional[float]]] = []

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        self.called.append((calls, timeout))
        return [
            ToolResult(tool=call.tool, result={"dummy": True}) for call in calls
        ]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_with_custom_strategy():
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
        def __init__(self, registry_arg, default_timeout, **_):
            created["registry"] = registry_arg
            created["timeout"] = default_timeout

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

    assert created == {"registry": registry, "timeout": 3.7}

    results = await executor.execute([ToolCall(tool="t", arguments={})])
    assert results[0].result == "ok"
