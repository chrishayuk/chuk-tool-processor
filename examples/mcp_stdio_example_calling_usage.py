#!/usr/bin/env python
"""
mcp_stdio_example_calling_usage.py
──────────────────────────────────
Showcases three parser plugins (JSON, XML, Function-call) invoking the
remote **time** MCP server through stdio transport.

It also fires a handful of parallel calls to demonstrate concurrency.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import logging
from pathlib import Path
from typing import Any, List, Tuple

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

# ═══════════════════════════════════════════════════════════════════════════
# Fix for CancelledError during asyncio shutdown
# ═══════════════════════════════════════════════════════════════════════════

def setup_asyncio_cleanup():
    """Setup proper asyncio cleanup to prevent CancelledError warnings."""
    def handle_exception(loop, context):
        exception = context.get('exception')
        if isinstance(exception, asyncio.CancelledError):
            # Silently ignore CancelledError during shutdown
            return
        
        # Log other exceptions normally
        loop.default_exception_handler(context)
    
    # Set the exception handler for the current event loop
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(handle_exception)
    except RuntimeError:
        # No running loop yet, will set later
        pass

# Apply the fix
setup_asyncio_cleanup()

# Also suppress asyncio logger for CancelledError
logging.getLogger('asyncio').setLevel(logging.CRITICAL)

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.logging import get_logger                                  # noqa: E402
from chuk_tool_processor.registry.provider import ToolRegistryProvider             # noqa: E402
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio                # noqa: E402

# parsers
from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin           # noqa: E402
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin             # noqa: E402
from chuk_tool_processor.plugins.parsers.function_call_tool import (               # noqa: E402
    FunctionCallPlugin,
)

# executor
from chuk_tool_processor.execution.tool_executor import ToolExecutor               # noqa: E402
from chuk_tool_processor.execution.strategies.inprocess_strategy import (          # noqa: E402
    InProcessStrategy,
)

from chuk_tool_processor.models.tool_call import ToolCall                          # noqa: E402
from chuk_tool_processor.models.tool_result import ToolResult                      # noqa: E402

logger = get_logger("mcp-time-demo")

# ─── config / bootstrap ─────────────────────────────────────────────────────
CONFIG_FILE = PROJECT_ROOT / "server_config.json"
TIME_SERVER = "time"
NAMESPACE = "stdio"          # where remote tools will be registered


async def bootstrap_mcp() -> None:
    """Ensure a *time* server entry exists & start the stdio transport."""
    if not CONFIG_FILE.exists():
        cfg = {
            "mcpServers": {
                TIME_SERVER: {
                    "command": "uvx",
                    "args": ["mcp-server-time", "--local-timezone=America/New_York"],
                }
            }
        }
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        logger.info("Created demo config %s", CONFIG_FILE)

    _, sm = await setup_mcp_stdio(
        config_file=str(CONFIG_FILE),
        servers=[TIME_SERVER],
        server_names={0: TIME_SERVER},
        namespace=NAMESPACE,
    )

    # keep for shutdown
    bootstrap_mcp.stream_manager = sm  # type: ignore[attr-defined]


# ─── payloads & parsers (all call get_current_time) ─────────────────────────
PLUGINS: List[Tuple[str, Any, str]] = [
    (
        "JSON Plugin",
        JsonToolPlugin(),
        json.dumps(
            {
                "tool_calls": [
                    {
                        "tool": f"{NAMESPACE}.get_current_time",
                        "arguments": {"timezone": "Europe/London"},
                    }
                ]
            }
        ),
    ),
    (
        "XML Plugin",
        XmlToolPlugin(),
        f'<tool name="{NAMESPACE}.get_current_time" '
        'args=\'{"timezone": "Asia/Tokyo"}\'/>',
    ),
    (
        "FunctionCall Plugin",
        FunctionCallPlugin(),
        json.dumps(
            {
                "function_call": {
                    "name": f"{NAMESPACE}.get_current_time",
                    "arguments": {"timezone": "America/Los_Angeles"},
                }
            }
        ),
    ),
]


# ─── helpers ────────────────────────────────────────────────────────────────
def banner(text: str, colour: str = Fore.CYAN) -> None:
    print(colour + f"\n=== {text} ===" + Style.RESET_ALL)


def show_results(title: str, calls: List[ToolCall], results: List[ToolResult]) -> None:
    banner(title)
    for call, res in zip(calls, results):
        ok = res.error is None
        head_colour = Fore.GREEN if ok else Fore.RED
        duration = (res.end_time - res.start_time).total_seconds()
        print(f"{head_colour}{res.tool}  ({duration:.3f}s){Style.RESET_ALL}")
        print(Fore.YELLOW + "  args   :" + Style.RESET_ALL, call.arguments)
        if ok:
            print(Fore.MAGENTA + "  result :" + Style.RESET_ALL, res.result)
        else:
            print(Fore.RED + "  error  :" + Style.RESET_ALL, res.error)
        print(Style.DIM + "-" * 60)


async def graceful_shutdown():
    """Perform graceful shutdown of all async tasks."""
    try:
        # Close the stream manager if it exists
        if hasattr(bootstrap_mcp, 'stream_manager'):
            try:
                await bootstrap_mcp.stream_manager.close()
                logger.debug("Stream manager closed successfully")
            except asyncio.CancelledError:
                logger.debug("Stream manager close cancelled during shutdown")
            except Exception as e:
                logger.error(f"Error closing stream manager: {e}")
        
        # Don't wait or cancel tasks during shutdown - let asyncio.run() handle it
        logger.debug("Graceful shutdown completed")
    
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")


# ─── main demo ──────────────────────────────────────────────────────────────
async def run_demo() -> None:
    print(Fore.GREEN + "=== MCP Time Tool-Calling Demo ===" + Style.RESET_ALL)

    # Setup asyncio exception handler for this loop
    loop = asyncio.get_running_loop()
    
    def handle_exception(loop, context):
        exception = context.get('exception')
        if isinstance(exception, asyncio.CancelledError):
            return  # Ignore CancelledError
        loop.default_exception_handler(context)
    
    loop.set_exception_handler(handle_exception)

    try:
        await bootstrap_mcp()

        registry = await ToolRegistryProvider.get_registry()

        executor = ToolExecutor(
            registry,
            strategy=InProcessStrategy(
                registry,
                default_timeout=5.0,
                max_concurrency=4,
            ),
        )

        # sequential examples --------------------------------------------------
        for title, plugin, raw in PLUGINS:
            # new parser API is async
            calls = await plugin.try_parse(raw)
            results = await executor.execute(calls)
            show_results(f"{title} → sequential", calls, results)

        # parallel demo --------------------------------------------------------
        banner("Parallel current-time calls")

        parallel_calls = [
            ToolCall(
                tool=f"{NAMESPACE}.get_current_time",
                arguments={"timezone": tz},
            )
            for tz in ["UTC", "Europe/Paris", "Asia/Kolkata", "America/New_York"]
        ]

        parallel_results = await executor.execute(parallel_calls)
        show_results("Parallel run", parallel_calls, parallel_results)

    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}")
        raise
    finally:
        # Always perform graceful shutdown
        await graceful_shutdown()


def main():
    """Main entry point with proper error handling."""
    # Set up logging
    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )
    
    try:
        # Run the demo with proper cleanup
        asyncio.run(run_demo())
        print(Fore.GREEN + "\n✅ Demo completed successfully!" + Style.RESET_ALL)
    
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n👋 Demo interrupted by user. Goodbye!" + Style.RESET_ALL)
    
    except Exception as e:
        print(Fore.RED + f"\n❌ Demo failed: {e}" + Style.RESET_ALL)
        logger.error(f"Demo failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()