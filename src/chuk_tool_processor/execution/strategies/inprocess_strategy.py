#!/usr/bin/env python
# chuk_tool_processor/execution/strategies/inprocess_strategy.py
"""
In-process execution strategy for tools with proper timeout handling.

This strategy executes tools concurrently in the same process using asyncio.
It has special support for streaming tools, accessing their stream_execute method
directly to enable true item-by-item streaming.

FIXED: Ensures consistent timeout handling across all execution paths.
"""
from __future__ import annotations

import asyncio
import inspect
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, List, Optional, AsyncIterator, Set

from chuk_tool_processor.core.exceptions import ToolExecutionError
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger, log_context_span

logger = get_logger("chuk_tool_processor.execution.inprocess_strategy")


# --------------------------------------------------------------------------- #
# Async no-op context-manager (used when no semaphore configured)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _noop_cm():
    yield


# --------------------------------------------------------------------------- #
class InProcessStrategy(ExecutionStrategy):
    """Execute tools in the local event-loop with optional concurrency cap and consistent timeout handling."""

    def __init__(
        self,
        registry: ToolRegistryInterface,
        default_timeout: Optional[float] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        """
        Initialize the in-process execution strategy.
        
        Args:
            registry: Tool registry to use for tool lookups
            default_timeout: Default timeout for tool execution
            max_concurrency: Maximum number of concurrent executions
        """
        self.registry = registry
        self.default_timeout = default_timeout or 30.0  # Always have a default
        self._sem = asyncio.Semaphore(max_concurrency) if max_concurrency else None
        
        # Task tracking for cleanup
        self._active_tasks = set()
        self._shutting_down = False
        self._shutdown_event = asyncio.Event()
        
        # Tracking for which calls are being handled directly by the executor
        # to prevent duplicate streaming results
        self._direct_streaming_calls = set()
        
        logger.debug("InProcessStrategy initialized with timeout: %ss, max_concurrency: %s", 
                    self.default_timeout, max_concurrency)

    # ------------------------------------------------------------------ #
    def mark_direct_streaming(self, call_ids: Set[str]) -> None:
        """
        Mark tool calls that are being handled directly by the executor.
        
        Args:
            call_ids: Set of call IDs that should be skipped during streaming
                      because they're handled directly
        """
        self._direct_streaming_calls.update(call_ids)
        
    def clear_direct_streaming(self) -> None:
        """Clear the list of direct streaming calls."""
        self._direct_streaming_calls.clear()
        
    # ------------------------------------------------------------------ #
    #  🔌 legacy façade for older wrappers                                #
    # ------------------------------------------------------------------ #
    async def execute(
        self,
        calls: List[ToolCall],
        *,
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """
        Back-compat shim.

        Old wrappers (`retry`, `rate_limit`, `cache`, …) still expect an
        ``execute()`` coroutine on an execution-strategy object.
        The real implementation lives in :meth:`run`, so we just forward.
        """
        return await self.run(calls, timeout)

    # ------------------------------------------------------------------ #
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """
        Execute tool calls concurrently and preserve order.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution
            
        Returns:
            List of tool results in the same order as calls
        """
        if not calls:
            return []
        
        # Use default_timeout if no timeout specified
        effective_timeout = timeout if timeout is not None else self.default_timeout
        logger.debug("Executing %d calls with %ss timeout each", len(calls), effective_timeout)
            
        tasks = []
        for call in calls:
            task = asyncio.create_task(
                self._execute_single_call(call, effective_timeout)  # Always pass timeout
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            tasks.append(task)
            
        async with log_context_span("inprocess_execution", {"num_calls": len(calls)}):
            return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------ #
    async def stream_run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> AsyncIterator[ToolResult]:
        """
        Execute tool calls concurrently and *yield* results as soon as they are
        produced, preserving completion order.
        """
        if not calls:
            return

        # Use default_timeout if no timeout specified
        effective_timeout = timeout if timeout is not None else self.default_timeout

        queue: asyncio.Queue[ToolResult] = asyncio.Queue()
        tasks = {
            asyncio.create_task(
                self._stream_tool_call(call, queue, effective_timeout)  # Always pass timeout
            )
            for call in calls
            if call.id not in self._direct_streaming_calls
        }

        # 🔑 keep consuming until every worker‐task finished *and*
        #    the queue is empty
        while tasks or not queue.empty():
            try:
                result = await queue.get()
                yield result
            except asyncio.CancelledError:
                break

            # clear finished tasks (frees exceptions as well)
            done, tasks = await asyncio.wait(tasks, timeout=0)
            for t in done:
                t.result()  # re-raise if a task crashed


    async def _stream_tool_call(
        self,
        call: ToolCall,
        queue: asyncio.Queue,
        timeout: float,  # Make timeout required
    ) -> None:
        """
        Execute a tool call with streaming support.
        
        This looks up the tool and if it's a streaming tool, it accesses
        stream_execute directly to get item-by-item streaming.
        
        Args:
            call: The tool call to execute
            queue: Queue to put results into
            timeout: Timeout in seconds (required)
        """
        # Skip if call is being handled directly by the executor
        if call.id in self._direct_streaming_calls:
            return
            
        if self._shutting_down:
            # Early exit if shutting down
            now = datetime.now(timezone.utc)
            result = ToolResult(
                tool=call.tool,
                result=None,
                error="System is shutting down",
                start_time=now,
                end_time=now,
                machine=os.uname().nodename,
                pid=os.getpid(),
            )
            await queue.put(result)
            return
            
        try:
            # Get the tool implementation
            tool_impl = await self.registry.get_tool(call.tool, call.namespace)
            if tool_impl is None:
                # Tool not found
                now = datetime.now(timezone.utc)
                result = ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Tool '{call.tool}' not found",
                    start_time=now,
                    end_time=now,
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
                await queue.put(result)
                return
                
            # Instantiate if class
            tool = tool_impl() if inspect.isclass(tool_impl) else tool_impl
            
            # Use semaphore if available
            guard = self._sem if self._sem is not None else _noop_cm()
            
            async with guard:
                # Check if this is a streaming tool
                if hasattr(tool, "supports_streaming") and tool.supports_streaming and hasattr(tool, "stream_execute"):
                    # Use direct streaming for streaming tools
                    await self._stream_with_timeout(tool, call, queue, timeout)
                else:
                    # Use regular execution for non-streaming tools
                    result = await self._execute_single_call(call, timeout)
                    await queue.put(result)
                    
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            now = datetime.now(timezone.utc)
            result = ToolResult(
                tool=call.tool,
                result=None,
                error="Execution was cancelled",
                start_time=now,
                end_time=now,
                machine=os.uname().nodename,
                pid=os.getpid(),
            )
            await queue.put(result)
            
        except Exception as e:
            # Handle other errors
            now = datetime.now(timezone.utc)
            result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Error setting up execution: {e}",
                start_time=now,
                end_time=now,
                machine=os.uname().nodename,
                pid=os.getpid(),
            )
            await queue.put(result)
            
    async def _stream_with_timeout(
        self, 
        tool: Any, 
        call: ToolCall, 
        queue: asyncio.Queue, 
        timeout: float,  # Make timeout required
    ) -> None:
        """
        Stream results from a streaming tool with timeout support.
        
        This method accesses the tool's stream_execute method directly
        and puts each yielded result into the queue.
        
        Args:
            tool: The tool instance
            call: Tool call data
            queue: Queue to put results into
            timeout: Timeout in seconds (required)
        """
        start_time = datetime.now(timezone.utc)
        machine = os.uname().nodename
        pid = os.getpid()
        
        logger.debug("Streaming %s with %ss timeout", call.tool, timeout)
        
        # Define the streaming task
        async def streamer():
            try:
                async for result in tool.stream_execute(**call.arguments):
                    # Create a ToolResult for each streamed item
                    now = datetime.now(timezone.utc)
                    tool_result = ToolResult(
                        tool=call.tool,
                        result=result,
                        error=None,
                        start_time=start_time,
                        end_time=now,
                        machine=machine,
                        pid=pid,
                    )
                    await queue.put(tool_result)
            except Exception as e:
                # Handle errors during streaming
                now = datetime.now(timezone.utc)
                error_result = ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Streaming error: {str(e)}",
                    start_time=start_time,
                    end_time=now,
                    machine=machine,
                    pid=pid,
                )
                await queue.put(error_result)
        
        try:
            # Always execute with timeout
            await asyncio.wait_for(streamer(), timeout)
            logger.debug("%s streaming completed within %ss", call.tool, timeout)
                
        except asyncio.TimeoutError:
            # Handle timeout
            now = datetime.now(timezone.utc)
            actual_duration = (now - start_time).total_seconds()
            logger.debug("%s streaming timed out after %.3fs (limit: %ss)", 
                        call.tool, actual_duration, timeout)
            
            timeout_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Streaming timeout after {timeout}s",
                start_time=start_time,
                end_time=now,
                machine=machine,
                pid=pid,
            )
            await queue.put(timeout_result)
            
        except Exception as e:
            # Handle other errors
            now = datetime.now(timezone.utc)
            logger.debug("%s streaming failed: %s", call.tool, e)
            
            error_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Error during streaming: {str(e)}",
                start_time=start_time,
                end_time=now,
                machine=machine,
                pid=pid,
            )
            await queue.put(error_result)

    async def _execute_to_queue(
        self,
        call: ToolCall,
        queue: asyncio.Queue,
        timeout: float,  # Make timeout required
    ) -> None:
        """Execute a single call and put the result in the queue."""
        # Skip if call is being handled directly by the executor
        if call.id in self._direct_streaming_calls:
            return
            
        result = await self._execute_single_call(call, timeout)
        await queue.put(result)

    # ------------------------------------------------------------------ #
    async def _execute_single_call(
        self,
        call: ToolCall,
        timeout: float,  # Make timeout required, not optional
    ) -> ToolResult:
        """
        Execute a single tool call with guaranteed timeout.

        The entire invocation – including argument validation – is wrapped
        by the semaphore to honour *max_concurrency*.
        
        Args:
            call: Tool call to execute
            timeout: Timeout in seconds (required)
            
        Returns:
            Tool execution result
        """
        pid = os.getpid()
        machine = os.uname().nodename
        start = datetime.now(timezone.utc)
        
        logger.debug("Executing %s with %ss timeout", call.tool, timeout)
        
        # Early exit if shutting down
        if self._shutting_down:
            return ToolResult(
                tool=call.tool,
                result=None,
                error="System is shutting down",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

        try:
            # Get the tool implementation
            impl = await self.registry.get_tool(call.tool, call.namespace)
            if impl is None:
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Tool '{call.tool}' not found",
                    start_time=start,
                    end_time=datetime.now(timezone.utc),
                    machine=machine,
                    pid=pid,
                )

            # Instantiate if class
            tool = impl() if inspect.isclass(impl) else impl
            
            # Use semaphore if available
            guard = self._sem if self._sem is not None else _noop_cm()

            try:
                async with guard:
                    return await self._run_with_timeout(
                        tool, call, timeout, start, machine, pid
                    )
            except Exception as exc:
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
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Execution was cancelled",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
        except Exception as exc:
            logger.exception("Error setting up execution for %s", call.tool)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Setup error: {exc}",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )

    async def _run_with_timeout(
        self,
        tool: Any,
        call: ToolCall,
        timeout: float,  # Make timeout required, not optional
        start: datetime,
        machine: str,
        pid: int,
    ) -> ToolResult:
        """
        Resolve the correct async entry-point and invoke it with a guaranteed timeout.
        
        Args:
            tool: Tool instance
            call: Tool call data
            timeout: Timeout in seconds (required)
            start: Start time for the execution
            machine: Machine name
            pid: Process ID
            
        Returns:
            Tool execution result
        """
        if hasattr(tool, "_aexecute") and inspect.iscoroutinefunction(
            getattr(type(tool), "_aexecute", None)
        ):
            fn = tool._aexecute
        elif hasattr(tool, "execute") and inspect.iscoroutinefunction(
            getattr(tool, "execute", None)
        ):
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

        try:
            # Always apply timeout
            logger.debug("Applying %ss timeout to %s", timeout, call.tool)
            
            try:
                result_val = await asyncio.wait_for(fn(**call.arguments), timeout=timeout)
                
                end_time = datetime.now(timezone.utc)
                actual_duration = (end_time - start).total_seconds()
                logger.debug("%s completed in %.3fs (limit: %ss)", 
                           call.tool, actual_duration, timeout)
                
                return ToolResult(
                    tool=call.tool,
                    result=result_val,
                    error=None,
                    start_time=start,
                    end_time=end_time,
                    machine=machine,
                    pid=pid,
                )
            except asyncio.TimeoutError:
                # Handle timeout
                end_time = datetime.now(timezone.utc)
                actual_duration = (end_time - start).total_seconds()
                logger.debug("%s timed out after %.3fs (limit: %ss)", 
                           call.tool, actual_duration, timeout)
                
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Timeout after {timeout}s",
                    start_time=start,
                    end_time=end_time,
                    machine=machine,
                    pid=pid,
                )
                
        except asyncio.CancelledError:
            # Handle cancellation explicitly
            logger.debug("%s was cancelled", call.tool)
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Execution was cancelled",
                start_time=start,
                end_time=datetime.now(timezone.utc),
                machine=machine,
                pid=pid,
            )
        except Exception as exc:
            logger.exception("Error executing %s: %s", call.tool, exc)
            end_time = datetime.now(timezone.utc)
            actual_duration = (end_time - start).total_seconds()
            logger.debug("%s failed after %.3fs: %s", call.tool, actual_duration, exc)
            
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(exc),
                start_time=start,
                end_time=end_time,
                machine=machine,
                pid=pid,
            )
            
    @property
    def supports_streaming(self) -> bool:
        """Check if this strategy supports streaming execution."""
        return True
        
    async def shutdown(self) -> None:
        """
        Gracefully shut down all active executions.
        
        This cancels all active tasks and waits for them to complete.
        """
        if self._shutting_down:
            return
            
        self._shutting_down = True
        self._shutdown_event.set()
        
        # Cancel all active tasks
        active_tasks = list(self._active_tasks)
        if active_tasks:
            logger.info(f"Cancelling {len(active_tasks)} active tool executions")
            for task in active_tasks:
                task.cancel()
                
            # Wait for all tasks to complete (with cancellation)
            await asyncio.gather(*active_tasks, return_exceptions=True)