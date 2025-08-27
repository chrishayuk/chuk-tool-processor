#!/usr/bin/env python
"""
run_streamable_http_demo.py
────────────────────────────
Convenience script to run the complete HTTP Streamable demo:
1. Starts the mock HTTP Streamable server
2. Waits for it to be ready
3. Runs the client demo
4. Cleans up

Usage: python run_streamable_http_demo.py
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import requests


def check_server_ready(url: str, max_attempts: int = 10) -> bool:
    """Check if the server is ready to accept connections."""
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass

        print(f"⏳ Waiting for server... (attempt {attempt + 1}/{max_attempts})")
        time.sleep(1)

    return False


async def run_demo():
    """Run the complete HTTP Streamable demo."""
    server_url = "http://localhost:8000"

    # Get the correct project root (parent of the script location)
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "examples":
        # If script is in examples/ directory
        project_root = script_path.parent.parent
    else:
        # If script is in project root
        project_root = script_path.parent

    print(f"📁 Project root: {project_root}")

    # Start the mock server
    print("🚀 Starting mock HTTP Streamable server...")
    server_script = project_root / "examples" / "mcp_streamable_http_server.py"
    client_script = project_root / "examples" / "mcp_streamable_http_example_calling_usage.py"

    print(f"🖥️  Server script: {server_script}")
    print(f"🎯 Client script: {client_script}")

    if not server_script.exists():
        print(f"❌ Server script not found: {server_script}")
        print("Please save the mcp_streamable_http_server.py to the examples/ directory")
        return

    if not client_script.exists():
        print(f"❌ Client script not found: {client_script}")
        print("Creating client script...")

        # Create the client script
        # Create the client script with proper escaping
        client_code = """#!/usr/bin/env python
\"\"\"
mcp_streamable_http_example_calling_usage.py
─────────────────────────────────────────────
Showcases three parser plugins (JSON, XML, Function-call) invoking
mock **HTTP Streamable** tools through a test MCP HTTP server.

Prerequisites:
- Run the test server first: python examples/mcp_streamable_http_server.py
- Server provides mock HTTP tools for demonstration

It also fires a handful of parallel calls to demonstrate concurrency.
\"\"\"

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
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable                    # noqa: E402

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

logger = get_logger("mcp-mock-http-streamable-demo")

# ─── config / bootstrap ─────────────────────────────────────────────────────
HTTP_SERVER_URL = "http://localhost:8000"
SERVER_NAME = "mock_http_server"
NAMESPACE = "http"          # where remote tools will be registered


async def bootstrap_mcp() -> None:
    \"\"\"Start the HTTP Streamable transport and connect to the mock test server.\"\"\"
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
        print("✅ Connected to mock server successfully!")

    except Exception as e:
        logger.error(f"Failed to bootstrap MCP HTTP Streamable: {e}")
        print(f"❌ Could not connect to mock HTTP server at {HTTP_SERVER_URL}")
        print("Please start the test server first:")
        print("   python examples/mcp_streamable_http_server.py")
        raise


# ─── payloads & parsers (all call mock http tools) ─────────────────────────
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
        '<tool name="' + NAMESPACE + '.session_info" args=\\'{}\\'/>'
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
    print(colour + f"\\n=== {text} ===" + Style.RESET_ALL)


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
    print("This demo uses a mock test server that simulates HTTP Streamable transport.")
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
            default_timeout=10.0,  # 10 second timeout for slower HTTP operations
            max_concurrency=2,    # Reduce concurrency for stability
        ),
    )

    # Check available tools
    tools = await registry.list_tools(NAMESPACE)
    if not tools:
        banner("❌ No Tools Found", Fore.RED)
        print("No tools were registered from the mock HTTP server.")
        await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
        return

    banner("Available Mock HTTP Tools", Fore.BLUE)
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

    # parallel demo - test all four tools -----------------------------------
    banner("Parallel Mock HTTP Calls")

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
            tool=f"{NAMESPACE}.slow_operation",
            arguments={"duration": 2},
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

    # Streaming demonstration ------------------------------------
    banner("Streaming Features Test")

    streaming_calls = [
        ToolCall(
            tool=f"{NAMESPACE}.slow_operation",
            arguments={"duration": 3},
        )
    ]

    try:
        streaming_results = await executor.execute(streaming_calls)
        show_results("Slow Operation (potential streaming)", streaming_calls, streaming_results)

    except Exception as e:
        print(f"❌ Streaming demonstration failed: {e}")

    # summary
    banner("Demo Summary", Fore.GREEN)
    print("✅ Successfully demonstrated:")
    print("  • MCP HTTP Streamable transport with proper initialization")
    print("  • Multiple parser plugins (JSON, XML, FunctionCall)")
    print("  • Parallel tool execution")
    print("  • Different mock HTTP tool types")
    print("  • Error handling")
    print("  • Mock server simulation of HTTP Streamable transport")
    print("  • Modern single-endpoint approach (spec 2025-03-26)")

    # goodbye
    await bootstrap_mcp.stream_manager.close()  # type: ignore[attr-defined]
    print("\\n🎉 Mock HTTP Streamable demo completed successfully!")


if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    asyncio.run(run_demo())
"""

        client_script.write_text(client_code)
        print(f"✅ Created client script: {client_script}")

    server_process = subprocess.Popen([sys.executable, str(server_script)])

    try:
        # Wait for server to be ready
        if not check_server_ready(server_url):
            print("❌ Server failed to start within timeout")
            return

        print("✅ Server is ready!")
        print("🔄 Running client demo...")

        # Run the client demo
        client_process = subprocess.run([sys.executable, str(client_script)])

        if client_process.returncode == 0:
            print("✅ Demo completed successfully!")
        else:
            print(f"❌ Demo failed with exit code: {client_process.returncode}")

    except KeyboardInterrupt:
        print("\\n🛑 Demo interrupted by user")

    except Exception as e:
        print(f"❌ Demo error: {e}")

    finally:
        # Clean up server
        print("🧹 Cleaning up server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("👋 Demo complete!")


if __name__ == "__main__":
    print("🌐 HTTP Streamable Demo Runner")
    print("=" * 50)

    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\\n👋 Bye!")
    except Exception as e:
        print(f"❌ Runner error: {e}")
        sys.exit(1)
