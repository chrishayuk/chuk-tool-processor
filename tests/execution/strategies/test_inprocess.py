# tests/execution/strategies/test_inprocess.py
"""
Run tools concurrently *inside the current interpreter* – async-only.

A valid tool implementation must define either:

1. `async def _aexecute(**kwargs)`  – recommended private coroutine
2. `async def execute(**kwargs)`    – public coroutine wrapper

Synchronous entry-points are **not supported**.
"""
from __future__ import annotations

import asyncio
import inspect
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, List

from chuk_tool_processor.core.exceptions import ToolExecutionError
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.inprocess_strategy")


# --------------------------------------------------------------------------- #
# Async no-op context-manager (used when no semaphore configured)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _noop_cm():
    yield


# --------------------------------------------------------------------------- #
class InProcessStrategy(ExecutionStrategy):
    """Execute tools in the local event-loop with optional concurrency cap."""

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
    async def run(
        self,
        calls: List[ToolCall],
        timeout: float | None = None,
    ) -> List[ToolResult]:
        """Execute *calls* concurrently and preserve order."""
        tasks = [
            self._execute_single_call(call, timeout or self.default_timeout)
            for call in calls
        ]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------ #
    async def _execute_single_call(
        self,
        call: ToolCall,
        timeout: float | None,
    ) -> ToolResult:
        """
        Execute a single tool call.

        The entire invocation – including argument validation – is wrapped
        by the semaphore to honour *max_concurrency*.
        """
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

        try:
            async with guard:
                return await self._run_with_timeout(
                    tool, call, timeout, start, machine, pid
                )
        except Exception as exc:  # pragma: no cover – last-chance safety net
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
    async def _run_with_timeout(
        self,
        tool: Any,
        call: ToolCall,
        timeout: float | None,
        start: datetime,
        machine: str,
        pid: int,
    ) -> ToolResult:
        """
        Resolve the correct async entry-point and invoke it with an optional
        timeout.
        """
        if hasattr(tool, "_aexecute") and inspect.iscoroutinefunction(tool._aexecute):
            fn = tool._aexecute
        elif hasattr(tool, "execute") and inspect.iscoroutinefunction(tool.execute):
            fn = tool.execute
        else:
            return ToolResult(
                tool=call.tool,
                result=None,
                error=(
                    "Tool must implement *async* '_aexecute' or 'execute'. "
                    "Synchronous entry-points are not supported."
                ),
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

        async def _invoke():
            return await fn(**call.arguments)

        try:
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
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(exc),
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
