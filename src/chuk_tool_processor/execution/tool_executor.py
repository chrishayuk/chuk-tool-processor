#!/usr/bin/env python
# chuk_tool_processor/execution/tool_executor.py
"""
Modified ToolExecutor with true streaming support and duplicate prevention.

This version accesses streaming tools' stream_execute method directly
to enable true item-by-item streaming behavior, while preventing duplicates.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, AsyncIterator, Set

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.tool_executor")


class ToolExecutor:
    """
    Async-native executor that selects and uses a strategy for tool execution.
    
    This class provides a unified interface for executing tools using different
    execution strategies, with special support for streaming tools.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistryInterface] = None,
        default_timeout: float = 10.0,
        strategy: Optional[ExecutionStrategy] = None,
        strategy_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the tool executor.
        
        Args:
            registry: Tool registry to use for tool lookups
            default_timeout: Default timeout for tool execution
            strategy: Optional execution strategy (default: InProcessStrategy)
            strategy_kwargs: Additional arguments for the strategy constructor
        """
        self.registry = registry
        self.default_timeout = default_timeout
        
        # Create strategy if not provided
        if strategy is None:
            # Lazy import to allow for circular imports
            import chuk_tool_processor.execution.strategies.inprocess_strategy as _inprocess_mod
            
            if registry is None:
                raise ValueError("Registry must be provided if strategy is not")
                
            strategy_kwargs = strategy_kwargs or {}
            strategy = _inprocess_mod.InProcessStrategy(
                registry,
                default_timeout=default_timeout,
                **strategy_kwargs,
            )
            
        self.strategy = strategy

    @property
    def supports_streaming(self) -> bool:
        """Check if this executor supports streaming execution."""
        return hasattr(self.strategy, "supports_streaming") and self.strategy.supports_streaming

    async def execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        """
        Execute tool calls using the configured strategy.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for execution (overrides default_timeout)
            use_cache: Whether to use cached results (for caching wrappers)
            
        Returns:
            List of tool results in the same order as calls
        """
        if not calls:
            return []
            
        # Use the provided timeout or fall back to default
        effective_timeout = timeout if timeout is not None else self.default_timeout
        
        logger.debug(f"Executing {len(calls)} tool calls with timeout {effective_timeout}s")
        
        # Delegate to the strategy
        return await self.strategy.run(calls, timeout=effective_timeout)
        
    async def stream_execute(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
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
            
        # Use the provided timeout or fall back to default
        effective_timeout = timeout if timeout is not None else self.default_timeout
        
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
                    task = asyncio.create_task(self._direct_stream_tool(
                        call, tool, queue, effective_timeout
                    ))
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
                    except asyncio.TimeoutError:
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
                
    async def _direct_stream_tool(
        self,
        call: ToolCall,
        tool: Any,
        queue: asyncio.Queue,
        timeout: Optional[float]
    ) -> None:
        """
        Stream results directly from a streaming tool.
        
        Args:
            call: Tool call to execute
            tool: Tool instance
            queue: Queue to put results into
            timeout: Optional timeout in seconds
        """
        start_time = datetime.now(timezone.utc)
        machine = "direct-stream"
        pid = 0
        
        # Create streaming task with timeout
        async def stream_with_timeout():
            try:
                async for result in tool.stream_execute(**call.arguments):
                    # Create a ToolResult for each result
                    end_time = datetime.now(timezone.utc)
                    tool_result = ToolResult(
                        tool=call.tool,
                        result=result,
                        error=None,
                        start_time=start_time,
                        end_time=end_time,
                        machine=machine,
                        pid=pid
                    )
                    await queue.put(tool_result)
            except Exception as e:
                # Handle errors
                end_time = datetime.now(timezone.utc)
                error_result = ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Streaming error: {str(e)}",
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid
                )
                await queue.put(error_result)
                
        try:
            if timeout:
                await asyncio.wait_for(stream_with_timeout(), timeout)
            else:
                await stream_with_timeout()
        except asyncio.TimeoutError:
            # Handle timeout
            end_time = datetime.now(timezone.utc)
            timeout_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Streaming timeout after {timeout}s",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )
            await queue.put(timeout_result)
        except Exception as e:
            # Handle other errors
            end_time = datetime.now(timezone.utc)
            error_result = ToolResult(
                tool=call.tool,
                result=None,
                error=f"Streaming error: {str(e)}",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )
            await queue.put(error_result)
                
    async def shutdown(self) -> None:
        """
        Gracefully shut down the executor and any resources used by the strategy.
        
        This should be called during application shutdown to ensure proper cleanup.
        """
        if hasattr(self.strategy, "shutdown") and callable(self.strategy.shutdown):
            await self.strategy.shutdown()