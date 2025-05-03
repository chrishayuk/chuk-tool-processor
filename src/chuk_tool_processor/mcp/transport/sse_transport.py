# chuk_tool_processor/mcp/transport/sse_transport.py
"""
Server-Sent Events (SSE) transport for MCP communication – implemented with **httpx**.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Dict, List, Optional

import httpx

from .base_transport import MCPBaseTransport

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
DEFAULT_TIMEOUT = 5.0  # seconds
HEADERS_JSON: Dict[str, str] = {"accept": "application/json"}


def _url(base: str, path: str) -> str:
    """Join *base* and *path* with exactly one slash."""
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# --------------------------------------------------------------------------- #
# Transport                                                                   #
# --------------------------------------------------------------------------- #
class SSETransport(MCPBaseTransport):
    """
    Minimal SSE/REST transport.  It speaks a simple REST dialect:

        GET  /ping                → 200 OK
        GET  /tools/list          → {"tools": [...]}
        POST /tools/call          → {"name": ..., "result": ...}
        GET  /resources/list      → {"resources": [...]}
        GET  /prompts/list        → {"prompts": [...]}
        GET  /events              → <text/event-stream>
    """

    EVENTS_PATH = "/events"

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #
    def __init__(self, url: str, api_key: Optional[str] = None) -> None:
        self.base_url = url.rstrip("/")
        self.api_key = api_key

        # httpx client (None until initialise)
        self._client: httpx.AsyncClient | None = None
        self.session: httpx.AsyncClient | None = None  # ← kept for legacy tests

        # background reader
        self._reader_task: asyncio.Task | None = None
        self._incoming_queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue()

    # ------------------------------------------------------------------ #
    # Life-cycle                                                         #
    # ------------------------------------------------------------------ #
    async def initialize(self) -> bool:
        """Open the httpx client and start the /events consumer."""
        if self._client:  # already initialised
            return True

        self._client = httpx.AsyncClient(
            headers={"authorization": self.api_key} if self.api_key else None,
            timeout=DEFAULT_TIMEOUT,
        )
        self.session = self._client  # legacy attribute for tests

        # spawn reader (best-effort reconnect)
        self._reader_task = asyncio.create_task(self._consume_events(), name="sse-reader")

        # verify connection
        return await self.send_ping()

    async def close(self) -> None:
        """Stop background reader and close the httpx client."""
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self._client:
            await self._client.aclose()
            self._client = None
            self.session = None  # keep tests happy

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #
    async def _get_json(self, path: str) -> Any:
        if not self._client:
            raise RuntimeError("Transport not initialised")

        resp = await self._client.get(_url(self.base_url, path), headers=HEADERS_JSON)
        resp.raise_for_status()
        return resp.json()

    async def _post_json(self, path: str, payload: Dict[str, Any]) -> Any:
        if not self._client:
            raise RuntimeError("Transport not initialised")

        resp = await self._client.post(
            _url(self.base_url, path), json=payload, headers=HEADERS_JSON
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Public API (implements MCPBaseTransport)                           #
    # ------------------------------------------------------------------ #
    async def send_ping(self) -> bool:
        if not self._client:
            return False
        try:
            await self._get_json("/ping")
            return True
        except Exception:  # pragma: no cover
            return False

    async def get_tools(self) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        try:
            data = await self._get_json("/tools/list")
            return data.get("tools", []) if isinstance(data, dict) else []
        except Exception:  # pragma: no cover
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # ─── tests expect this specific message if *not* initialised ───
        if not self._client:
            return {"isError": True, "error": "SSE transport not implemented"}

        try:
            payload = {"name": tool_name, "arguments": arguments}
            return await self._post_json("/tools/call", payload)
        except Exception as exc:  # pragma: no cover
            return {"isError": True, "error": str(exc)}

    # ----------------------- extras used by StreamManager ------------- #
    async def list_resources(self) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        try:
            data = await self._get_json("/resources/list")
            return data.get("resources", []) if isinstance(data, dict) else []
        except Exception:  # pragma: no cover
            return []

    async def list_prompts(self) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        try:
            data = await self._get_json("/prompts/list")
            return data.get("prompts", []) if isinstance(data, dict) else []
        except Exception:  # pragma: no cover
            return []

    # ------------------------------------------------------------------ #
    # Background event-stream reader                                     #
    # ------------------------------------------------------------------ #
    async def _consume_events(self) -> None:  # pragma: no cover
        """Continuously read `/events` and push JSON objects onto a queue."""
        if not self._client:
            return

        while True:
            try:
                async with self._client.stream(
                    "GET", _url(self.base_url, self.EVENTS_PATH), headers=HEADERS_JSON
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            await self._incoming_queue.put(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)  # back-off and retry
