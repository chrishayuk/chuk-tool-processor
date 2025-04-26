"""
In-process execution strategy with sync/async support.

This version prefers the public `execute()` wrapper (with validation and
defaults) over the private `_execute` implementation, fixing missing-argument
errors for `ValidatedTool` subclasses.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from chuk_tool_processor.core.exceptions import ToolExecutionError
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.inprocess_strategy")


class InProcessStrategy(ExecutionStrategy):
    """Run tools inside the current interpreter, concurrently."""

    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.registry = registry
        self.default_timeout = default_timeout
        self._sem = asyncio.Semaphore(max_concurrency) if max_concurrency else None

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
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

        try:
            run = self._run_with_timeout
            if self._sem is None:
                return await run(impl, call, timeout, start, machine, pid)
            async with self._sem:
                return await run(impl, call, timeout, start, machine, pid)
        except Exception as exc:  # pragma: no cover – safety net
            logger.exception("Unexpected error while executing %s", call.tool)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Unexpected error: {exc}",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

    # ------------------------------------------------------------------ #
    # core execution with timeout
    # ------------------------------------------------------------------ #
    async def _run_with_timeout(
        self,
        impl: Any,
        call: ToolCall,
        timeout: float | None,
        start: datetime,
        machine: str,
        pid: int,
    ) -> ToolResult:
        tool = impl() if isinstance(impl, type) else impl

        # ------------------------------------------------------------------
        # Entry-point selection order:
        # 1. `_aexecute` (async special case)
        # 2. `execute`   (public wrapper WITH validation & defaults)
        # 3. `_execute`  (fallback / legacy)
        # ------------------------------------------------------------------
        if hasattr(tool, "_aexecute") and inspect.iscoroutinefunction(tool._aexecute):
            fn = tool._aexecute
            is_async = True
        elif hasattr(tool, "execute"):
            fn = tool.execute
            is_async = inspect.iscoroutinefunction(fn)
        elif hasattr(tool, "_execute"):
            fn = tool._execute
            is_async = inspect.iscoroutinefunction(fn)
        else:
            raise ToolExecutionError(
                f"Tool '{call.tool}' must implement _execute, execute or _aexecute"
            )

        async def _invoke():
            if is_async:
                return await fn(**call.arguments)
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: fn(**call.arguments))

        try:
            result_val = (
                await asyncio.wait_for(_invoke(), timeout) if timeout else await _invoke()
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
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(exc),
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
