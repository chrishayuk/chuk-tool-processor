#!/usr/bin/env python
"""
remote_sse_calling_example.py
─────────────────────────────
Calls the REMOTE SSE server that the perplexity_agent uses,
not the local mock server.

This uses your actual remote SSE server configuration.

Prerequisites:
- Set the same environment variables that your perplexity_agent uses:
  export MCP_SERVER_NAME_MAP='{"perplexity_server":"perplexity_server"}'
  export MCP_SERVER_URL_MAP='{"perplexity_server":"https://your-remote-server.com"}'
  export MCP_BEARER_TOKEN="your-token-if-needed"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from colorama import Fore, Style
from colorama import init as colorama_init

colorama_init(autoreset=True)

# ─── local-package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if it exists
try:
    from dotenv import load_dotenv

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded .env file from {env_file}")
    else:
        print("ℹ️ No .env file found, using system environment variables")
except ImportError:
    print("ℹ️ python-dotenv not available, using system environment variables only")

from chuk_tool_processor.execution.strategies.inprocess_strategy import (  # noqa: E402
    InProcessStrategy,
)

# executor
from chuk_tool_processor.execution.tool_executor import ToolExecutor  # noqa: E402
from chuk_tool_processor.logging import get_logger  # noqa: E402
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse  # noqa: E402
from chuk_tool_processor.models.tool_call import ToolCall  # noqa: E402
from chuk_tool_processor.models.tool_result import ToolResult  # noqa: E402
from chuk_tool_processor.plugins.parsers.function_call_tool import (  # noqa: E402
    FunctionCallPlugin,
)

# parsers
from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin  # noqa: E402
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin  # noqa: E402
from chuk_tool_processor.registry.provider import ToolRegistryProvider  # noqa: E402

logger = get_logger("remote-sse-demo")


# ─── Remote SSE Server Configuration (same as perplexity_agent) ─────────────
def _load_override(var: str) -> dict[str, str]:
    """Load environment variable as JSON dict or return empty dict."""
    raw = os.getenv(var)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Ignoring invalid %s (%s)", var, exc)
        return {}


def get_remote_mcp_servers() -> list[dict[str, str]]:
    """Get the same remote MCP server configuration that perplexity_agent uses."""

    # Debug: Log all relevant environment variables
    print("🔍 Checking remote SSE MCP environment variables...")
    print(f"MCP_SERVER_URL: {os.getenv('MCP_SERVER_URL', 'NOT SET')}")
    print(f"MCP_SERVER_URL_MAP: {os.getenv('MCP_SERVER_URL_MAP', 'NOT SET')}")
    print(f"MCP_SERVER_NAME_MAP: {os.getenv('MCP_SERVER_NAME_MAP', 'NOT SET')}")
    print(f"MCP_BEARER_TOKEN: {'SET' if os.getenv('MCP_BEARER_TOKEN') else 'NOT SET'}")

    # Get bearer token
    bearer_token = os.getenv("MCP_BEARER_TOKEN")

    # Load environment variable overrides
    name_override = _load_override("MCP_SERVER_NAME_MAP")
    url_override = _load_override("MCP_SERVER_URL_MAP")

    print(f"📋 Parsed name_override: {name_override}")
    print(f"📋 Parsed url_override: {url_override}")

    # Check for simple single server URL
    single_server_url = os.getenv("MCP_SERVER_URL")

    if single_server_url:
        print(
            f"🌐 Using single remote SSE MCP server: {single_server_url[:50]}{'...' if len(single_server_url) > 50 else ''}"
        )
        server_config = {
            "name": "perplexity_server",
            "url": single_server_url,
        }
        # ADD THE API KEY!
        if bearer_token:
            server_config["api_key"] = bearer_token
        return [server_config]

    # Check URL override map
    if url_override:
        servers = []
        for server_name, server_url in url_override.items():
            actual_name = name_override.get(server_name, server_name)
            server_config = {
                "name": actual_name,
                "url": server_url,
            }
            # ADD THE API KEY!
            if bearer_token:
                server_config["api_key"] = bearer_token
            servers.append(server_config)
        print(f"🌐 Using {len(servers)} remote SSE MCP server(s) from URL map")
        # Don't print the actual api_key in logs
        safe_servers = []
        for s in servers:
            safe_s = s.copy()
            if "api_key" in safe_s:
                safe_s["api_key"] = "SET"
            safe_servers.append(safe_s)
        print(f"📋 Servers: {safe_servers}")
        return servers

    # No MCP configuration found
    print("❌ No remote SSE MCP server configuration found in environment variables")
    print("Please set one of:")
    print("  export MCP_SERVER_URL='https://your-remote-server.com'")
    print('  export MCP_SERVER_URL_MAP=\'{"perplexity_server": "https://your-remote-server.com"}\'')
    return []


NAMESPACE = "sse"  # where remote tools will be registered


async def bootstrap_remote_mcp() -> None:
    """Connect to the same remote SSE server that perplexity_agent uses."""
    servers = get_remote_mcp_servers()

    if not servers:
        raise ValueError(
            "No remote SSE MCP servers configured. Please set MCP_SERVER_URL or MCP_SERVER_URL_MAP environment variables."
        )

    try:
        print("🔄 Connecting to remote SSE MCP server(s)...")
        for server in servers:
            print(f"  📡 {server['name']}: {server['url']}")
            if "api_key" in server:
                print("     🔑 Auth: SET")

        server_names = {i: srv["name"] for i, srv in enumerate(servers)}

        _, sm = await setup_mcp_sse(
            servers=servers,
            server_names=server_names,
            namespace=NAMESPACE,
        )

        # keep for shutdown
        bootstrap_remote_mcp.stream_manager = sm  # type: ignore[attr-defined]
        print("✅ Connected to remote server(s) successfully!")

    except Exception as e:
        logger.error(f"Failed to bootstrap remote MCP SSE: {e}")
        print("❌ Could not connect to remote SSE server(s)")
        print("Check your network connection and server URLs")
        raise


# ─── Test payloads for remote server tools ─────────────────────────────────
def get_test_plugins() -> list[tuple[str, Any, str]]:
    """Get test plugins with payloads for the remote server's tools."""

    # Note: These tool names should match what the remote server provides
    # You may need to adjust these based on the actual remote server's tool names

    return [
        (
            "JSON Plugin - Remote Search",
            JsonToolPlugin(),
            json.dumps(
                {
                    "tool_calls": [
                        {
                            "tool": f"{NAMESPACE}.perplexity_search",
                            "arguments": {"query": "What are the latest developments in renewable energy technology?"},
                        }
                    ]
                }
            ),
        ),
        (
            "XML Plugin - Remote Research",
            XmlToolPlugin(),
            f'<tool name="{NAMESPACE}.perplexity_deep_research" '
            'args=\'{"query": "Impact of artificial intelligence on healthcare industry"}\'/>',
        ),
        (
            "FunctionCall Plugin - Remote Fact",
            FunctionCallPlugin(),
            json.dumps(
                {
                    "function_call": {
                        "name": f"{NAMESPACE}.perplexity_quick_fact",
                        "arguments": {"query": "What is carbon capture technology?"},
                    }
                }
            ),
        ),
    ]


# ─── helpers ────────────────────────────────────────────────────────────────
def banner(text: str, colour: str = Fore.CYAN) -> None:
    print(colour + f"\n=== {text} ===" + Style.RESET_ALL)


def show_results(title: str, calls: list[ToolCall], results: list[ToolResult]) -> None:
    banner(title)
    for call, res in zip(calls, results, strict=False):
        ok = res.error is None
        head_colour = Fore.GREEN if ok else Fore.RED
        duration = (res.end_time - res.start_time).total_seconds()
        print(f"{head_colour}{res.tool}  ({duration:.3f}s){Style.RESET_ALL}")
        print(Fore.YELLOW + "  args   :" + Style.RESET_ALL, call.arguments)
        if ok:
            print(Fore.MAGENTA + "  result :" + Style.RESET_ALL)
            # Truncate long results for readability
            result_str = str(res.result)
            if len(result_str) > 300:
                print(f"{result_str[:300]}...")
            else:
                print(res.result)
        else:
            print(Fore.RED + "  error  :" + Style.RESET_ALL, res.error)
        print(Style.DIM + "-" * 60)


# ─── main demo ──────────────────────────────────────────────────────────────
async def run_remote_demo() -> None:
    print(Fore.GREEN + "=== Remote SSE MCP Server Tool-Calling Demo ===" + Style.RESET_ALL)
    print("This demo connects to the SAME remote SSE server that your perplexity_agent uses.")
    print("Make sure you have the same environment variables set as your perplexity_agent.\n")

    try:
        await bootstrap_remote_mcp()
    except Exception:
        return  # Error already logged

    registry = await ToolRegistryProvider.get_registry()

    executor = ToolExecutor(
        registry,
        strategy=InProcessStrategy(
            registry,
            default_timeout=30.0,  # Longer timeout for remote calls
            max_concurrency=2,  # Conservative for remote server
        ),
    )

    # Check available tools from remote server
    tools = await registry.list_tools(NAMESPACE)
    if not tools:
        banner("❌ No Tools Found", Fore.RED)
        print("No tools were registered from the remote SSE server.")
        print("This could mean:")
        print("  • The remote server is not responding")
        print("  • The server doesn't provide MCP tools")
        print("  • Authentication issues (check MCP_BEARER_TOKEN)")
        print("  • Wrong server URL")
        await bootstrap_remote_mcp.stream_manager.close()  # type: ignore[attr-defined]
        return

    banner("Available Remote Tools", Fore.BLUE)
    for ns, name in tools:
        tool_meta = await registry.get_metadata(name, ns)
        desc = tool_meta.description if tool_meta else "No description"
        print(f"  🔧 {name}: {desc}")

    # Get test plugins based on what tools are actually available
    available_tool_names = [name for ns, name in tools]
    plugins = get_test_plugins()

    # Filter plugins to only test tools that exist
    valid_plugins = []
    for title, plugin, raw in plugins:
        # Extract tool name from the payload to check if it exists
        try:
            if "perplexity_search" in raw and "perplexity_search" in available_tool_names or "perplexity_deep_research" in raw and "perplexity_deep_research" in available_tool_names or "perplexity_quick_fact" in raw and "perplexity_quick_fact" in available_tool_names:
                valid_plugins.append((title, plugin, raw))
        except Exception:
            pass

    if not valid_plugins:
        print(f"⚠️ No matching test plugins for available tools: {available_tool_names}")
        print("Creating generic test calls...")

        # Create generic test calls for whatever tools are available
        generic_calls = []
        for ns, tool_name in tools[:3]:  # Test first 3 tools
            # Get tool metadata to determine correct arguments
            tool_meta = await registry.get_metadata(tool_name, ns)
            args = {}

            if tool_meta and hasattr(tool_meta, "input_schema"):
                schema = tool_meta.input_schema
                required = schema.get("required", [])
                properties = schema.get("properties", {})

                for field in required:
                    if field in properties:
                        prop = properties[field]
                        if prop.get("type") == "string":
                            if "query" in field.lower():
                                args[field] = f"Test query for {tool_name}"
                            elif "message" in field.lower():
                                args[field] = f"Test message for {tool_name}"
                            else:
                                args[field] = "test_string"
                        elif prop.get("type") == "integer":
                            args[field] = 1
                        elif prop.get("type") == "boolean":
                            args[field] = True

            if not args:
                args = {"query": f"Test query for {tool_name}"}

            generic_calls.append(ToolCall(tool=f"{ns}.{tool_name}", arguments=args))

        if generic_calls:
            try:
                results = await executor.execute(generic_calls)
                show_results("Generic Tool Tests", generic_calls, results)
            except Exception as e:
                print(f"❌ Generic tool test failed: {e}")

    else:
        # Test with valid plugins
        for title, plugin, raw in valid_plugins:
            try:
                calls = await plugin.try_parse(raw)
                results = await executor.execute(calls)
                show_results(f"{title} → remote call", calls, results)

                # Add delay between calls to be nice to remote server
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ {title} failed: {e}")

    # Test parallel calls if we have multiple tools
    if len(tools) >= 2:
        banner("Parallel Remote Calls")

        parallel_calls = []
        for i, (ns, tool_name) in enumerate(tools[:3]):  # Max 3 parallel
            # Get tool metadata to build correct arguments
            tool_meta = await registry.get_metadata(tool_name, ns)

            # Build arguments based on tool requirements
            if tool_name == "echo":
                args = {"message": f"Parallel test {i + 1}: Hello from SSE!"}
            elif tool_name == "get_current_time":
                args = {"timezone": "UTC"}
            elif tool_name == "convert_time":
                args = {"source_timezone": "UTC", "time": "12:00", "target_timezone": "America/New_York"}
            elif tool_name == "ping":
                args = {"host": "google.com"}
            elif tool_name == "tcp_ping":
                args = {"host": "google.com", "port": 80}
            elif tool_name == "perplexity_search":
                args = {"query": f"Parallel test query {i + 1}"}
            elif tool_name == "perplexity_quick_fact":
                args = {"query": f"What is test fact {i + 1}?"}
            elif tool_name == "google_search":
                args = {"query": f"Test search {i + 1}"}
            elif tool_name == "wikipedia_search":
                args = {"query": "Python programming"}
            else:
                # For unknown tools, try to build minimal valid args from schema
                args = {}
                if tool_meta and hasattr(tool_meta, "input_schema"):
                    schema = tool_meta.input_schema
                    required = schema.get("required", [])
                    properties = schema.get("properties", {})

                    for field in required[:1]:  # Just fill first required field
                        if field in properties:
                            prop = properties[field]
                            if prop.get("type") == "string":
                                # Check if it's likely a query field
                                if "query" in field.lower() or "message" in field.lower() or "text" in field.lower():
                                    args[field] = f"Parallel test {i + 1}"
                                elif "timezone" in field.lower():
                                    args[field] = "UTC"
                                elif "host" in field.lower():
                                    args[field] = "example.com"
                                else:
                                    args[field] = "test_value"
                            elif prop.get("type") == "integer":
                                args[field] = 1
                            elif prop.get("type") == "boolean":
                                args[field] = True

            parallel_calls.append(ToolCall(tool=f"{ns}.{tool_name}", arguments=args))

        try:
            parallel_results = await executor.execute(parallel_calls)
            show_results("Parallel Remote Tool Execution", parallel_calls, parallel_results)
        except Exception as e:
            print(f"❌ Parallel execution failed: {e}")

    # summary
    banner("Remote Demo Summary", Fore.GREEN)
    print("✅ Successfully demonstrated:")
    print("  • Connection to the same remote SSE server as perplexity_agent")
    print("  • Remote tool discovery and execution")
    print("  • Multiple parser plugins with remote calls")
    print("  • Real network-based MCP communication")
    print(f"  • {len(tools)} tools available from remote server")

    # goodbye
    await bootstrap_remote_mcp.stream_manager.close()  # type: ignore[attr-defined]
    print("\n🎉 Remote demo completed successfully!")


if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper()))

    print("🌐 Remote SSE MCP Tool Calling Demo")
    print("=" * 50)
    print("This script connects to your actual remote SSE server")
    print("using the same configuration as your perplexity_agent.")
    print()
    print("Required environment variables:")
    print("  MCP_SERVER_NAME_MAP (server name mapping)")
    print("  MCP_SERVER_URL_MAP (server URL mapping)")
    print("  MCP_BEARER_TOKEN (if authentication required)")
    print("=" * 50)
    print()

    asyncio.run(run_remote_demo())
