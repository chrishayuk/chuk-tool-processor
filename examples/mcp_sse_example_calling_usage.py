#!/usr/bin/env python
"""
mcp_sse_example_calling_usage.py
──────────────────────────────────
Showcases three parser plugins (JSON, XML, Function-call) invoking
mock **perplexity_search** tools through a test MCP SSE server.

Prerequisites:
- Run the test server first: python examples/test_sse_server.py
- Server provides mock Perplexity tools for demonstration

It also fires a handful of parallel calls to demonstrate concurrency.
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
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse                    # noqa: E402

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

logger = get_logger("mcp-mock-sse-demo")

# ─── config / bootstrap ─────────────────────────────────────────────────────
SSE_SERVER_URL = "http://localhost:8000"
SERVER_NAME = "mock_perplexity_server"
NAMESPACE = "sse"          # where remote tools will be registered


async def bootstrap_mcp() -> None:
    """Start the SSE transport and connect to the mock test server."""
    try:
        print("🔄 Connecting to mock MCP SSE server...")
        _, sm = await setup_mcp_sse(
            servers=[
                {
                    "name": SERVER_NAME,
                    "url": SSE_SERVER_URL,
                }
            ],
            server_names={0: SERVER_NAME},
            namespace=NAMESPACE,
        )
        
        # keep for shutdown
        bootstrap_mcp.stream_manager = sm  # type: ignore[attr-defined]
        print("✅ Connected to mock server successfully!")
        
    except Exception as e:
        logger.error(f"Failed to bootstrap MCP SSE: {e}")
        print(f"❌ Could not connect to mock SSE server at {SSE_SERVER_URL}")
        print("Please start the test server first:")
        print("   python examples/test_sse_server.py")
        raise


# ─── payloads & parsers (all call mock perplexity tools) ─────────────────────
PLUGINS: List[Tuple[str, Any, str]] = [
    (
        "JSON Plugin",
        JsonToolPlugin(),
        json.dumps(
            {
                "tool_calls": [
                    {
                        "tool": f"{NAMESPACE}.perplexity_search",
                        "arguments": {"query": "What are the latest AI breakthroughs in artificial intelligence?"},
                    }
                ]
            }
        ),
    ),
    (
        "XML Plugin",
        XmlToolPlugin(),
        f'<tool name="{NAMESPACE}.perplexity_deep_research" '
        'args=\'{"query": "How does quantum computing technology work and what are its applications?"}\'/>',
    ),
    (
        "FunctionCall Plugin",
        FunctionCallPlugin(),
        json.dumps(
            {
                "function_call": {
                    "name": f"{NAMESPACE}.perplexity_quick_fact",
                    "arguments": {"query": "What is renewable energy?"},
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
    print(Fore.GREEN + "=== Mock MCP Perplexity Search Tool-Calling Demo (SSE) ===" + Style.RESET_ALL)
    print("This demo uses a mock test server that simulates Perplexity API responses.")
    print("Start the test server with: python examples/test_sse_server.py")

    try:
        await bootstrap_mcp()
    except Exception:
        return  # Error already logged

    registry = await ToolRegistryProvider.get_registry()

    executor = ToolExecutor(
        registry,
        strategy=InProcessStrategy(
            registry,
            default_timeout=2.0,  # 2 second timeout - will be enforced consistently
            max_concurrency=2,    # Reduce concurrency for stability
        ),
    )

    # Check available tools
    tools = await registry.list_tools(NAMESPACE)
    if not tools:
        banner("❌ No Tools Found", Fore.RED)
        print("No tools were registered from the mock SSE server.")
        await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
        return

    banner("Available Mock Tools", Fore.BLUE)
    for ns, name in tools:
        tool_meta = await registry.get_metadata(name, ns)
        desc = tool_meta.description if tool_meta else "No description"
        print(f"  🔧 {name}: {desc}")

    # sequential examples with different parsers ------------------------------
    for title, plugin, raw in PLUGINS:
        try:
            # new parser API is async
            calls = await plugin.try_parse(raw)
            results = await executor.execute(calls)
            show_results(f"{title} → sequential", calls, results)
        except Exception as e:
            print(f"❌ {title} failed: {e}")

    # parallel demo - test all three tools -----------------------------------
    banner("Parallel Mock Search Calls")

    parallel_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_search",
            arguments={"query": "What is machine learning and how does it work?"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_deep_research",
            arguments={"query": "Climate change effects and mitigation strategies 2024"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_quick_fact",
            arguments={"query": "What are electric vehicles?"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_search",
            arguments={"query": "Latest space exploration achievements"},
        )
    ]

    try:
        parallel_results = await executor.execute(parallel_calls)
        show_results("Parallel Mock Tool Execution", parallel_calls, parallel_results)
    except Exception as e:
        print(f"❌ Parallel execution failed: {e}")

    # test error handling -----------------------------------------------------
    banner("Error Handling Test")
    
    error_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.nonexistent_tool",
            arguments={"query": "This should fail"},
        )
    ]
    
    try:
        error_results = await executor.execute(error_calls)
        show_results("Error Handling", error_calls, error_results)
    except Exception as e:
        print(f"Expected error test result: {e}")

    # Tool-specific feature demonstration ------------------------------------
    banner("Tool-Specific Features")
    
    feature_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_search",
            arguments={"query": "artificial intelligence applications"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_deep_research", 
            arguments={"query": "artificial intelligence applications"},
        ),
        ToolCall(
            tool=f"{NAMESPACE}.perplexity_quick_fact",
            arguments={"query": "artificial intelligence applications"},
        )
    ]
    
    try:
        feature_results = await executor.execute(feature_calls)
        show_results("Different Tool Types (same query)", feature_calls, feature_results)
        
        print(Fore.CYAN + "\nNotice how each tool type returns different response formats:" + Style.RESET_ALL)
        print("  • perplexity_search: Standard conversational response")
        print("  • perplexity_deep_research: Detailed analysis with citations")
        print("  • perplexity_quick_fact: Concise factual answer")
        
    except Exception as e:
        print(f"❌ Feature demonstration failed: {e}")

    # summary
    banner("Demo Summary", Fore.GREEN)
    print("✅ Successfully demonstrated:")
    print("  • MCP SSE transport with proper initialization")
    print("  • Multiple parser plugins (JSON, XML, FunctionCall)")
    print("  • Parallel tool execution")
    print("  • Different mock Perplexity tool types")
    print("  • Error handling")
    print("  • Mock server simulation of real Perplexity API")

    # goodbye
    await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
    print("\n🎉 Mock demo completed successfully!")


if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    asyncio.run(run_demo())