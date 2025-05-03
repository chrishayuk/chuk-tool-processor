#!/usr/bin/env python
#!/usr/bin/env python
"""
mcp_stdio_example_calling_usage.py
Demonstrates JSON / XML / function-call parsing, sequential & parallel execution,
timeouts, and colourised results – but routing all calls to the MCP stdio echo server.
"""

import asyncio
import json
import os
import sys
from typing import Any, List

from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

# ----------------------------------------------------- #
#  Project imports                                      #
# ----------------------------------------------------- #
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chuk_tool_processor.logging import get_logger, log_context_span
from chuk_tool_processor.mcp import setup_mcp_stdio
from chuk_tool_processor.registry import ToolRegistryProvider

from chuk_tool_processor.plugins.parsers.json_tool_plugin import JsonToolPlugin
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin
from chuk_tool_processor.plugins.parsers.function_call_tool_plugin import FunctionCallPlugin
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy

logger = get_logger("mcp-demo")

# ----------------------------------------------------- #
#  MCP bootstrap                                        #
# ----------------------------------------------------- #
CONFIG_FILE = "server_config.json"
ECHO_SERVER = "echo"

async def bootstrap_mcp() -> None:
    """Ensure the stdio echo server is configured, started and its tools registered."""
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as fh:
            json.dump(
                {
                    "mcpServers": {
                        ECHO_SERVER: {
                            "command": "uv",
                            "args": [
                                "--directory",
                                "/Users/you/path/to/chuk-mcp-echo-server",
                                "run",
                                "src/chuk_mcp_echo_server/main.py",
                            ],
                        }
                    }
                },
                fh,
            )
        logger.info("Created %s", CONFIG_FILE)

    processor, sm = await setup_mcp_stdio(
        config_file=CONFIG_FILE,
        servers=[ECHO_SERVER],
        server_names={0: ECHO_SERVER},
        namespace="stdio",
    )
    bootstrap_mcp.stream_manager = sm     # type: ignore[attr-defined]

# ----------------------------------------------------- #
#  Parsers / test payloads                              #
# ----------------------------------------------------- #
plugins = [
    (
        "JSON Plugin",
        JsonToolPlugin(),
        json.dumps(
            {"tool_calls": [{"tool": "stdio.echo", "arguments": {"message": "Hello JSON"}}]}
        ),
    ),
    (
        "XML Plugin",
        XmlToolPlugin(),
        '<tool name="stdio.echo" args=\'{"message": "Hello XML"}\'/>',
    ),
    (
        "FunctionCall Plugin",
        FunctionCallPlugin(),
        json.dumps(
            {
                "function_call": {
                    "name": "stdio.echo",
                    "arguments": {"message": "Hello FunctionCall"},
                }
            }
        ),
    ),
]

# ----------------------------------------------------- #
#  Pretty-print helper                                  #
# ----------------------------------------------------- #
def print_results(title: str, calls: List[ToolCall], results: List[ToolResult]) -> None:
    print(Fore.CYAN + f"\n=== {title} ===")
    for call, r in zip(calls, results):
        duration = (r.end_time - r.start_time).total_seconds()
        hdr = (Fore.GREEN if not r.error else Fore.RED) + f"{r.tool} ({duration:.3f}s) [pid:{r.pid}]"
        print(hdr + Style.RESET_ALL)
        print(f"  {Fore.YELLOW}Args:{Style.RESET_ALL}    {call.arguments}")
        if r.error:
            print(f"  {Fore.RED}Error:{Style.RESET_ALL}   {r.error!r}")
        else:
            print(f"  {Fore.MAGENTA}Result:{Style.RESET_ALL}  {r.result!r}")
        print(f"  Started: {r.start_time.isoformat()}")
        print(f"  Finished:{r.end_time.isoformat()}")
        print(f"  Host:    {r.machine}")
        print(Style.DIM + "-" * 60)

# ----------------------------------------------------- #
#  Demo runner                                          #
# ----------------------------------------------------- #
async def run_demo() -> None:
    print(Fore.GREEN + "=== MCP Tool-Calling Demo ===")
    await bootstrap_mcp()

    registry = ToolRegistryProvider.get_registry()
    executor = ToolExecutor(
        registry,
        strategy=InProcessStrategy(registry, default_timeout=2.0, max_concurrency=4),
    )

    # sequential tests
    for title, plugin, raw in plugins:
        calls = plugin.try_parse(raw)
        results = await executor.execute(calls)
        print_results(f"{title} (sequential)", calls, results)

    # parallel echo spam
    print(Fore.CYAN + "\n=== Parallel Echo Tasks ===")
    parallel_calls = [
        ToolCall(tool="stdio.echo", arguments={"message": f"parallel-{i}"}) for i in range(5)
    ]
    tasks = [asyncio.create_task(executor.execute([c]), name=f"echo-{i}") for i, c in enumerate(parallel_calls)]
    for call, task in zip(parallel_calls, tasks):
        try:
            res = await asyncio.wait_for(task, timeout=3.0)
            print_results("Parallel echo", [call], res)
        except asyncio.TimeoutError:
            print(Fore.RED + f"Task {task.get_name()} timed out")

    await bootstrap_mcp.stream_manager.close()        # type: ignore[attr-defined]

# ----------------------------------------------------- #
#  Entry-point                                          #
# ----------------------------------------------------- #
if __name__ == "__main__":
    import logging
    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )
    asyncio.run(run_demo())
