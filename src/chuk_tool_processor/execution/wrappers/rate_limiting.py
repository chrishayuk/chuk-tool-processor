# chuk_tool_processor/execution/wrappers/rate_limiting.py
"""
Async-native rate-limiting wrapper.

Two layers of limits are enforced:

* **Global** - ``<N requests> / <period>`` over *all* tools.
* **Per-tool** - independent ``<N requests> / <period>`` windows.

A simple sliding-window algorithm with timestamp queues is used.  
`asyncio.Lock` guards shared state so the wrapper can be used safely from
multiple coroutines.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# --------------------------------------------------------------------------- #
# Core limiter
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(
        self,
        *,
        global_limit: int | None = None,
        global_period: float = 60.0,
        tool_limits: Dict[str, Tuple[int, float]] | None = None,
    ) -> None:
        self.global_limit = global_limit
        self.global_period = global_period
        self.tool_limits = tool_limits or {}

        self._global_ts: List[float] = []
        self._tool_ts: Dict[str, List[float]] = {}

        self._global_lock = asyncio.Lock()
        self._tool_locks: Dict[str, asyncio.Lock] = {}

    # --------------------- helpers -------------------- #
    async def _acquire_global(self) -> None:
        """Block until a global slot is available."""
        if self.global_limit is None:
            return

        while True:
            async with self._global_lock:
                now = time.monotonic()
                cutoff = now - self.global_period
                self._global_ts = [t for t in self._global_ts if t > cutoff]

                if len(self._global_ts) < self.global_limit:
                    self._global_ts.append(now)
                    return

                wait = (self._global_ts[0] + self.global_period) - now

            await asyncio.sleep(wait)

    async def _acquire_tool(self, tool: str) -> None:
        """Block until a per-tool slot is available (if the tool has a limit)."""
        if tool not in self.tool_limits:
            return

        limit, period = self.tool_limits[tool]
        lock = self._tool_locks.setdefault(tool, asyncio.Lock())
        buf = self._tool_ts.setdefault(tool, [])

        while True:
            async with lock:
                now = time.monotonic()
                cutoff = now - period
                buf[:] = [t for t in buf if t > cutoff]

                if len(buf) < limit:
                    buf.append(now)
                    return

                wait = (buf[0] + period) - now
            await asyncio.sleep(wait)

    # ----------------------- public -------------------- #
    async def wait(self, tool: str) -> None:
        """Await until both global and per-tool windows allow one more call."""
        await self._acquire_global()
        await self._acquire_tool(tool)


# --------------------------------------------------------------------------- #
# Executor wrapper
# --------------------------------------------------------------------------- #
class RateLimitedToolExecutor:
    """Delegates to another executor but honours the given RateLimiter."""

    def __init__(self, executor: Any, limiter: RateLimiter) -> None:
        self.executor = executor
        self.limiter = limiter

    async def execute(
        self,
        calls: List[ToolCall],
        *,
        timeout: float | None = None,
    ) -> List[ToolResult]:
        # Block for each call *before* dispatching to the wrapped executor
        for c in calls:
            await self.limiter.wait(c.tool)
        return await self.executor.execute(calls, timeout=timeout)


# --------------------------------------------------------------------------- #
# Convenience decorator for tools
# --------------------------------------------------------------------------- #
def rate_limited(limit: int, period: float = 60.0):
    """
    Class decorator that marks a Tool with default rate-limit metadata.

    Higher-level orchestration can read ``cls._rate_limit`` /
    ``cls._rate_period`` to auto-configure a ``RateLimiter``.
    """

    def decorator(cls):
        cls._rate_limit = limit
        cls._rate_period = period
        return cls

    return decorator
