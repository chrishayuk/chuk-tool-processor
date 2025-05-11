"""
Unit tests for the ToolExecutor class.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Optional, AsyncIterator

import pytest
from unittest.mock import patch, AsyncMock

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


# --------------------------------------------------------------------------- #
# Mock registry
# --------------------------------------------------------------------------- #
class MockRegistry:
    """Very small async-compatible registry stub."""

    def __init__(self, tools: Dict[str, Any] | None = None):
        self._tools = tools or {}

    async def get_tool(self, name: str, namespace: str = "default") -> Optional[Any]:
        return self._tools.get(name)

    async def get_metadata(self, name: str, namespace: str = "default") -> Optional[Any]:
        if name in self._tools:
            return {"description": f"mock meta {name}", "supports_streaming": False}
        return None

    async def list_tools(self, namespace: Optional[str] = None) -> list:
        return [(namespace or "default", n) for n in self._tools]


# --------------------------------------------------------------------------- #
# Dummy strategies
# --------------------------------------------------------------------------- #
class DummyStrategy(ExecutionStrategy):
    """
    Non-streaming mock strategy.  The flexible __init__ lets it act as a stand-in
    for InProcessStrategy when ToolExecutor instantiates one with kwargs.
    """

    def __init__(self, *args, **kwargs):  # swallow anything
        self._args = args
        self._kwargs = kwargs

    async def run(
        self, calls: List[ToolCall], timeout: Optional[float] = None
    ) -> List[ToolResult]:
        return [
            ToolResult(tool=c.tool, result=f"Result for {c.tool}", error=None)
            for c in calls
        ]

    @property
    def supports_streaming(self) -> bool:  # noqa: D401
        return False


class StreamingStrategy(DummyStrategy):
    """Same as DummyStrategy but with stream support."""

    async def stream_run(
        self, calls: List[ToolCall], timeout: Optional[float] = None
    ) -> AsyncIterator[ToolResult]:
        for c in calls:
            yield ToolResult(tool=c.tool, result=f"Streamed {c.tool}", error=None)
            await asyncio.sleep(0.01)

    @property
    def supports_streaming(self) -> bool:  # noqa: D401
        return True


class ErrorStrategy(DummyStrategy):
    """Always returns an error."""

    async def run(
        self, calls: List[ToolCall], timeout: Optional[float] = None
    ) -> List[ToolResult]:
        return [
            ToolResult(tool=c.tool, result=None, error=f"error {c.tool}") for c in calls
        ]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def registry() -> MockRegistry:
    return MockRegistry()


@pytest.fixture
def dummy_strategy() -> DummyStrategy:
    return DummyStrategy()


@pytest.fixture
def streaming_strategy() -> StreamingStrategy:
    return StreamingStrategy()


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_initialisation_explicit_strategy(registry, dummy_strategy):
    ex = ToolExecutor(registry=registry, default_timeout=7, strategy=dummy_strategy)
    assert ex.strategy is dummy_strategy
    assert ex.default_timeout == 7


@pytest.mark.asyncio
async def test_executor_initialisation_creates_inprocess_strategy(registry):
    """
    If *strategy* is omitted, ``ToolExecutor`` should import and instantiate
    ``InProcessStrategy`` – we monkey-patch that class at the real import path.
    """
    patch_target = (
        "chuk_tool_processor.execution.strategies.inprocess_strategy.InProcessStrategy"
    )
    with patch(patch_target) as mock_cls:
        mock_cls.return_value = DummyStrategy()  # what ToolExecutor gets back

        ex = ToolExecutor(
            registry=registry,
            default_timeout=9,
            strategy_kwargs={"max_concurrency": 5, "hello": "world"},
        )

        mock_cls.assert_called_once_with(
            registry, default_timeout=9, max_concurrency=5, hello="world"
        )
        assert isinstance(ex.strategy, DummyStrategy)


@pytest.mark.asyncio
async def test_execute_returns_results_in_order(registry, dummy_strategy):
    ex = ToolExecutor(registry=registry, strategy=dummy_strategy)
    calls = [ToolCall(tool="a"), ToolCall(tool="b")]
    res = await ex.execute(calls)
    assert [r.tool for r in res] == ["a", "b"]


@pytest.mark.asyncio
async def test_execute_empty_call_list(registry, dummy_strategy):
    ex = ToolExecutor(registry=registry, strategy=dummy_strategy)
    res = await ex.execute([])
    assert res == []


@pytest.mark.asyncio
async def test_stream_execute_with_streaming_strategy(registry, streaming_strategy):
    ex = ToolExecutor(registry=registry, strategy=streaming_strategy)
    calls = [ToolCall(tool="a"), ToolCall(tool="b")]
    collected = []
    async for r in ex.stream_execute(calls):
        collected.append(r.tool)
    assert collected == ["a", "b"]


@pytest.mark.asyncio
async def test_stream_execute_falls_back_for_non_streaming_strategy(
    registry, dummy_strategy
):
    ex = ToolExecutor(registry=registry, strategy=dummy_strategy)
    calls = [ToolCall(tool="a"), ToolCall(tool="b")]
    collected = []
    async for r in ex.stream_execute(calls):
        collected.append(r.tool)
    assert collected == ["a", "b"]


@pytest.mark.asyncio
async def test_timeout_is_forwarded(registry):
    class TimeoutSpy(DummyStrategy):
        async def run(self, calls, timeout=None):
            self.seen_timeout = timeout
            return await super().run(calls, timeout)

    strat = TimeoutSpy()
    ex = ToolExecutor(registry=registry, default_timeout=3, strategy=strat)
    await ex.execute([ToolCall(tool="x")], timeout=7)
    assert strat.seen_timeout == 7


@pytest.mark.asyncio
async def test_shutdown_calls_underlying_strategy(registry):
    strat = DummyStrategy()
    strat.shutdown = AsyncMock()
    ex = ToolExecutor(registry=registry, strategy=strat)
    await ex.shutdown()
    strat.shutdown.assert_called_once()
