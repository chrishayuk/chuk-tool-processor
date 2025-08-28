#!/usr/bin/env python
# chuk_tool_processor/execution/tool_executor.py
"""
Modified ToolExecutor with true streaming support and proper timeout handling.

This version accesses streaming tools' stream_execute method directly
to enable true item-by-item streaming behavior, while preventing duplicates.

Proper timeout precedence - respects strategy's default_timeout when available.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface

logger = get_logger("chuk_tool_processor.execution.tool_executor")


class ToolExecutor:
    """
    Async-native executor that selects and uses a strategy for tool execution.

    This class provides a unified interface for executing tools using different
    execution strategies, with special support for streaming tools.

    FIXED: Proper timeout handling that respects strategy's default_timeout.
    """

    def __init__(
        self,
        registry: ToolRegistryInterface | None = None,
        default_timeout: float | None = None,  # Made optional to allow strategy precedence
        strategy: ExecutionStrategy | None = None,
        strategy_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the tool executor.

        Args:
            registry: Tool registry to use for tool lookups
            default_timeout: Default timeout for tool execution (optional)
                           If None, will use strategy's default_timeout if available
            strategy: Optional execution strategy (default: InProcessStrategy)
            strategy_kwargs: Additional arguments for the strategy constructor
        """
        self.registry = registry

        # Create strategy if not provided
        if strategy is None:
            # Lazy import to allow for circular imports
            import chuk_tool_processor.execution.strategies.inprocess_strategy as _inprocess_mod

            if registry is None:
                raise ValueError("Registry must be provided if strategy is not")

            strategy_kwargs = strategy_kwargs or {}

            # If no default_timeout specified, use a reasonable default for the strategy
            strategy_timeout = default_timeout if default_timeout is not None else 30.0

            strategy = _inprocess_mod.InProcessStrategy(
                registry,
                default_timeout=strategy_timeout,
                **strategy_kwargs,
            )

        self.strategy = strategy

        # Set default timeout with proper precedence:
        # 1. Explicit default_timeout parameter
        # 2. Strategy's default_timeout (if available and not None)
        # 3. Fallback to 30.0 seconds
        if default_timeout is not None:
            self.default_timeout = default_timeout
            logger.debug(f"Using explicit default_timeout: {self.default_timeout}s")
        elif hasattr(strategy, "default_timeout") and strategy.default_timeout is not None:
            self.default_timeout = strategy.default_timeout
            logger.debug(f"Using strategy's default_timeout: {self.default_timeout}s")
        else:
            self.default_timeout = 30.0  # Conservative fallback
            logger.debug(f"Using fallback default_timeout: {self.default_timeout}s")

    @property
    def supports_streaming(self) -> bool:
        """Check if this executor supports streaming execution."""
        return hasattr(self.strategy, "supports_streaming") and self.strategy.supports_streaming

    async def execute(
        self,
        calls: list[ToolCall],
        timeout: float | None = None,
        use_cache: bool = True,  # noqa: ARG002
    ) -> list[ToolResult]:
        """
        Execute tool calls using the configured strategy.

        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution (overrides all defaults)
            use_cache: Whether to use cached results (for caching wrappers)

        Returns:
            List of tool results in the same order as calls
        """
        if not calls:
            return []

        # Timeout precedence:
        # 1. Explicit timeout parameter (highest priority)
        # 2. Executor's default_timeout (which already considers strategy's timeout)
        effective_timeout = timeout if timeout is not None else self.default_timeout

        logger.debug(
            f"Executing {len(calls)} tool calls with timeout {effective_timeout}s (explicit: {timeout is not None})"
        )

        # Delegate to the strategy
        return await self.strategy.run(calls, timeout=effective_timeout)

    async def stream_execute(
        self,
        calls: list[ToolCall],
        timeout: float | None = None,
    ) -> AsyncIterator[ToolResult]:
        """
        Execute tool calls and yield results as they become available.

        For streaming tools, this directly accesses their stream_execute method
        to yield individual results as they are produced, rather than collecting
        them into lists.

        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution

        Yields:
            Tool results as they become available
        """
        if not calls:
            return

        # Use the same timeout precedence as execute()
        effective_timeout = timeout if timeout is not None else self.default_timeout

        logger.debug(
            f"Stream executing {len(calls)} tool calls with timeout {effective_timeout}s "
            f"(explicit: {timeout is not None})"
        )

        # There are two possible ways to handle streaming:
        # 1. Use the strategy's stream_run if available
        # 2. Use direct streaming for streaming tools
        # We'll choose one approach based on the tool types to avoid duplicates

        # Check if strategy supports streaming
        if hasattr(self.strategy, "stream_run") and self.strategy.supports_streaming:
            # Check for streaming tools
            streaming_tools = []
            non_streaming_tools = []

            for call in calls:
                # Check if the tool is a streaming tool
                tool_impl = await self.registry.get_tool(call.tool, call.namespace)
                if tool_impl is None:
                    # Tool not found - treat as non-streaming
                    non_streaming_tools.append(call)
                    continue

                # Instantiate if class
                tool = tool_impl() if callable(tool_impl) else tool_impl

                # Check for streaming support
                if hasattr(tool, "supports_streaming") and tool.supports_streaming and hasattr(tool, "stream_execute"):
                    streaming_tools.append((call, tool))
                else:
                    non_streaming_tools.append(call)

            # If we have streaming tools, handle them directly
            if streaming_tools:
                # Create a tracking queue for all results
                queue = asyncio.Queue()

                # Track processing to avoid duplicates
                processed_calls = set()

                # For streaming tools, create direct streaming tasks
                pending_tasks = set()
                for call, tool in streaming_tools:
                    # Add to processed list to avoid duplication
                    processed_calls.add(call.id)

                    # Create task for direct streaming
                    task = asyncio.create_task(self._direct_stream_tool(call, tool, queue, effective_timeout))
                    pending_tasks.add(task)
                    task.add_done_callback(pending_tasks.discard)

                # For non-streaming tools, use the strategy's stream_run
                if non_streaming_tools:

                    async def strategy_streamer():
                        async for result in self.strategy.stream_run(non_streaming_tools, timeout=effective_timeout):
                            await queue.put(result)

                    strategy_task = asyncio.create_task(strategy_streamer())
                    pending_tasks.add(strategy_task)
                    strategy_task.add_done_callback(pending_tasks.discard)

                # Yield results as they arrive in the queue
                while pending_tasks:
                    try:
                        # Wait a short time for a result, then check task status
                        result = await asyncio.wait_for(queue.get(), 0.1)
                        yield result
                    except TimeoutError:
                        # Check if tasks have completed
                        if not pending_tasks:
                            break

                        # Check for completed tasks
                        done, pending_tasks = await asyncio.wait(
                            pending_tasks, timeout=0, return_when=asyncio.FIRST_COMPLETED
                        )

                        # Handle any exceptions
                        for task in done:
                            try:
                                await task
                            except Exception as e:
                                logger.exception(f"Error in streaming task: {e}")
            else:
                # No streaming tools, use the strategy's stream_run for all
                async for result in self.strategy.stream_run(calls, timeout=effective_timeout):
                    yield result
        else:
            # Strategy doesn't support streaming, fall back to executing all at once
            results = await self.execute(calls, timeout=effective_timeout)
            for result in results:
                yield result

    async def _direct_stream_tool(self, call: ToolCall, tool: Any, queue: asyncio.Queue, timeout: float | None) -> None:
        """
        Stream results directly from a streaming tool.

        Args:
            call: Tool call to execute
            tool: Tool instance
            queue: Queue to put results into
            timeout: Optional timeout in seconds
        """
        start_time = datetime.now(UTC)
        machine = "direct-stream"
        pid = 0

        logger.debug(f"Direct streaming {call.tool} with timeout {timeout}s")

        # Create streaming task with timeout
        async def stream_with_timeout():
            try:
                async for result in tool.stream_execute(**call.arguments):
                    # Create a ToolResult for each result
                    end_time = datetime.now(UTC)
                    tool_result = ToolResult(
                        tool=call.tool,
                        result=result,
                        error=None,
                        start_time=start_time,
                        end_time=end_time,
                        machine=machine,
                        pid=pid,
                    )
                    await queue.put(tool_result)
            except Exception as e:
                # Handle errors
                end_time = datetime.now(UTC)
                error_result = ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Streaming error: {str(e)}",
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid,
                )
                await queue.put(error_result)

        try:
            if timeout:
                await asyncio.wait_for(stream_with_timeout(), timeout)
                logger.debug(f"Direct streaming {call.tool} completed within {timeout}s")
            else:
                await stream_with_timeout()
                logger.debug(f"Direct streaming {call.tool} completed (no timeout)")
        except TimeoutError:
            # Handle timeout
            end_time = datetime.now(UTC)
            actual_duration = (end_time - start_time).total_seconds()
            logger.debug(f"Direct streaming {call.tool} timed out after {actual_duration:.3f}s (limit: {timeout}s)")

            timeout_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Streaming timeout after {timeout}s",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid,
            )
            await queue.put(timeout_result)
        except Exception as e:
            # Handle other errors
            end_time = datetime.now(UTC)
            logger.exception(f"Error in direct streaming {call.tool}: {e}")

            error_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Streaming error: {str(e)}",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid,
            )
            await queue.put(error_result)

    async def shutdown(self) -> None:
        """Enhanced shutdown for ToolExecutor with strategy coordination."""
        logger.debug("Finalizing ToolExecutor operations")

        if hasattr(self.strategy, "shutdown") and callable(self.strategy.shutdown):
            try:
                await self.strategy.shutdown()
            except Exception as e:
                logger.debug(f"Strategy finalization completed: {e}")
