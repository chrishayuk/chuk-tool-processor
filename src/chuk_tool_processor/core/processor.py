#!/usr/bin/env python3
#!/usr/bin/env python3
"""Session‑aware tool processor for **chuk_tool_processor ≥ 0.8**.

Executes OpenAI `tool_calls` exclusively via **`ToolProcessor.process()`**—
no executor fall‑backs.  Adds in‑memory caching, configurable retries, and
records each call as a `TOOL_CALL` event in the A2A session tree.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List

from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.models.tool_result import ToolResult

from a2a_session_manager.models.event_source import EventSource
from a2a_session_manager.models.event_type import EventType
from a2a_session_manager.models.session_event import SessionEvent
from a2a_session_manager.storage import SessionStoreProvider

logger = logging.getLogger(__name__)


class SessionAwareToolProcessor:
    """Run tool‑calls, add retry/caching, log into session."""

    def __init__(
        self,
        session_id: str,
        *,
        enable_caching: bool = True,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:
        self.session_id = session_id
        self.enable_caching = enable_caching
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cache: Dict[str, Any] = {}
        self._tp = ToolProcessor()
        if not hasattr(self._tp, "process"):
            raise AttributeError(
                "Current chuk_tool_processor lacks .process(); this adapter "
                "supports only versions ≥ 0.8 where that API exists."
            )

    # factory ------------------------------------------------------------
    @classmethod
    async def create(cls, session_id: str, **kwargs):
        store = SessionStoreProvider.get_store()
        if not await store.get(session_id):
            raise ValueError(f"Session {session_id} not found")
        return cls(session_id=session_id, **kwargs)

    # helpers -------------------------------------------------------------
    async def _await(self, val: Any) -> Any:
        return await val if asyncio.iscoroutine(val) else val

    async def _process_calls(self, calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """Execute calls via `ToolProcessor.process()` (no fall‑back)."""
        results = await self._tp.process(calls)
        for r in results:
            r.result = await self._await(r.result)
        return results

    async def _log_event(
        self,
        session,
        parent_id: str,
        res: ToolResult,
        attempt: int,
        *,
        cached: bool,
        failed: bool = False,
    ) -> None:
        ev = await SessionEvent.create_with_tokens(
            message={
                "tool": res.tool,
                "arguments": getattr(res, "arguments", None),
                "result": res.result,
                "error": res.error,
                "cached": cached,
            },
            prompt=f"{res.tool}({json.dumps(getattr(res, 'arguments', None), default=str)})",
            completion=json.dumps(res.result, default=str) if res.result is not None else "",
            model="tool-execution",
            source=EventSource.SYSTEM,
            type=EventType.TOOL_CALL,
        )
        await ev.update_metadata("parent_event_id", parent_id)
        await ev.update_metadata("call_id", getattr(res, "id", "cid"))
        await ev.update_metadata("attempt", attempt)
        if failed:
            await ev.update_metadata("failed", True)
        await session.add_event_and_save(ev)

    # ------------------------------------------------------------------ #
    async def process_llm_message(self, llm_msg: Dict[str, Any], _) -> List[ToolResult]:
        store = SessionStoreProvider.get_store()
        session = await store.get(self.session_id)
        if not session:
            raise ValueError(f"Session {self.session_id} not found")

        parent_evt = await SessionEvent.create_with_tokens(
            message=llm_msg,
            prompt="",
            completion=json.dumps(llm_msg),
            model="gpt-4o-mini",
            source=EventSource.LLM,
            type=EventType.MESSAGE,
        )
        await session.add_event_and_save(parent_evt)

        calls = llm_msg.get("tool_calls", [])
        if not calls:
            return []

        out: List[ToolResult] = []
        for call in calls:
            cid = call.get("id", "cid")
            fn = call.get("function", {})
            name = fn.get("name", "tool")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {"raw": fn.get("arguments")}

            key = (
                hashlib.md5(f"{name}:{json.dumps(args, sort_keys=True)}".encode()).hexdigest()
                if self.enable_caching else None
            )

            if key and key in self.cache:
                cached: ToolResult = self.cache[key]
                await self._log_event(session, parent_evt.id, cached, 1, cached=True)
                out.append(cached)
                continue

            last_err: str | None = None
            for attempt in range(1, self.max_retries + 2):
                try:
                    res = (await self._process_calls([call]))[0]
                    if key:
                        self.cache[key] = res
                    await self._log_event(session, parent_evt.id, res, attempt, cached=False)
                    out.append(res)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    if attempt <= self.max_retries:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    err_res = ToolResult(tool=name, result=None, error=last_err)
                    await self._log_event(session, parent_evt.id, err_res, attempt, cached=False, failed=True)
                    out.append(err_res)

        return out
