# chuk_tool_processor/execution/wrappers/retry.py
"""
Async-native retry wrapper for tool execution.

Adds exponential-back-off retry logic and *deadline-aware* timeout handling so a
`timeout=` passed by callers is treated as the **total wall-clock budget** for
all attempts of a single tool call.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from typing import Any

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = get_logger("chuk_tool_processor.execution.wrappers.retry")


# --------------------------------------------------------------------------- #
# Retry configuration
# --------------------------------------------------------------------------- #
class RetryConfig:
    """Configuration object that decides *whether* and *when* to retry."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        retry_on_exceptions: list[type[Exception]] | None = None,
        retry_on_error_substrings: list[str] | None = None,
    ):
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_on_exceptions = retry_on_exceptions or []
        self.retry_on_error_substrings = retry_on_error_substrings or []

    # --------------------------------------------------------------------- #
    # Decision helpers
    # --------------------------------------------------------------------- #
    def should_retry(  # noqa: D401  (imperative mood is fine)
        self,
        attempt: int,
        *,
        error: Exception | None = None,
        error_str: str | None = None,
    ) -> bool:
        """Return *True* iff another retry is allowed for this attempt."""
        if attempt >= self.max_retries:
            return False

        # Nothing specified → always retry until max_retries reached
        if not self.retry_on_exceptions and not self.retry_on_error_substrings:
            return True

        if error is not None and any(isinstance(error, exc) for exc in self.retry_on_exceptions):
            return True

        return bool(error_str and any(substr in error_str for substr in self.retry_on_error_substrings))

    # --------------------------------------------------------------------- #
    # Back-off
    # --------------------------------------------------------------------- #
    def get_delay(self, attempt: int) -> float:
        """Exponential back-off delay for *attempt* (0-based)."""
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        if self.jitter:
            delay *= 0.5 + random.random()  # jitter in [0.5, 1.5)
        return delay


# --------------------------------------------------------------------------- #
# Retryable executor
# --------------------------------------------------------------------------- #
class RetryableToolExecutor:
    """
    Wraps another executor and re-invokes it according to a :class:`RetryConfig`.
    """

    def __init__(
        self,
        executor: Any,
        *,
        default_config: RetryConfig | None = None,
        tool_configs: dict[str, RetryConfig] | None = None,
    ):
        self.executor = executor
        self.default_config = default_config or RetryConfig()
        self.tool_configs = tool_configs or {}

    # --------------------------------------------------------------------- #
    # Public helpers
    # --------------------------------------------------------------------- #
    def _config_for(self, tool: str) -> RetryConfig:
        return self.tool_configs.get(tool, self.default_config)

    async def execute(
        self,
        calls: list[ToolCall],
        *,
        timeout: float | None = None,
        use_cache: bool = True,
    ) -> list[ToolResult]:
        if not calls:
            return []

        out: list[ToolResult] = []
        for call in calls:
            cfg = self._config_for(call.tool)
            out.append(await self._execute_single(call, cfg, timeout, use_cache))
        return out

    # --------------------------------------------------------------------- #
    # Core retry loop (per call)
    # --------------------------------------------------------------------- #
    async def _execute_single(
        self,
        call: ToolCall,
        cfg: RetryConfig,
        timeout: float | None,
        use_cache: bool,
    ) -> ToolResult:
        attempt = 0
        last_error: str | None = None
        pid = 0
        machine = "unknown"

        # ---------------------------------------------------------------- #
        # Deadline budget (wall-clock)
        # ---------------------------------------------------------------- #
        deadline = None
        if timeout is not None:
            deadline = time.monotonic() + timeout

        while True:
            # ---------------------------------------------------------------- #
            # Check whether we have any time left *before* trying the call
            # ---------------------------------------------------------------- #
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ToolResult(
                        tool=call.tool,
                        result=None,
                        error=f"Timeout after {timeout}s",
                        start_time=datetime.now(UTC),
                        end_time=datetime.now(UTC),
                        machine=machine,
                        pid=pid,
                        attempts=attempt,
                    )
            else:
                remaining = None  # unlimited

            # ---------------------------------------------------------------- #
            # Execute one attempt
            # ---------------------------------------------------------------- #
            start_time = datetime.now(UTC)
            try:
                kwargs = {"timeout": remaining} if remaining is not None else {}
                if hasattr(self.executor, "use_cache"):
                    kwargs["use_cache"] = use_cache

                result = (await self.executor.execute([call], **kwargs))[0]
                pid = result.pid
                machine = result.machine

                # Success?
                if not result.error:
                    result.attempts = attempt + 1
                    return result

                # Error: decide on retry
                last_error = result.error
                if cfg.should_retry(attempt, error_str=result.error):
                    delay = cfg.get_delay(attempt)
                    # never overshoot the deadline
                    if deadline is not None:
                        delay = min(delay, max(deadline - time.monotonic(), 0))
                    if delay:
                        await asyncio.sleep(delay)
                    attempt += 1
                    continue

                # No more retries wanted
                result.error = self._wrap_error(last_error, attempt, cfg)
                result.attempts = attempt + 1
                return result

            # ---------------------------------------------------------------- #
            # Exception path
            # ---------------------------------------------------------------- #
            except Exception as exc:  # noqa: BLE001
                err_str = str(exc)
                last_error = err_str
                if cfg.should_retry(attempt, error=exc):
                    delay = cfg.get_delay(attempt)
                    if deadline is not None:
                        delay = min(delay, max(deadline - time.monotonic(), 0))
                    if delay:
                        await asyncio.sleep(delay)
                    attempt += 1
                    continue

                end_time = datetime.now(UTC)
                return ToolResult(
                    tool=call.tool,
                    result=None,
                    error=self._wrap_error(err_str, attempt, cfg),
                    start_time=start_time,
                    end_time=end_time,
                    machine=machine,
                    pid=pid,
                    attempts=attempt + 1,
                )

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _wrap_error(err: str, attempt: int, cfg: RetryConfig) -> str:
        if attempt >= cfg.max_retries and attempt > 0:
            return f"Max retries reached ({cfg.max_retries}): {err}"
        return err


# --------------------------------------------------------------------------- #
# Decorator helper
# --------------------------------------------------------------------------- #
def retryable(
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_on_exceptions: list[type[Exception]] | None = None,
    retry_on_error_substrings: list[str] | None = None,
):
    """
    Class decorator that attaches a :class:`RetryConfig` to a *tool* class.

    Example
    -------
    ```python
    @retryable(max_retries=5, base_delay=0.5)
    class MyTool:
        ...
    ```
    """

    def _decorator(cls):
        cls._retry_config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            jitter=jitter,
            retry_on_exceptions=retry_on_exceptions,
            retry_on_error_substrings=retry_on_error_substrings,
        )
        return cls

    return _decorator
