#!/usr/bin/env python
"""
mcp_stdio_example_subprocess_strategy.py
Demonstrates invoking MCP tools via stdio transport and executing them
with the SubprocessStrategy (true process isolation).

Fixed version that addresses:
1. Null result issues with MCP tool calls
2. Proper error handling and logging
3. Clean shutdown without task cancellation errors
4. Better timeout handling
5. Correct ToolResult structure handling
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import traceback
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────────
#  Local package imports
# ────────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from colorama import Fore, Style
    from colorama import init as colorama_init

    colorama_init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    # Fallback for environments without colorama
    COLORAMA_AVAILABLE = False

    class MockFore:
        CYAN = YELLOW = RED = GREEN = ""

    class MockStyle:
        RESET_ALL = ""

    Fore = MockFore()
    Style = MockStyle()

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
    try:
        # Get duration - ToolResult has a duration property
        dur = res.duration if hasattr(res, "duration") else 0.0

        # Check success status - ToolResult uses is_success property
        success = res.is_success if hasattr(res, "is_success") else (not res.error if hasattr(res, "error") else False)

        status = "✅" if success else "❌"
        tool_name = res.tool if hasattr(res, "tool") else call.tool

        print(f"{status} {Fore.YELLOW}{tool_name:20}{Style.RESET_ALL} ({dur:5.3f}s)")

        # Show arguments
        print(f"  📥 Args: {json.dumps(call.arguments, indent=2)}")

        # Show result or error
        if success and hasattr(res, "result") and res.result is not None:
            print(f"  📤 Result: {json.dumps(res.result, indent=2, default=str)}")
        elif not success and hasattr(res, "error") and res.error:
            print(f"  ❌ Error: {res.error}")
        else:
            print(f"  ⚠️  No result data (success: {success})")
            print(f"      Raw result type: {type(res).__name__}")
            if hasattr(res, "__dict__"):
                print(f"      Available attributes: {list(res.__dict__.keys())}")

        # Show additional metadata if available
        if hasattr(res, "machine") and hasattr(res, "pid"):
            print(f"  🖥️  Machine: {res.machine} (PID: {res.pid})")
        if hasattr(res, "attempts") and res.attempts > 1:
            print(f"  🔄 Attempts: {res.attempts}")
        if hasattr(res, "cached") and res.cached:
            print("  💾 Cached: Yes")

        print("─" * 60)

    except Exception as e:
        print(f"❌ Error displaying result: {e}")
        print(f"   Result type: {type(res).__name__}")
        if hasattr(res, "__dict__"):
            print(f"   Result dict: {res.__dict__}")
        else:
            print(f"   Result repr: {repr(res)}")
        print("─" * 60)


def show_error(message: str, error: Exception) -> None:
    """Show error with proper formatting."""
    print(f"{Fore.RED}❌ {message}:{Style.RESET_ALL}")
    print(f"   {str(error)}")
    if LOG.isEnabledFor(10):  # DEBUG level
        print(f"   Traceback: {traceback.format_exc()}")


# ────────────────────────────────────────────────────────────────────────────────
async def verify_config() -> bool:
    """Verify that the configuration file exists and has the time server."""
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Configuration file not found: {CONFIG_FILE}")
        print("   Please create a server_config.json with a 'time' server entry.")
        print("   Example:")
        print('   {"mcpServers": {"time": {"command": "uvx", "args": ["mcp-server-time"]}}}')
        return False

    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)

        if TIME_SERVER not in config.get("mcpServers", {}):
            print(f"❌ Server '{TIME_SERVER}' not found in {CONFIG_FILE}")
            print(f"   Available servers: {list(config.get('mcpServers', {}).keys())}")
            return False

        print(f"✅ Configuration verified - '{TIME_SERVER}' server found")
        return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {CONFIG_FILE}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading {CONFIG_FILE}: {e}")
        return False


# ────────────────────────────────────────────────────────────────────────────────
async def bootstrap() -> tuple[ToolExecutor | None, list[ToolCall]]:
    """Start MCP stdio transport for the *time* server and prep ToolCalls."""
    try:
        print("🔧 Setting up MCP stdio transport...")

        # Bring up the MCP stdio transport & register remote tools
        processor, sm = await setup_mcp_stdio(
            config_file=CONFIG_FILE,
            servers=[TIME_SERVER],
            server_names={0: TIME_SERVER},
            namespace="stdio",
        )

        print("✅ MCP transport established")

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

        # SubprocessStrategy with fewer workers for stability
        print("🔧 Initializing subprocess strategy...")
        registry = await ToolRegistryProvider.get_registry()

        # Use fewer workers and longer timeout for stability
        strategy = SubprocessStrategy(registry, max_workers=2, default_timeout=10.0)
        executor = ToolExecutor(registry=registry, strategy=strategy)

        print(f"✅ ToolExecutor ready with {len(calls)} test calls")
        return executor, calls

    except Exception as e:
        show_error("Failed to bootstrap MCP environment", e)
        return None, []


# ────────────────────────────────────────────────────────────────────────────────
async def run_demo() -> None:
    """Run the main demonstration."""
    print("🚀 MCP Time Tool-Calling Demo (SubprocessStrategy)")
    print("=" * 60)

    # Verify configuration first
    if not await verify_config():
        return

    # Bootstrap the environment
    executor, calls = await bootstrap()
    if not executor:
        print("❌ Failed to set up MCP environment")
        return

    try:
        # ── Test individual call first ──────────────────────────────────────
        header("Testing single tool call")
        if calls:
            single_call = calls[0]
            print(f"🧪 Testing: {single_call.tool} with {single_call.arguments}")

            try:
                single_results = await executor.execute([single_call])
                if single_results:
                    show_result(single_call, single_results[0])
                else:
                    print("❌ No results returned from single call")
            except Exception as e:
                show_error("Single call failed", e)

        # ── Run in parallel ─────────────────────────────────────────────────
        header("Running calls in parallel")
        print(f"🔄 Executing {len(calls)} calls concurrently...")

        try:
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(executor.execute(calls), timeout=30.0)

            print(f"✅ Completed {len(results)} calls")

            for call, res in zip(calls, results, strict=False):
                show_result(call, res)

        except TimeoutError:
            print("❌ Parallel execution timed out after 30 seconds")
        except Exception as e:
            show_error("Parallel execution failed", e)

    finally:
        # ── Clean shutdown ──────────────────────────────────────────────────
        header("Cleaning up")
        try:
            print("🧹 Shutting down executor...")
            await executor.strategy.shutdown()
            print("✅ Cleanup completed")
        except Exception as e:
            # Don't fail on cleanup errors, just log them
            print(f"⚠️  Cleanup warning: {e}")


# ────────────────────────────────────────────────────────────────────────────────
def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


# ────────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    """Main entry point with comprehensive error handling."""
    setup_signal_handlers()

    try:
        await run_demo()
        print("\n🎉 Demo completed successfully!")

    except KeyboardInterrupt:
        print("\n👋 Demo interrupted by user")
    except Exception as e:
        show_error("Demo failed with unexpected error", e)
        sys.exit(1)


# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
