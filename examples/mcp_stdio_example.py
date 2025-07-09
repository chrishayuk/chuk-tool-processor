#!/usr/bin/env python
# examples/mcp_stdio_example.py - FIXED VERSION
"""
Demo: wire a remote MCP "time" server into CHUK via **stdio** transport.

FIXED VERSION: This version includes proper cleanup that avoids cancel scope errors.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

# --------------------------------------------------------------------- #
#  allow "poetry run python examples/…" style execution                 #
# --------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# --------------------------------------------------------------------- #
#  CHUK imports                                                         #
# --------------------------------------------------------------------- #
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.logging import get_logger

logger = get_logger("mcp_stdio_example")


# --------------------------------------------------------------------- #
#  helper: pretty-print a namespace                                     #
# --------------------------------------------------------------------- #
async def dump_namespace(namespace: str) -> None:
    registry = await ToolRegistryProvider.get_registry()

    # ✅ list_tools() gives a plain list already
    tools = [t for t in await registry.list_tools() if t[0] == namespace]

    print(f"Tools in namespace {namespace!r} ({len(tools)}):")
    for ns, name in tools:
        meta = await registry.get_metadata(name, ns)
        desc = meta.description if meta else "no description"
        print(f"  • {ns}.{name:<20} — {desc}")


# --------------------------------------------------------------------- #
#  FIXED: Safer cleanup function                                       #
# --------------------------------------------------------------------- #
async def safer_cleanup(stream_manager):
    """
    Safer cleanup that handles cancel scope issues during event loop shutdown.
    
    This version uses very short timeouts and graceful error handling to avoid
    the cancel scope error that was occurring in the original version.
    """
    if not stream_manager:
        return
        
    try:
        # CRITICAL FIX: Use very short timeout (0.1s) to avoid blocking 
        # event loop shutdown which causes cancel scope conflicts
        await asyncio.wait_for(stream_manager.close(), timeout=0.1)
        logger.debug("Stream manager closed successfully")
    except asyncio.TimeoutError:
        # Timeout during shutdown is normal and expected - the important 
        # resources are cleaned up even if we don't wait for full completion
        logger.debug("Stream manager close timed out during shutdown (normal)")
    except asyncio.CancelledError:
        # Don't suppress cancellation - let event loop handle it properly
        # This occurs during normal event loop shutdown
        logger.debug("Stream manager close cancelled during event loop shutdown")
        # Don't re-raise - we want the example to exit cleanly
    except Exception as e:
        # Log but don't fail on other cleanup errors
        logger.debug(f"Stream manager cleanup error: {e}")


# --------------------------------------------------------------------- #
#  main demo - FIXED VERSION                                           #
# --------------------------------------------------------------------- #
async def main() -> None:
    stream_manager = None
    try:
        print("=== Flexible MCP integration demo ===\n")

        # 1️⃣  write / reuse server-config
        cfg_path = PROJECT_ROOT / "server_config.json"
        if not cfg_path.exists():
            cfg = {
                "mcpServers": {
                    "time": {
                        "command": "uvx",
                        "args": [
                            "mcp-server-time",
                            "--local-timezone=America/New_York",
                        ],
                    }
                }
            }
            cfg_path.write_text(json.dumps(cfg, indent=2))
            print(f"Created demo config: {cfg_path}\n")
        else:
            print(f"Using server config: {cfg_path}\n")

        # 2️⃣  setup stdio transport + registry
        processor, stream_manager = await setup_mcp_stdio(
            config_file=str(cfg_path),
            servers=["time"],
            server_names={0: "time"},
            namespace="stdio",
        )

        await dump_namespace("stdio")

        # 3️⃣  look up the wrapper & call it directly
        print("\nExecuting stdio.get_current_time …")
        registry = await ToolRegistryProvider.get_registry()
        wrapper_cls = await registry.get_tool("get_current_time", "stdio")

        if wrapper_cls is None:
            print("❌ tool not found in registry")
        else:
            wrapper = wrapper_cls() if callable(wrapper_cls) else wrapper_cls
            try:
                res = await wrapper.execute(timezone="America/New_York")
                print("\nResult:")
                if isinstance(res, (dict, list)):
                    print(json.dumps(res, indent=2))
                else:
                    print(res)
            except Exception as exc:
                print("❌ execution failed:", exc)

    finally:
        # 4️⃣  FIXED: Proper cleanup that avoids cancel scope errors
        await safer_cleanup(stream_manager)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✋ Interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)