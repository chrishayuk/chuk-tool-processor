#!/usr/bin/env python
"""
mcp_http_streamable_example_calling_usage.py
────────────────────────────────────────────
Showcases three parser plugins (JSON, XML, Function-call) invoking
HTTP Streamable tools through a test MCP HTTP Streamable server.

Prerequisites:
- Run the test server first: python examples/mcp_streamable_http_server.py
- Server provides HTTP Streamable tools for demonstration

This uses the modern MCP Streamable HTTP transport (spec 2025-03-26)
which replaces the deprecated SSE transport.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.logging import get_logger                                  # noqa: E402
from chuk_tool_processor.registry.provider import ToolRegistryProvider             # noqa: E402
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable  # noqa: E402

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

logger = get_logger("mcp-http-streamable-demo")

# ─── config / bootstrap ─────────────────────────────────────────────────────
HTTP_SERVER_URL = "http://localhost:8000"
SERVER_NAME = "http_streamable_server"
NAMESPACE = "http"          # where remote tools will be registered


async def bootstrap_mcp() -> None:
    """Start the HTTP Streamable transport and connect to the mock test server."""
    try:
        print("🔄 Connecting to mock MCP HTTP Streamable server...")
        _, sm = await setup_mcp_http_streamable(
            servers=[
                {
                    "name": SERVER_NAME,
                    "url": HTTP_SERVER_URL,
                }
            ],
            server_names={0: SERVER_NAME},
            namespace=NAMESPACE,
        )
        
        # keep for shutdown
        bootstrap_mcp.stream_manager = sm  # type: ignore[attr-defined]
        print("✅ Connected to mock HTTP Streamable server successfully!")
        
    except Exception as e:
        logger.error(f"Failed to bootstrap MCP HTTP Streamable: {e}")
        print(f"❌ Could not connect to mock HTTP Streamable server at {HTTP_SERVER_URL}")
        print("Please start the test server first:")
        print("   python examples/mcp_streamable_http_server.py")
        raise


# ─── payloads & parsers (all call HTTP Streamable tools) ─────────────────────
PLUGINS: List[Tuple[str, Any, str]] = [
    (
        "JSON Plugin",
        JsonToolPlugin(),
        json.dumps(
            {
                "tool_calls": [
                    {
                        "tool": f"{NAMESPACE}.http_greet",
                        "arguments": {"name": "Alice", "style": "formal"},
                    }
                ]
            }
        ),
    ),
    (
        "XML Plugin",
        XmlToolPlugin(),
        f'<tool name="{NAMESPACE}.session_info" args=\'{{}}\'/>',
    ),
    (
        "FunctionCall Plugin",
        FunctionCallPlugin(),
        json.dumps(
            {
                "function_call": {
                    "name": f"{NAMESPACE}.http_counter",
                    "arguments": {"increment": 5},
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
            print(Fore.MAGENTA + "  result :" + Style.RESET_ALL)
            # Truncate long results for readability
            result_str = str(res.result)
            if len(result_str) > 250:
                print(f"{result_str[:250]}...")
            else:
                print(res.result)
        else:
            print(Fore.RED + "  error  :" + Style.RESET_ALL, res.error)
        print(Style.DIM + "-" * 60)


# ─── main demo ──────────────────────────────────────────────────────────────
async def run_demo() -> None:
    print(Fore.GREEN + "=== Mock MCP HTTP Streamable Tool-Calling Demo ===" + Style.RESET_ALL)
    print("This demo uses the modern MCP Streamable HTTP transport (spec 2025-03-26)")
    print("which replaces the deprecated SSE transport with better infrastructure compatibility.")
    print("Start the test server with: python examples/mcp_streamable_http_server.py")

    try:
        await bootstrap_mcp()
    except Exception:
        return  # Error already logged

    registry = await ToolRegistryProvider.get_registry()

    executor = ToolExecutor(
        registry,
        strategy=InProcessStrategy(
            registry,
            default_timeout=5.0,  # Longer timeout for slow operations
            max_concurrency=3,    # Good concurrency for HTTP
        ),
    )

    # Check available tools
    tools = await registry.list_tools(NAMESPACE)
    if not tools:
        banner("❌ No Tools Found", Fore.RED)
        print("No tools were registered from the mock HTTP Streamable server.")
        await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
        return

    banner("Available HTTP Streamable Tools", Fore.BLUE)
    for ns, name in tools:
        tool_meta = await registry.get_metadata(name, ns)
        desc = tool_meta.description if tool_meta else "No description"
        print(f"  🛠️  {name}: {desc}")

    # sequential examples with different parsers ------------------------------
    for title, plugin, raw in PLUGINS:
        try:
            # new parser API is async
            calls = await plugin.try_parse(raw)
            results = await executor.execute(calls)
            show_results(f"{title} → sequential", calls, results)
        except Exception as e:
            print(f"❌ {title} failed: {e}")

    # parallel demo - test HTTP tools ---------------------------------------------
    banner("Parallel HTTP Streamable Calls")

    parallel_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.http_greet",
            arguments={"name": "Bob", "style": "casual"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.session_info",
            arguments={},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.http_counter",
            arguments={"increment": 3},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.http_greet",
            arguments={"name": "Charlie", "style": "formal"},
        )
    ]

    try:
        parallel_results = await executor.execute(parallel_calls)
        show_results("Parallel HTTP Tool Execution", parallel_calls, parallel_results)
    except Exception as e:
        print(f"❌ Parallel execution failed: {e}")

    # test error handling -----------------------------------------------------
    banner("Error Handling Test")
    
    error_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.nonexistent_http_tool",
            arguments={"test": "This should fail"},
        )
    ]
    
    try:
        error_results = await executor.execute(error_calls)
        show_results("Error Handling", error_calls, error_results)
    except Exception as e:
        print(f"Expected error test result: {e}")

    # Test slow operation (demonstrates streaming capability) ----------------
    banner("Slow Operation Test (Streaming Demonstration)")
    
    slow_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.slow_operation",
            arguments={"duration": 2},
        )
    ]
    
    try:
        print("⏱️  Testing slow operation (may use streaming response)...")
        slow_results = await executor.execute(slow_calls)
        show_results("Slow Operation (HTTP Streamable)", slow_calls, slow_results)
    except Exception as e:
        print(f"❌ Slow operation test failed: {e}")

    # HTTP-specific feature demonstration ------------------------------------
    banner("HTTP Streamable Features")
    
    # Test session persistence
    session_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.http_counter",
            arguments={"increment": 1},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.http_counter", 
            arguments={"increment": 2},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.session_info",
            arguments={},
        )
    ]
    
    try:
        session_results = await executor.execute(session_calls)
        show_results("Session Persistence Test", session_calls, session_results)
        
        print(Fore.CYAN + "\nHTTP Streamable Transport Features:" + Style.RESET_ALL)
        print("  • Single /mcp endpoint for all communication")
        print("  • Works with standard HTTP infrastructure")
        print("  • Supports both immediate JSON and streaming SSE responses")
        print("  • Better error handling and retry logic")
        print("  • Stateless operation when streaming not needed")
        print("  • Session management for stateful interactions")
        
    except Exception as e:
        print(f"❌ HTTP feature demonstration failed: {e}")

    # Transport comparison
    banner("Transport Comparison", Fore.MAGENTA)
    print("📊 HTTP Streamable vs SSE Transport:")
    print("   ✅ HTTP Streamable (2025-03-26 spec):")
    print("      • Single endpoint (/mcp)")
    print("      • Better infrastructure compatibility")
    print("      • Optional streaming when needed")
    print("      • Cleaner error handling")
    print("      • Standard HTTP semantics")
    print()
    print("   ⚠️  SSE Transport (deprecated):")
    print("      • Separate SSE and message endpoints")
    print("      • Infrastructure compatibility issues")
    print("      • Always streaming")
    print("      • Complex error scenarios")

    # summary
    banner("Demo Summary", Fore.GREEN)
    print("✅ Successfully demonstrated:")
    print("  • MCP HTTP Streamable transport with proper initialization")
    print("  • Multiple parser plugins (JSON, XML, FunctionCall)")
    print("  • Parallel tool execution")
    print("  • HTTP-specific tools and session management")
    print("  • Error handling and timeout scenarios")
    print("  • Modern single-endpoint approach")
    print("  • Optional streaming for complex operations")

    # goodbye
    await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
    print("\n🎉 HTTP Streamable demo completed successfully!")


if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    asyncio.run(run_demo())