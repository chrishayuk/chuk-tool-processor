#!/usr/bin/env python
"""
mcp_stdio_resources_demo.py

Ping an MCP server started via **stdio** and show its `resources/list`
and `prompts/list` catalogues.

Prerequisites
-------------
* `server_config.json` must contain a server entry called "sqlite"
  that can be started with `uvx` or any other command.
* Run inside the project's virtual-env.

Usage
-----
$ uv run python examples/mcp_stdio_resources_demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from colorama import Fore, Style, init as colorama_init

# --------------------------------------------------------------------------- #
#  Colour output setup                                                        #
# --------------------------------------------------------------------------- #
colorama_init(autoreset=True)

def c(text: str, colour: str) -> str:
    return f"{colour}{text}{Style.RESET_ALL}"


# --------------------------------------------------------------------------- #
#  Local imports (allow running file directly)                                #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.logging import get_logger            # noqa: E402
from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio   # noqa: E402
from chuk_tool_processor.mcp.stream_manager import StreamManager      # noqa: E402

logger = get_logger("mcp-resources-demo")

# --------------------------------------------------------------------------- #
#  Config                                                                     #
# --------------------------------------------------------------------------- #
CONFIG_FILE = PROJECT_ROOT / "server_config.json"
SQLITE_SERVER = "sqlite"


# --------------------------------------------------------------------------- #
#  Bootstrap                                                                  #
# --------------------------------------------------------------------------- #
async def bootstrap() -> StreamManager:
    """
    Fire up the *sqlite* MCP server defined in ``server_config.json``
    and return the ready `StreamManager`.
    """
    if not CONFIG_FILE.exists():
        logger.error("Missing %s - add a 'sqlite' server definition first.", CONFIG_FILE)
        raise SystemExit(1)

    _, sm = await setup_mcp_stdio(
        config_file=str(CONFIG_FILE),
        servers=[SQLITE_SERVER],
        server_names={0: SQLITE_SERVER},
        namespace="stdio",
    )
    return sm


# --------------------------------------------------------------------------- #
#  Pretty-printers                                                           #
# --------------------------------------------------------------------------- #
def hdr(title: str) -> None:
    print(c(f"\n=== {title} ===", Fore.CYAN))


def show_ping(ok: bool) -> None:
    colour = Fore.GREEN if ok else Fore.RED
    symbol = "✓" if ok else "✗"
    print(c(f"{symbol} ping {'ok' if ok else 'failed'}", colour))


# -------------------------------------------------- #
#  Pretty-printers                                   #
# -------------------------------------------------- #
def show_resources(payload: Any) -> None:
    """
    Accept the raw reply from `resources/list` and print it.

    The server may return either a plain list *or* a dict
    like {"resources":[...], ...}.  Handle both.
    """
    resources = (
        payload.get("resources", [])            # dict shape
        if isinstance(payload, dict)
        else payload                            # plain list
    )
    print(f"Received {len(resources)} resources")
    for r in resources:
        print(f"  • {r.get('uri', '<unknown>')}")


def show_prompts(payload: Any) -> None:
    """Pretty-print the reply from `prompts/list`."""
    prompts = (
        payload.get("prompts", [])              # dict shape
        if isinstance(payload, dict)
        else payload                            # plain list
    )
    print(f"Received {len(prompts)} prompts")
    for p in prompts:
        line = f"  • {p.get('name', '<unnamed>')}"
        if desc := p.get("description"):
            line += f" - {desc}"
        print(line)


# --------------------------------------------------------------------------- #
#  Demo logic                                                                 #
# --------------------------------------------------------------------------- #
async def run_demo() -> None:
    hdr("Connecting to MCP (sqlite)")
    sm = await bootstrap()

    # ── ping ───────────────────────────────────────────────────────────────
    hdr("Ping")
    ping_ok = await sm.transports[SQLITE_SERVER].send_ping()  # type: ignore[attr-defined]
    show_ping(ping_ok)

    # ── resources/list ────────────────────────────────────────────────────
    hdr("resources/list")
    resources_payload = await sm.list_resources()             # type: ignore[attr-defined]
    show_resources(resources_payload)

    # ── prompts/list ──────────────────────────────────────────────────────
    hdr("prompts/list")
    prompts_payload = await sm.list_prompts()                 # type: ignore[attr-defined]
    show_prompts(prompts_payload)

    # ── tidy up ───────────────────────────────────────────────────────────
    await sm.close()


# --------------------------------------------------------------------------- #
#  Entrypoint                                                                 #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import logging

    # honour LOGLEVEL env-var for quick debugging
    logging.getLogger("chuk_tool_processor").setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper())
    )

    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nInterrupted — exiting.")
