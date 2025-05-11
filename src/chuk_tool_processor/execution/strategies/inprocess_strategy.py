# chuk_tool_processor/execution/strategies/inprocess_strategy.py
from __future__ import annotations

import asyncio
import inspect
import os
from datetime import datetime, timezone
from typing import Any, List

from chuk_tool_processor.core.exceptions import ToolExecutionError
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.inprocess_strategy")

from contextlib import asynccontextmanager

# Async no-op context manager when no semaphore
@asynccontextmanager
async def _noop_cm():
    yield

class InProcessStrategy(ExecutionStrategy):
    """Execute tools concurrently in the current event-loop."""

    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.registry = registry
        self.default_timeout = default_timeout
        self._sem = asyncio.Semaphore(max_concurrency) if max_concurrency else None

    async def run(
        self,
        calls: List[ToolCall],
        timeout: float | None = None,
    ) -> List[ToolResult]:
        tasks = [
            self._execute_single_call(call, timeout or self.default_timeout)
            for call in calls
        ]
        return await asyncio.gather(*tasks)

    async def _execute_single_call(
        self,
        call: ToolCall,
        timeout: float | None,
    ) -> ToolResult:
        pid = os.getpid()
        machine = os.uname().nodename
        start = datetime.now(timezone.utc)

        impl = self.registry.get_tool(call.tool)
        if impl is None:
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Tool not found",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

        tool = impl() if inspect.isclass(impl) else impl
        guard = self._sem if self._sem is not None else _noop_cm()

        # Determine correct async entry-point, even on bound methods
        if hasattr(tool, "_aexecute") and inspect.iscoroutinefunction(type(tool)._aexecute):
            fn = tool._aexecute
        elif hasattr(tool, "execute") and inspect.iscoroutinefunction(tool.execute):
            fn = tool.execute
        else:
            return ToolResult(
                tool=call.tool,
                result=None,
                error=(
                    "Tool must implement async '_aexecute' or 'execute'."
                ),
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

        async def _invoke():
            return await fn(**call.arguments)

        try:
            async with guard:
                result_val = (
                    await asyncio.wait_for(_invoke(), timeout)
                    if timeout
                    else await _invoke()
                )
            return ToolResult(
                tool=call.tool,
                result=result_val,
                error=None,
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Timeout after {timeout}s",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
        except Exception as exc:
            logger.exception("Error while executing %s", call.tool)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(exc),
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
