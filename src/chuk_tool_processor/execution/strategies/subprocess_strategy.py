# chuk_tool_processor/execution/subprocess_strategy.py
"""
“Subprocess” execution strategy - async-native version
=====================================================

For now this class is a *thin* wrapper around
:class:`~chuk_tool_processor.execution.strategies.inprocess_strategy.InProcessStrategy`.
That keeps behaviour identical to the old implementation while the
code-base completes its async migration.  A real ``ProcessPoolExecutor``
backend can be swapped in later without touching any call-sites.

Key points
----------
* **No synchronous fall-backs** – tools must expose an *async* entry point
  (``_aexecute`` or ``execute`` coroutine).
* Constructor still accepts ``max_workers`` and ``default_timeout`` so
  existing user code and tests (that monkey-patch
  ``inprocess_strategy.InProcessStrategy``) continue to work.
"""
from __future__ import annotations

from typing import List, Optional

from chuk_tool_processor.execution.strategies.inprocess_strategy import (
    InProcessStrategy,
)
from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

# --------------------------------------------------------------------------- #
class SubprocessStrategy(ExecutionStrategy):
    """Delegate every call to an internal :class:`InProcessStrategy`."""

    def __init__(
        self,
        registry,
        *,
        max_workers: int = 4,
        default_timeout: Optional[float] = None,
    ) -> None:
        self._delegate = InProcessStrategy(
            registry=registry,
            default_timeout=default_timeout,
            max_concurrency=max_workers,
        )

    # ------------------------------------------------------------------ #
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None,
    ) -> List[ToolResult]:
        """Execute *calls* via the delegated async strategy."""
        return await self._delegate.run(calls, timeout=timeout)
