# chuk_tool_processor/execution/strategies/subprocess_strategy.py
"""
Subprocess execution strategy - truly runs tools in separate OS processes.

This strategy executes tools in separate Python processes using a process pool,
providing isolation and potentially better parallelism on multi-core systems.

FIXED: Ensures consistent timeout handling across all execution paths.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import inspect
import os
import pickle
import signal
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Set

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.logging import get_logger, log_context_span

logger = get_logger("chuk_tool_processor.execution.subprocess_strategy")


# --------------------------------------------------------------------------- #
# Module-level helper functions for worker processes - these must be at the module
# level so they can be pickled
# --------------------------------------------------------------------------- #
def _init_worker():
    """Initialize worker process with signal handlers."""
    # Ignore keyboard interrupt in workers
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    

def _pool_test_func():
    """Simple function to test if the process pool is working."""
    return "ok"


def _process_worker(
    tool_name: str,
    namespace: str,
    module_name: str,
    class_name: str,
    arguments: Dict[str, Any],
    timeout: Optional[float]
) -> Dict[str, Any]:
    """
    Worker function that runs in a separate process.
    
    Args:
        tool_name: Name of the tool
        namespace: Namespace of the tool
        module_name: Module containing the tool class
        class_name: Name of the tool class
        arguments: Arguments to pass to the tool
        timeout: Optional timeout in seconds
        
    Returns:
        Serialized result data
    """
    import asyncio
    import importlib
    import inspect
    import os
    import sys
    import time
    from datetime import datetime, timezone
    
    start_time = datetime.now(timezone.utc)
    pid = os.getpid()
    hostname = os.uname().nodename
    
    # Data for the result
    result_data = {
        "tool": tool_name,
        "namespace": namespace,
        "start_time": start_time.isoformat(),
        "end_time": None,
        "machine": hostname,
        "pid": pid,
        "result": None,
        "error": None,
    }
    
    try:
        # Import the module
        if not module_name or not class_name:
            raise ValueError("Missing module or class name")
            
        # Import the module
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            result_data["error"] = f"Failed to import module {module_name}: {str(e)}"
            result_data["end_time"] = datetime.now(timezone.utc).isoformat()
            return result_data
            
        # Get the class or function
        try:
            tool_class = getattr(module, class_name)
        except AttributeError as e:
            result_data["error"] = f"Failed to find {class_name} in {module_name}: {str(e)}"
            result_data["end_time"] = datetime.now(timezone.utc).isoformat()
            return result_data
            
        # Instantiate the tool
        tool_instance = tool_class() if inspect.isclass(tool_class) else tool_class

        # Find the execute method
        if hasattr(tool_instance, "_aexecute") and inspect.iscoroutinefunction(
            getattr(tool_instance.__class__, "_aexecute", None)
        ):
            execute_fn = tool_instance._aexecute
        elif hasattr(tool_instance, "execute") and inspect.iscoroutinefunction(
            getattr(tool_instance.__class__, "execute", None)
        ):
            execute_fn = tool_instance.execute
        else:
            result_data["error"] = "Tool must have an async execute or _aexecute method"
            result_data["end_time"] = datetime.now(timezone.utc).isoformat()
            return result_data
            
        # Create a new event loop for this process
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Execute the tool with timeout
            if timeout is not None and timeout > 0:
                result_value = loop.run_until_complete(
                    asyncio.wait_for(execute_fn(**arguments), timeout)
                )
            else:
                result_value = loop.run_until_complete(execute_fn(**arguments))
                
            # Store the result
            result_data["result"] = result_value
            
        except asyncio.TimeoutError:
            result_data["error"] = f"Execution timed out after {timeout}s"
        except Exception as e:
            result_data["error"] = f"Error during execution: {str(e)}"
            
        finally:
            # Clean up the loop
            loop.close()
            
    except Exception as e:
        # Catch any other exceptions
        result_data["error"] = f"Unexpected error: {str(e)}"
        
    # Set end time
    result_data["end_time"] = datetime.now(timezone.utc).isoformat()
    return result_data


# --------------------------------------------------------------------------- #
# The subprocess strategy
# --------------------------------------------------------------------------- #
class SubprocessStrategy(ExecutionStrategy):
    """
    Execute tools in separate processes for isolation and parallelism.
    
    This strategy creates a pool of worker processes and distributes tool calls
    among them. Each tool executes in its own process, providing isolation and
    parallelism.
    """

    def __init__(
        self,
        registry: ToolRegistryInterface,
        *,
        max_workers: int = 4,
        default_timeout: Optional[float] = None,
        worker_init_timeout: float = 5.0,
    ) -> None:
        """
        Initialize the subprocess execution strategy.
        
        Args:
            registry: Tool registry for tool lookups
            max_workers: Maximum number of worker processes
            default_timeout: Default timeout for tool execution
            worker_init_timeout: Timeout for worker process initialization
        """
        self.registry = registry
        self.max_workers = max_workers
        self.default_timeout = default_timeout or 30.0  # Always have a default
        self.worker_init_timeout = worker_init_timeout
        
        # Process pool (initialized lazily)
        self._process_pool: Optional[concurrent.futures.ProcessPoolExecutor] = None
        self._pool_lock = asyncio.Lock()
        
        # Task tracking for cleanup
        self._active_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        self._shutting_down = False
        
        logger.debug("SubprocessStrategy initialized with timeout: %ss, max_workers: %d", 
                    self.default_timeout, max_workers)
        
        # Register shutdown handler if in main thread
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(self._signal_handler(s))
                )
        except (RuntimeError, NotImplementedError):
            # Not in the main thread or not on Unix
            pass

    async def _ensure_pool(self) -> None:
        """Initialize the process pool if not already initialized."""
        if self._process_pool is not None:
            return
            
        async with self._pool_lock:
            if self._process_pool is not None:
                return
                
            # Create process pool
            self._process_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=self.max_workers,
                initializer=_init_worker,
            )
            
            # Test the pool with a simple task
            loop = asyncio.get_running_loop()
            try:
                # Use a module-level function instead of a lambda
                await asyncio.wait_for(
                    loop.run_in_executor(self._process_pool, _pool_test_func),
                    timeout=self.worker_init_timeout
                )
                logger.info("Process pool initialized with %d workers", self.max_workers)
            except Exception as e:
                # Clean up on initialization error
                self._process_pool.shutdown(wait=False)
                self._process_pool = None
                logger.error("Failed to initialize process pool: %s", e)
                raise RuntimeError(f"Failed to initialize process pool: {e}") from e
    
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
    
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """
        Execute tool calls in separate processes.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for each execution (overrides default)
            
        Returns:
            List of tool results in the same order as calls
        """
        if not calls:
            return []
            
        if self._shutting_down:
            # Return early with error results if shutting down
            return [
                ToolResult(
                    tool=call.tool,
                    result=None,
                    error="System is shutting down",
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
                for call in calls
            ]
        
        # Use default_timeout if no timeout specified
        effective_timeout = timeout if timeout is not None else self.default_timeout
        logger.debug("Executing %d calls in subprocesses with %ss timeout each", len(calls), effective_timeout)
            
        # Create tasks for each call
        tasks = []
        for call in calls:
            task = asyncio.create_task(self._execute_single_call(
                call, effective_timeout  # Always pass concrete timeout
            ))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            tasks.append(task)
            
        # Execute all tasks concurrently
        async with log_context_span("subprocess_execution", {"num_calls": len(calls)}):
            return await asyncio.gather(*tasks)

    async def stream_run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> AsyncIterator[ToolResult]:
        """
        Execute tool calls and yield results as they become available.
        
        Args:
            calls: List of tool calls to execute
            timeout: Optional timeout for each execution
            
        Yields:
            Tool results as they complete (not necessarily in order)
        """
        if not calls:
            return
            
        if self._shutting_down:
            # Yield error results if shutting down
            for call in calls:
                yield ToolResult(
                    tool=call.tool,
                    result=None,
                    error="System is shutting down",
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
            return
        
        # Use default_timeout if no timeout specified
        effective_timeout = timeout if timeout is not None else self.default_timeout
            
        # Create a queue for results
        queue = asyncio.Queue()
        
        # Start all executions and have them put results in the queue
        pending = set()
        for call in calls:
            task = asyncio.create_task(self._execute_to_queue(
                call, queue, effective_timeout  # Always pass concrete timeout
            ))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            pending.add(task)
            
        # Yield results as they become available
        while pending:
            # Get next result from queue
            result = await queue.get()
            yield result
            
            # Check for completed tasks
            done, pending = await asyncio.wait(
                pending, timeout=0, return_when=asyncio.FIRST_COMPLETED
            )
            
            # Handle any exceptions
            for task in done:
                try:
                    await task
                except Exception as e:
                    logger.exception("Error in task: %s", e)

    async def _execute_to_queue(
        self,
        call: ToolCall,
        queue: asyncio.Queue,
        timeout: float,  # Make timeout required
    ) -> None:
        """Execute a single call and put the result in the queue."""
        result = await self._execute_single_call(call, timeout)
        await queue.put(result)

    async def _execute_single_call(
        self,
        call: ToolCall,
        timeout: float,  # Make timeout required
    ) -> ToolResult:
        """
        Execute a single tool call in a separate process.
        
        Args:
            call: Tool call to execute
            timeout: Timeout in seconds (required)
            
        Returns:
            Tool execution result
        """
        start_time = datetime.now(timezone.utc)
        
        logger.debug("Executing %s in subprocess with %ss timeout", call.tool, timeout)
        
        try:
            # Ensure pool is initialized
            await self._ensure_pool()
            
            # Get tool from registry
            tool_impl = await self.registry.get_tool(call.tool, call.namespace)
            if tool_impl is None:
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Tool '{call.tool}' not found",
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
                
            # Get module and class names for import in worker process
            if inspect.isclass(tool_impl):
                module_name = tool_impl.__module__
                class_name = tool_impl.__name__
            else:
                module_name = tool_impl.__class__.__module__
                class_name = tool_impl.__class__.__name__
            
            # Execute in subprocess
            loop = asyncio.get_running_loop()
            
            # Add safety timeout to handle process crashes (tool timeout + buffer)
            safety_timeout = timeout + 5.0
            
            try:
                result_data = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._process_pool,
                        functools.partial(
                            _process_worker, 
                            call.tool, 
                            call.namespace,
                            module_name, 
                            class_name, 
                            call.arguments, 
                            timeout  # Pass the actual timeout to worker
                        )
                    ),
                    timeout=safety_timeout
                )
                
                # Parse timestamps
                if isinstance(result_data["start_time"], str):
                    start_time_str = result_data["start_time"]
                    result_data["start_time"] = datetime.fromisoformat(start_time_str)
                    
                if isinstance(result_data["end_time"], str):
                    end_time_str = result_data["end_time"]
                    result_data["end_time"] = datetime.fromisoformat(end_time_str)
                
                end_time = datetime.now(timezone.utc)
                actual_duration = (end_time - start_time).total_seconds()
                
                if result_data.get("error"):
                    logger.debug("%s subprocess failed after %.3fs: %s", 
                               call.tool, actual_duration, result_data["error"])
                else:
                    logger.debug("%s subprocess completed in %.3fs (limit: %ss)", 
                               call.tool, actual_duration, timeout)
                
                # Create ToolResult from worker data
                return ToolResult(
                    tool=result_data.get("tool", call.tool),
                    result=result_data.get("result"),
                    error=result_data.get("error"),
                    start_time=result_data.get("start_time", start_time),
                    end_time=result_data.get("end_time", end_time),
                    machine=result_data.get("machine", os.uname().nodename),
                    pid=result_data.get("pid", os.getpid()),
                )
                
            except asyncio.TimeoutError:
                # This happens if the worker process itself hangs
                end_time = datetime.now(timezone.utc)
                actual_duration = (end_time - start_time).total_seconds()
                logger.debug("%s subprocess timed out after %.3fs (safety limit: %ss)", 
                           call.tool, actual_duration, safety_timeout)
                
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error=f"Worker process timed out after {safety_timeout}s",
                    start_time=start_time,
                    end_time=end_time,
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
                
            except concurrent.futures.process.BrokenProcessPool:
                # Process pool broke - need to recreate it
                logger.error("Process pool broke during execution - recreating")
                if self._process_pool:
                    self._process_pool.shutdown(wait=False)
                    self._process_pool = None
                    
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error="Worker process crashed",
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    machine=os.uname().nodename,
                    pid=os.getpid(),
                )
                
        except asyncio.CancelledError:
            # Handle cancellation
            logger.debug("%s subprocess was cancelled", call.tool)
            return ToolResult(
                tool=call.tool,
                result=None,
                error="Execution was cancelled",
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                machine=os.uname().nodename,
                pid=os.getpid(),
            )
            
        except Exception as e:
            # Handle any other errors
            logger.exception("Error executing %s in subprocess: %s", call.tool, e)
            end_time = datetime.now(timezone.utc)
            actual_duration = (end_time - start_time).total_seconds()
            logger.debug("%s subprocess setup failed after %.3fs: %s", 
                       call.tool, actual_duration, e)
            
            return ToolResult(
                tool=call.tool,
                result=None,
                error=f"Error: {str(e)}",
                start_time=start_time,
                end_time=end_time,
                machine=os.uname().nodename,
                pid=os.getpid(),
            )

    @property
    def supports_streaming(self) -> bool:
        """Check if this strategy supports streaming execution."""
        return True
        
    async def _signal_handler(self, sig: int) -> None:
        """Handle termination signals."""
        signame = signal.Signals(sig).name
        logger.info("Received %s, shutting down process pool", signame)
        await self.shutdown()
        
    async def shutdown(self) -> None:
        """
        Gracefully shut down the process pool.
        
        This cancels all active tasks and shuts down the process pool.
        """
        if self._shutting_down:
            return
            
        self._shutting_down = True
        self._shutdown_event.set()
        
        # Cancel all active tasks
        active_tasks = list(self._active_tasks)
        if active_tasks:
            logger.info("Cancelling %d active tool executions", len(active_tasks))
            for task in active_tasks:
                task.cancel()
                
            # Wait for all tasks to complete (with cancellation)
            await asyncio.gather(*active_tasks, return_exceptions=True)
            
        # Shut down the process pool
        if self._process_pool:
            logger.info("Shutting down process pool")
            self._process_pool.shutdown(wait=True)
            self._process_pool = None