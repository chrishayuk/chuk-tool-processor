# chuk_tool_processor/execution/inprocess_strategy.py
import asyncio
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.core.exceptions import ToolNotFoundError, ToolTimeoutError, ToolExecutionError
from chuk_tool_processor.utils.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.inprocess_strategy")

class InProcessStrategy(ExecutionStrategy):
    """
    In-process execution strategy with concurrent execution support.
    """
    def __init__(
        self, 
        registry: ToolRegistryInterface, 
        default_timeout: Optional[float] = None,
        max_concurrency: Optional[int] = None
    ):
        """
        Initialize the strategy.
        
        Args:
            registry: Tool registry to look up tools.
            default_timeout: Default timeout for tool executions.
            max_concurrency: Maximum number of concurrent tool executions (default: None = unlimited).
        """
        self.registry = registry
        self.default_timeout = default_timeout
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute tool calls concurrently with timeout.
        
        Args:
            calls: List of tool calls to execute.
            timeout: Optional timeout that overrides the default.
            
        Returns:
            List of tool results in the same order as the calls.
        """
        # Create tasks for each call
        tasks = []
        for call in calls:
            task = self._execute_single_call(call, timeout if timeout is not None else self.default_timeout)
            tasks.append(task)
        
        # Run all tasks concurrently and gather results
        results = await asyncio.gather(*tasks)
        return results

    async def _execute_single_call(
        self, 
        call: ToolCall, 
        timeout: Optional[float]
    ) -> ToolResult:
        """
        Execute a single tool call with timeout.
        
        Args:
            call: Tool call to execute.
            timeout: Optional timeout in seconds.
            
        Returns:
            Tool result with execution metadata.
        """
        # Get execution metadata
        pid = os.getpid()
        machine = os.uname().nodename
        start_time = datetime.now(timezone.utc)
        
        # Look up the tool
        tool_impl = self.registry.get_tool(call.tool)
        if not tool_impl:
            end_time = datetime.now(timezone.utc)
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Tool not found",  # Keep this message exactly as "Tool not found" for test compatibility
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )
        
        # Execute with concurrency control if needed
        try:
            if self._semaphore:
                async with self._semaphore:
                    return await self._run_with_timeout(tool_impl, call, timeout, start_time, machine, pid)
            else:
                return await self._run_with_timeout(tool_impl, call, timeout, start_time, machine, pid)
        except Exception as e:
            # Catch any uncaught exceptions
            end_time = datetime.now(timezone.utc)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Unexpected error: {str(e)}",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )

    async def _run_with_timeout(
        self,
        tool_impl: Any,
        call: ToolCall,
        timeout: Optional[float],
        start_time: datetime,
        machine: str,
        pid: int
    ) -> ToolResult:
        """
        Execute a tool with timeout handling.
        """
        try:
            # Determine if we need to instantiate the tool
            # If tool_impl is a class (not an instance), instantiate it
            if isinstance(tool_impl, type):
                tool_instance = tool_impl()
            else:
                tool_instance = tool_impl
                
            # Get the tool metadata to check if it's async
            metadata = self.registry.get_metadata(call.tool) if hasattr(self.registry, "get_metadata") else None
            is_async = metadata.is_async if metadata else asyncio.iscoroutinefunction(tool_instance.execute)
            
            # Call the tool implementation
            if is_async:
                # Direct async call
                if timeout:
                    result_value = await asyncio.wait_for(
                        tool_instance.execute(**call.arguments), 
                        timeout
                    )
                else:
                    result_value = await tool_instance.execute(**call.arguments)
            else:
                # Run sync function in executor
                loop = asyncio.get_running_loop()
                if timeout:
                    result_value = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, 
                            lambda: tool_instance.execute(**call.arguments)
                        ),
                        timeout
                    )
                else:
                    result_value = await loop.run_in_executor(
                        None,
                        lambda: tool_instance.execute(**call.arguments)
                    )
            
            # Create successful result
            end_time = datetime.now(timezone.utc)
            return ToolResult(
                tool=call.tool,
                result=result_value,
                error=None,
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )
            
        except asyncio.TimeoutError:
            # Handle timeout
            end_time = datetime.now(timezone.utc)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Timeout after {timeout}s",
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )
            
        except Exception as e:
            # Handle execution error
            end_time = datetime.now(timezone.utc)
            return ToolResult(
                tool=call.tool,
                result=None,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                machine=machine,
                pid=pid
            )