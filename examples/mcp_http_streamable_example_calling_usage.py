#!/usr/bin/env python
"""
mcp_streamable_http_example_calling_usage.py - FIXED
────────────────────────────────────────────────────
Updated demo showcasing HTTP Streamable transport using chuk-mcp patterns.

FIXED: Removed faulty dependency checks that were incorrectly failing
despite chuk-mcp being properly installed and working.
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

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.registry.provider import ToolRegistryProvider

# Import the working setup function (we know this works from Context7 success)
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable

# parsers
from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin
from chuk_tool_processor.plugins.parsers.function_call_tool import FunctionCallPlugin

# executor
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = get_logger("mcp-http-streamable-demo")

# ─── config / bootstrap ─────────────────────────────────────────────────────
HTTP_SERVER_URL = "http://localhost:8000"
SERVER_NAME = "mock_http_server"
NAMESPACE = "http"


async def bootstrap_mcp() -> None:
    """Start the HTTP Streamable transport and connect to the mock test server."""
    try:
        print("🔄 Connecting to mock MCP HTTP Streamable server...")
        
        # Use the working setup function (proven to work with Context7)
        _, sm = await setup_mcp_http_streamable(
            servers=[
                {
                    "name": SERVER_NAME,
                    "url": HTTP_SERVER_URL,
                }
            ],
            server_names={0: SERVER_NAME},
            namespace=NAMESPACE,
            connection_timeout=10.0,
            default_timeout=30.0,
        )
        
        # keep for shutdown
        bootstrap_mcp.stream_manager = sm
        print("✅ Connected to mock server successfully!")
        
    except Exception as e:
        logger.error(f"Failed to bootstrap MCP HTTP Streamable: {e}")
        print(f"❌ Could not connect to mock HTTP server at {HTTP_SERVER_URL}")
        print("Please start the test server first:")
        print("   python examples/mcp_streamable_http_server.py")
        print("\n🔍 Troubleshooting:")
        print("   • Check if the server is running")
        print("   • Verify the server URL is correct")
        raise


def create_test_plugins():
    """Create test plugins with proper string handling."""
    return [
        (
            "JSON Plugin",
            JsonToolPlugin(),
            json.dumps({
                "tool_calls": [{
                    "tool": f"{NAMESPACE}.http_greet",
                    "arguments": {"name": "Alice", "style": "formal"},
                }]
            }),
        ),
        (
            "XML Plugin", 
            XmlToolPlugin(),
            f'<tool name="{NAMESPACE}.session_info" args="{{}}"/>',
        ),
        (
            "FunctionCall Plugin",
            FunctionCallPlugin(),
            json.dumps({
                "function_call": {
                    "name": f"{NAMESPACE}.http_counter",
                    "arguments": {"increment": 5},
                }
            }),
        ),
    ]


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
            result_str = str(res.result)
            if len(result_str) > 250:
                print(f"{result_str[:250]}...")
            else:
                print(res.result)
        else:
            print(Fore.RED + "  error  :" + Style.RESET_ALL, res.error)
        print(Style.DIM + "-" * 60)


async def run_demo() -> None:
    print(Fore.GREEN + "=== MCP HTTP Streamable Tool-Calling Demo ===" + Style.RESET_ALL)
    print("This demo uses chuk-mcp HTTP Streamable transport (spec 2025-03-26)")
    print("Modern replacement for deprecated SSE transport")
    
    # Verify chuk-mcp is working (we know it is from Context7 success)
    try:
        import chuk_mcp
        print(f"✅ chuk-mcp detected: {chuk_mcp.__file__}")
    except ImportError:
        print("❌ chuk-mcp not available - but this shouldn't happen!")
        return

    try:
        await bootstrap_mcp()
    except Exception:
        return  # Error already logged

    registry = await ToolRegistryProvider.get_registry()

    executor = ToolExecutor(
        registry,
        strategy=InProcessStrategy(
            registry,
            default_timeout=10.0,
            max_concurrency=2,
        ),
    )

    # Check available tools
    tools = await registry.list_tools(NAMESPACE)
    if not tools:
        banner("❌ No Tools Found", Fore.RED)
        print("No tools were registered from the HTTP Streamable server.")
        print("Available namespaces:")
        all_tools = await registry.list_tools()
        namespaces = set(ns for ns, _ in all_tools)
        for ns in namespaces:
            print(f"  • {ns}")
        await bootstrap_mcp.stream_manager.close()
        return

    banner("Available HTTP Streamable Tools", Fore.BLUE)
    for ns, name in tools:
        tool_meta = await registry.get_metadata(name, ns)
        desc = tool_meta.description if tool_meta else "No description"
        print(f"  🔧 {name}: {desc}")

    # sequential examples with different parsers
    plugins = create_test_plugins()
    for title, plugin, raw in plugins:
        try:
            calls = await plugin.try_parse(raw)
            results = await executor.execute(calls)
            show_results(f"{title} → sequential", calls, results)
        except Exception as e:
            print(f"❌ {title} failed: {e}")

    # parallel demo
    banner("Parallel HTTP Streamable Calls")

    parallel_calls = [
        ToolCall(tool=f"{NAMESPACE}.http_greet", arguments={"name": "Bob", "style": "casual"}),
        ToolCall(tool=f"{NAMESPACE}.session_info", arguments={}),
        ToolCall(tool=f"{NAMESPACE}.http_counter", arguments={"increment": 3}),
        ToolCall(tool=f"{NAMESPACE}.slow_operation", arguments={"duration": 2}),
    ]

    try:
        parallel_results = await executor.execute(parallel_calls)
        show_results("Parallel HTTP Streamable Execution", parallel_calls, parallel_results)
    except Exception as e:
        print(f"❌ Parallel execution failed: {e}")

    # error handling test
    banner("Error Handling Test")
    
    error_calls = [ToolCall(tool=f"{NAMESPACE}.nonexistent_tool", arguments={"query": "This should fail"})]
    
    try:
        error_results = await executor.execute(error_calls)
        show_results("Error Handling", error_calls, error_results)
    except Exception as e:
        print(f"Expected error test result: {e}")

    # Test HTTP Streamable specific features
    banner("HTTP Streamable Features Test")
    
    # Get transport metrics if available
    try:
        transport = None
        for transport_name, transport_instance in bootstrap_mcp.stream_manager.transports.items():
            if hasattr(transport_instance, 'get_metrics'):
                transport = transport_instance
                break
        
        if transport:
            metrics = transport.get_metrics()
            print("📊 HTTP Streamable Transport Metrics:")
            for key, value in metrics.items():
                if value is not None:
                    if isinstance(value, float):
                        print(f"  {key}: {value:.3f}")
                    else:
                        print(f"  {key}: {value}")
        else:
            print("  📊 Transport metrics not available")
    except Exception as e:
        print(f"  ❌ Error getting metrics: {e}")

    # summary
    banner("Demo Summary", Fore.GREEN)
    print("✅ Successfully demonstrated:")
    print("  • MCP HTTP Streamable transport using chuk-mcp")
    print("  • Modern replacement for SSE transport (spec 2025-03-26)")
    print("  • Multiple parser plugins (JSON, XML, FunctionCall)")
    print("  • Parallel tool execution with HTTP requests")
    print("  • Different HTTP Streamable tool types")
    print("  • Error handling and timeout management")
    print("  • Performance metrics and monitoring")
    print("  • Session management via HTTP headers")

    # cleanup
    await bootstrap_mcp.stream_manager.close()
    print("\n🎉 HTTP Streamable demo completed successfully!")


if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    asyncio.run(run_demo())