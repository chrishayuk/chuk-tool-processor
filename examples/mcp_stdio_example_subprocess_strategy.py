#!/usr/bin/env python
# examples/mcp_stdio_example_subprocess_strategy.py
#!/usr/bin/env python
"""
mcp_stdio_example_subprocess_strategy.py
Demonstrates invoking MCP tools via stdio transport and executing them
with the SubprocessStrategy (true process isolation).

Requires: a “time” MCP server entry in server_config.json using uvx.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

# ────────────────────────────────────────────────────────────────────────────────
#  Local package imports
# ────────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.execution.strategies.subprocess_strategy import (
    SubprocessStrategy,
)
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.registry.provider import ToolRegistryProvider

LOG = get_logger("mcp-subprocess-demo")

# ────────────────────────────────────────────────────────────────────────────────
CONFIG_FILE = "server_config.json"
TIME_SERVER = "time"


# ────────────────────────────────────────────────────────────────────────────────
#  Pretty helpers
# ────────────────────────────────────────────────────────────────────────────────
def header(title: str) -> None:
    print(Fore.CYAN + f"\n=== {title} ===" + Style.RESET_ALL)


def show_result(call: ToolCall, res) -> None:
    """Pretty-print a ToolResult together with its original call."""
    dur = (res.end_time - res.start_time).total_seconds()
    print(
        f"{Fore.YELLOW}{res.tool:24}{Style.RESET_ALL}"
        f"({dur:5.3f}s)\n"
        f"  args   : {json.dumps(call.arguments, indent=2)}\n"
        f"  result : {json.dumps(res.result,   indent=2)}\n"
        f"------------------------------------------------------------"
    )


# ────────────────────────────────────────────────────────────────────────────────
async def bootstrap() -> tuple[ToolExecutor, List[ToolCall]]:
    """Start MCP stdio transport for the *time* server and prep ToolCalls."""
    # Bring up the MCP stdio transport & register remote tools
    processor, sm = await setup_mcp_stdio(
        config_file=CONFIG_FILE,
        servers=[TIME_SERVER],
        server_names={0: TIME_SERVER},
        namespace="stdio",
    )

    # Build some ToolCall objects
    calls = [
        ToolCall(
            tool="get_current_time",
            namespace="stdio",
            arguments={"timezone": tz},
        )
        for tz in [
            "UTC",
            "Europe/Paris",
            "Asia/Kolkata",
            "America/New_York",
        ]
    ]

    # SubprocessStrategy with 4 workers
    registry = await ToolRegistryProvider.get_registry()
    strategy = SubprocessStrategy(registry, max_workers=4, default_timeout=5.0)
    executor = ToolExecutor(registry=registry, strategy=strategy)

    return executor, calls


# ────────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    print("=== MCP Time Tool-Calling Demo  (SubprocessStrategy) ===")

    executor, calls = await bootstrap()

    # ── Run in parallel ───────────────────────────────────────────────────────
    header("Running calls in parallel")
    results = await executor.execute(calls)

    for call, res in zip(calls, results):
        show_result(call, res)

    # Tidy-up
    await executor.strategy.shutdown()


# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
