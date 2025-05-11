# chuk_tool_processor/execution/tool_executor.py
"""
Thin façade that turns a list of :class:`~chuk_tool_processor.models.tool_call.ToolCall`
objects into a list of :class:`~chuk_tool_processor.models.tool_result.ToolResult`
objects by delegating to an :class:`ExecutionStrategy`.

Everything here is **async-native** – no support for synchronous tools.
"""
from __future__ import annotations

from typing import List, Optional

# Lazy import so test-suites can monkey-patch `InProcessStrategy`
import chuk_tool_processor.execution.strategies.inprocess_strategy as _inprocess_mod
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class ToolExecutor:
    """
    Convenience wrapper that selects a strategy (in-process by default) and
    exposes a single async :py:meth:`execute` method.
    """

    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: float = 1.0,
        strategy: ExecutionStrategy | None = None,
        *,
        strategy_kwargs: dict | None = None,
    ) -> None:
        self.registry = registry
        if strategy is None:
            strategy_kwargs = strategy_kwargs or {}
            strategy = _inprocess_mod.InProcessStrategy(
                registry,
                default_timeout=default_timeout,
                **strategy_kwargs,
            )
        self.strategy = strategy

    # ------------------------------------------------------------------ #
    async def execute(
        self,
        calls: List[ToolCall],
        timeout: float | None = None,
    ) -> List[ToolResult]:
        """Delegate to the underlying strategy (async)."""
        return await self.strategy.run(calls, timeout=timeout)
