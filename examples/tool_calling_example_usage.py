# tool_calling_example_usage.py
#!/usr/bin/env python
"""
Demonstrates tool registration, parsing with JSON/XML/function-call plugins,
executing with in-process and subprocess strategies, timeouts, sequential and parallel tasks,
and printing colorized results including durations, host info, process IDs, and timeout handling.

Updated to work with the improved tool processor and new project structure.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, List

# Add parent directory to path for imports when running the script directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ANSI colors
from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

# Updated tool processor imports
from chuk_tool_processor.registry.providers.memory import InMemoryToolRegistry
from chuk_tool_processor.registry import ToolRegistryProvider
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy
from chuk_tool_processor.execution.strategies.subprocess_strategy import SubprocessStrategy

from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin
from chuk_tool_processor.plugins.parsers.function_call_tool import FunctionCallPlugin
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.utils.logging import get_logger, log_context_span

# Set up logger
logger = get_logger("example")

# --- Dummy tools ---
class EchoTool:
    """Simple tool that echoes back the input arguments."""
    def execute(self, **kwargs: Any) -> str:
        logger.info(f"EchoTool executing with args: {kwargs}")
        return f"Echo: {kwargs}"

class AsyncComputeTool:
    """Async tool that sums numeric values in the arguments."""
    async def execute(self, **kwargs: Any) -> str:
        logger.info(f"AsyncComputeTool executing with args: {kwargs}")
        await asyncio.sleep(0.1)
        total = sum(v for v in kwargs.values() if isinstance(v, (int, float)))
        return f"Sum: {total}"

class SlowTool:
    """Intentionally slow tool for testing timeouts."""
    async def execute(self, **kwargs: Any) -> str:
        logger.info(f"SlowTool executing with args: {kwargs}")
        await asyncio.sleep(2)
        return "Done"

class ErrorTool:
    """Tool that always raises an exception."""
    def execute(self, **kwargs: Any) -> Any:
        logger.info(f"ErrorTool executing with args: {kwargs}")
        raise RuntimeError("Tool failure occurred")

# --- Common plugins and calls ---
plugins = [
    ("JSON Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "echo", "arguments": {"msg": "Hello JSON"}}]
    })),
    ("XML Plugin", XmlToolPlugin(), '<tool name="compute" args=\'{"a":5,"b":7}\'/>' ),
    ("FunctionCall Plugin", FunctionCallPlugin(), json.dumps({
        "function_call": {"name": "echo", "arguments": {"user": "Alice", "action": "login"}}
    })),
    ("Slow Tool Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "slow", "arguments": {}}]
    })),
    ("Error Tool Plugin", JsonToolPlugin(), json.dumps({
        "tool_calls": [{"tool": "error", "arguments": {}}]
    })),
]

# --- Helper to format and print results ---
def print_results(title: str, calls: List[ToolCall], results: List[ToolResult]):
    print(Fore.CYAN + f"\n=== {title} ===")
    for call, r in zip(calls, results):
        duration = (r.end_time - r.start_time).total_seconds()
        color = Fore.GREEN if not r.error else Fore.RED
        header = color + f"{r.tool} ({duration:.3f}s) [pid:{r.pid}]"
        print(header + Style.RESET_ALL)
        print(f"  {Fore.YELLOW}Args:{Style.RESET_ALL}    {call.arguments}")
        if r.error and r.error.startswith("Timeout"):
            print(f"  {Fore.RED}Timeout:{Style.RESET_ALL}  {r.error}")
        else:
            print(f"  {Fore.MAGENTA}Result:{Style.RESET_ALL}  {r.result!r}")
            if r.error:
                print(f"  {Fore.RED}Error:{Style.RESET_ALL}   {r.error!r}")
        print(f"  Started: {r.start_time.isoformat()}")
        print(f"  Finished:{r.end_time.isoformat()}")
        print(f"  Host:    {r.machine}")
        print(Style.DIM + "-" * 60)

# --- Runner helper ---
async def run_all(executor: ToolExecutor):
    # Test each parser sequentially
    with log_context_span("sequential_tests"):
        for title, plugin, raw in plugins:
            logger.info(f"Testing {title}")
            with log_context_span(f"parse_{title.lower().replace(' ', '_')}"):
                calls = plugin.try_parse(raw)
                logger.info(f"Found {len(calls)} calls: {[call.tool for call in calls]}")
                
            timeout = 0.5 if "Slow Tool Plugin" in title else None
            with log_context_span(f"execute_{title.lower().replace(' ', '_')}"):
                results = await executor.execute(calls, timeout=timeout)
                
            print_results(f"{title} (sequential)", calls, results)
            await asyncio.sleep(0.1)

    # Test parallel execution
    with log_context_span("parallel_tests"):
        print(Fore.CYAN + "\n=== Parallel Echo Tasks ===")
        parallel_calls = [ToolCall(tool="echo", arguments={"i": i}) for i in range(5)]
        tasks = [
            (call, asyncio.create_task(executor.execute([call]), name=f"echo-{i}"))
            for i, call in enumerate(parallel_calls)
        ]
        
        for i, (call, task) in enumerate(tasks):
            with log_context_span(f"parallel_task_{i}"):
                try:
                    results = await asyncio.wait_for(task, timeout=2.0)
                    print(Fore.YELLOW + f"Task {task.get_name()} completed")
                    print_results("Parallel echo result", [call], results)
                except asyncio.TimeoutError:
                    print(Fore.RED + f"Task {task.get_name()} timed out")

# --- Main ---
async def main():
    print(Fore.GREEN + "=== Tool Processor Demo ===")
    
    # Create a registry
    registry = InMemoryToolRegistry()
    
    # Register tools
    logger.info("Registering tools")
    registry.register_tool(EchoTool(), name="echo")
    registry.register_tool(AsyncComputeTool(), name="compute")
    registry.register_tool(SlowTool(), name="slow")
    registry.register_tool(ErrorTool(), name="error")
    
    # Set as global registry
    ToolRegistryProvider.set_registry(registry)
    logger.info(f"Registered tools: {registry.list_tools()}")

    # Test with InProcessStrategy
    with log_context_span("inprocess_strategy_tests"):
        print(Fore.BLUE + "\n--- Using InProcessStrategy ---")
        executor_ip = ToolExecutor(
            registry,
            strategy=InProcessStrategy(
                registry, 
                default_timeout=1.0,
                max_concurrency=4  # Use the new concurrent execution
            )
        )
        await run_all(executor_ip)

    # Test with SubprocessStrategy
    with log_context_span("subprocess_strategy_tests"):
        print(Fore.BLUE + "\n--- Using SubprocessStrategy ---")
        try:
            executor_sp = ToolExecutor(
                registry,
                strategy=SubprocessStrategy(registry, max_workers=4, default_timeout=1.0)
            )
            await run_all(executor_sp)
        except Exception as e:
            logger.error(f"SubprocessStrategy error: {str(e)}", exc_info=True)
            print(Fore.RED + "SubprocessStrategy demo skipped due to error:", str(e))

if __name__ == "__main__":
    # Configure logging level from environment
    import os
    import logging
    log_level = os.environ.get("LOGLEVEL", "INFO").upper()
    logging.getLogger("chuk_tool_processor").setLevel(getattr(logging, log_level))
    
    # Run the demo
    asyncio.run(main())