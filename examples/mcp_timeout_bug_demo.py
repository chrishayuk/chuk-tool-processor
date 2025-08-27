#!/usr/bin/env python
"""
examples/mcp_timeout_bug_demo.py (cleaned)

Minimal demo that verifies the MCP timeout / retry behaviour
without the heavy-weight tracing that was needed during the bug hunt.

Run it with

    $ python examples/mcp_timeout_bug_demo.py

You should see each step finishing in ~timeout seconds rather than the full
20-second hang simulated by the mock transport.
"""

from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Local imports - add project root so `python examples/...` works everywhere.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.models.tool_call import ToolCall

# ---------------------------------------------------------------------------
# A minimal mock "hanging" SSE server/transport.
# ---------------------------------------------------------------------------


class _MockTransport:
    """Transport that *never* responds within the caller-supplied timeout."""

    async def initialize(self) -> bool:  # noqa: D401 - simple bool
        return True

    async def close(self) -> None:  # noqa: D401 - just a noop
        return None

    async def send_ping(self) -> bool:  # keep StreamManager happy
        return True

    async def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "hanging_tool",
                "description": "A tool that hangs forever (20s sleep)",
                "inputSchema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            }
        ]

    async def call_tool(self, _tool: str, _args: dict[str, Any]):
        print("      ↪ MockTransport.call_tool → sleeping 20s (simulating hang)")
        await asyncio.sleep(20)
        return {"isError": False, "content": "should never get here"}


@asynccontextmanager
async def _patched_stream_manager():
    """Patch StreamManager.create_with_sse so it uses the mock transport."""

    from chuk_tool_processor.mcp.stream_manager import StreamManager

    async def _factory(  # type: ignore[override] - signature comes from classmethod
        cls, servers, server_names=None
    ):
        mgr = StreamManager()
        transport = _MockTransport()
        mgr.transports = {"hanging_server": transport}
        mgr.server_info = [{"id": 0, "name": "hanging_server", "tools": 1, "status": "Up"}]
        mgr.tool_to_server_map = {"hanging_tool": "hanging_server"}
        mgr.all_tools = await transport.get_tools()
        return mgr

    orig = StreamManager.create_with_sse
    StreamManager.create_with_sse = classmethod(_factory)  # type: ignore[method-assign]
    try:
        yield
    finally:
        StreamManager.create_with_sse = orig  # restore


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


def _pretty(t: float) -> str:
    return f"{t:.3f}s"


async def _run_demo() -> None:
    print("=== MCP TIMEOUT DEMO (clean) ===\n")

    async with _patched_stream_manager():
        print("• Setting up MCP with mock hanging server …", end=" ", flush=True)
        processor, stream_manager = await setup_mcp_sse(
            servers=[{"name": "hanging_server", "url": "mock://hanging"}],
            namespace="mcp",
            default_timeout=2.0,  # baseline
        )
        print("done")

        # -------------------------------------------------------------------
        # 1️⃣ Processor.process (XML) with explicit timeout
        # -------------------------------------------------------------------
        print("\n1️⃣  processor.process() - expect ~3s timeout")
        start = time.perf_counter()
        result = await processor.process(
            '<tool name="mcp.hanging_tool" args="{"message": "hello"}"/>',
            timeout=3.0,
        )
        elapsed = time.perf_counter() - start
        _report(result[0].error, elapsed, expect=3.0)

        # -------------------------------------------------------------------
        # 2️⃣ Processor.execute (ToolCall) with explicit timeout
        # -------------------------------------------------------------------
        print("\n2️⃣  processor.execute() - expect ~1s timeout")
        tc = ToolCall(tool="hanging_tool", namespace="mcp", arguments={})
        start = time.perf_counter()
        result = await processor.execute([tc], timeout=1.0)
        elapsed = time.perf_counter() - start
        _report(result[0].error, elapsed, expect=1.0)

        # -------------------------------------------------------------------
        # 3️⃣ StreamManager.call_tool with timeout parameter
        # -------------------------------------------------------------------
        print("\n3️⃣  stream_manager.call_tool() - expect ~2s timeout")
        start = time.perf_counter()
        sm_result = await stream_manager.call_tool("hanging_tool", {"message": "hi"}, timeout=2.0)
        elapsed = time.perf_counter() - start
        _report(sm_result["error"], elapsed, expect=2.0)

        await stream_manager.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(err: str | None, elapsed: float, *, expect: float) -> None:
    """Pretty-print outcome and highlight if expectation wasn’t met."""

    status = "✅ OK" if err and abs(elapsed - expect) < 0.5 else "⚠️  ISSUE"
    print(f'   · elapsed {_pretty(elapsed)} → {status}; error="{err}"')


if __name__ == "__main__":
    asyncio.run(_run_demo())
