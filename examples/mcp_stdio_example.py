#!/usr/bin/env python
# examples/mcp_stdio_example.py
"""
Demo: wire a remote MCP "time" server into CHUK via **stdio** transport.

Prerequisites
-------------
Nothing but `uv` installed - the time-server will be fetched on-the-fly
(`uvx mcp-server-time …`).

What it shows
-------------
1. create / reuse a minimal server-config JSON
2. initialise the stdio StreamManager & register the remote tools
3. list everything that landed in the registry
4. look up the wrapper for `get_current_time` and call it directly
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
#  main demo                                                            #
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
        # 4️⃣  Proper cleanup
        if stream_manager:
            try:
                # Give a short timeout for graceful shutdown
                await asyncio.wait_for(stream_manager.close(), timeout=1.0)
            except asyncio.TimeoutError:
                print("⚠️  Stream manager close timed out (this is normal)")
            except asyncio.CancelledError:
                # This can happen during event loop shutdown
                pass
            except Exception as e:
                print(f"⚠️  Error during cleanup: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✋ Interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)