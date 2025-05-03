#!/usr/bin/env python
"""
mcp_stdio_resources_demo.py
Demonstrates pinging an MCP server and listing resources / prompts
via the new StreamManager helper-methods.

Prerequisites
-------------
* The MCP SQLite server must be defined in `server_config.json`
  under the name  "sqlite".
* All MCP / CHUK-TP packages are importable (run inside the repo venv).

Run it
------
$ uv run python mcp_stdio_resources_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

# ------------------------------------------------------------------ #
#  Local project imports                                             #
# ------------------------------------------------------------------ #
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chuk_tool_processor.logging import get_logger  # noqa: E402
from chuk_tool_processor.mcp import setup_mcp_stdio  # noqa: E402

logger = get_logger("mcp-resources-demo")

# ------------------------------------------------------------------ #
#  Config                                                            #
# ------------------------------------------------------------------ #
CONFIG_FILE = "server_config.json"
SQLITE_SERVER = "sqlite"


# ------------------------------------------------------------------ #
#  Bootstrap helper                                                  #
# ------------------------------------------------------------------ #
async def bootstrap_mcp() -> "StreamManager":  # type: ignore[name-defined]
    """
    Ensure *sqlite* is present in `server_config.json` and start/attach
    the stdio transport, returning the `StreamManager` instance.
    """
    if not os.path.exists(CONFIG_FILE):
        logger.error(
            "No %s found.   Add a 'sqlite' server definition first.", CONFIG_FILE
        )
        raise SystemExit(1)

    tp, sm = await setup_mcp_stdio(
        config_file=CONFIG_FILE,
        servers=[SQLITE_SERVER],
        server_names={0: SQLITE_SERVER},
        namespace="stdio",
    )
    return sm


# ------------------------------------------------------------------ #
#  Pretty-printers                                                   #
# ------------------------------------------------------------------ #
def print_header(title: str) -> None:
    print(Fore.CYAN + f"\n=== {title} ===" + Style.RESET_ALL)


def print_ping(ok: bool) -> None:
    colour = Fore.GREEN if ok else Fore.RED
    print(colour + ("✓ ping ok" if ok else "✗ ping failed") + Style.RESET_ALL)


# -------------------------------------------------- #
#  Pretty-printers  (FIXED)                          #
# -------------------------------------------------- #
def print_resources(res: List[dict[str, Any]]) -> None:        # ★ changed
    print(f"Received {len(res)} resources")
    for r in res:
        print(f"  • {r.get('uri', '<unknown>')}")


def print_prompts(res: List[dict[str, Any]]) -> None:          # ★ changed
    print(f"Received {len(res)} prompts")
    for p in res:
        line = f"  • {p.get('name', '<unnamed>')}"
        if desc := p.get("description"):
            line += f" – {desc}"
        print(line)

# ------------------------------------------------------------------ #
#  Demo                                                              #
# ------------------------------------------------------------------ #
async def run_demo() -> None:
    print_header("Connecting to MCP (sqlite)")
    sm = await bootstrap_mcp()

    # -- ping -------------------------------------------------------
    print_header("Ping")
    ok = await sm.transports[SQLITE_SERVER].send_ping()  # type: ignore[attr-defined]
    print_ping(ok)

    # -- resources --------------------------------------------------
    print_header("resources/list")
    resources = await sm.list_resources()  # type: ignore[attr-defined]
    print_resources(resources)

    # -- prompts ----------------------------------------------------
    print_header("prompts/list")
    prompts = await sm.list_prompts()  # type: ignore[attr-defined]
    print_prompts(prompts)

    # -- tidy up ----------------------------------------------------
    await sm.close()


# ------------------------------------------------------------------ #
#  Main                                                              #
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import logging

    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nInterrupted — exiting.")
