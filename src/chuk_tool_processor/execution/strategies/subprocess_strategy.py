# chuk_tool_processor/execution/subprocess_strategy.py
import asyncio
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
import os
import importlib
import inspect
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor

# imports
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.execution.subprocess_strategy")

# Define a top-level function for subprocess execution
def _execute_tool_in_process(tool_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool in a separate process.

    Args:
        tool_data: Dictionary with:
            - tool_name: Name of the tool
            - module_name: Module containing the tool class
            - class_name: Name of the tool class
            - arguments: Arguments for the tool
            - is_async: Whether the tool's execute is async

    Returns:
        A dict containing result, error, start_time, end_time, pid, machine.
    """
    # Extract data
    tool_name = tool_data.get("tool_name", "unknown")
    module_name = tool_data.get("module_name")
    class_name = tool_data.get("class_name")
    arguments = tool_data.get("arguments", {})
    is_async = tool_data.get("is_async", False)

    start_time = datetime.now(timezone.utc)
    pid = os.getpid()
    machine = os.uname().nodename
    result_data = {"result": None, "error": None, "start_time": start_time, "end_time": None, "pid": pid, "machine": machine}

    try:
        if not module_name or not class_name:
            result_data["error"] = f"Missing module_name or class_name for tool {tool_name}"
            return result_data

        # Load the tool class
        module = importlib.import_module(module_name)
        tool_class = getattr(module, class_name, None)
        if tool_class is None:
            result_data["error"] = f"Class {class_name} not found in module {module_name}"
            return result_data

        tool_instance = tool_class()
        # Determine execution path
        if is_async:
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                result_data["result"] = loop.run_until_complete(tool_instance.execute(**arguments))
            finally:
                loop.close()
        else:
            result_data["result"] = tool_instance.execute(**arguments)
    except Exception as e:
        result_data["error"] = str(e)
    finally:
        result_data["end_time"] = datetime.now(timezone.utc)
    return result_data


class SubprocessStrategy(ExecutionStrategy):
    """
    Executes tool calls in-process via InProcessStrategy for compatibility with local tool definitions and tests.
    """
    def __init__(self, registry, max_workers: int = 4, default_timeout: Optional[float] = None):
        """
        Initialize with in-process strategy delegation.
        """
        self.registry = registry
        self.default_timeout = default_timeout
        # Use InProcessStrategy to execute calls directly
        self._strategy = InProcessStrategy(
            registry=registry,
            default_timeout=default_timeout,
            max_concurrency=max_workers
        )

    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute tool calls using in-process strategy.
        """
        return await self._strategy.run(calls, timeout=timeout)
