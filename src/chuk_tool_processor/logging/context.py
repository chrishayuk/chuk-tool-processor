# chuk_tool_processor/logging/context.py
"""
Async-safe context management for structured logging.

This module provides:

* **LogContext** – an `asyncio`-aware container that keeps a per-task dict of
  contextual data (request IDs, span IDs, arbitrary metadata, …).
* **log_context** – a global instance of `LogContext` for convenience.
* **StructuredAdapter** – a `logging.LoggerAdapter` that injects the current
  `log_context.context` into every log record.
* **get_logger** – helper that returns a configured `StructuredAdapter`.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import uuid
from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Dict,
    Optional,
)

__all__ = ["LogContext", "log_context", "StructuredAdapter", "get_logger"]

# --------------------------------------------------------------------------- #
# Per-task context storage
# --------------------------------------------------------------------------- #

_context_var: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "log_context", default={}
)


# --------------------------------------------------------------------------- #
# Helpers for turning async generators into async context managers
# --------------------------------------------------------------------------- #
class AsyncContextManagerWrapper(AsyncContextManager):
    """Wrap an async generator so it can be used with `async with`."""

    def __init__(self, gen: AsyncGenerator[Any, None]):
        self._gen = gen

    async def __aenter__(self):
        return await self._gen.__anext__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                # Normal exit
                await self._gen.__anext__()
            else:
                # Propagate the exception into the generator
                try:
                    await self._gen.athrow(exc_type, exc_val, exc_tb)
                except StopAsyncIteration:
                    return False
                # If the generator swallowed the exception, suppress it;
                # otherwise, propagate.
                return True
        except StopAsyncIteration:
            return False


# --------------------------------------------------------------------------- #
# LogContext
# --------------------------------------------------------------------------- #
class LogContext:
    """
    Async-safe context container.

    Holds a mutable dict that is *local* to the current asyncio task, so
    concurrent coroutines don’t interfere with each other.
    """

    # ------------------------------------------------------------------ #
    # Dunders / basic helpers
    # ------------------------------------------------------------------ #
    def __init__(self) -> None:
        self._reset_token()

    def _reset_token(self) -> None:
        self._token = _context_var.set({})

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def context(self) -> Dict[str, Any]:
        """Return the current context dict (task-local)."""
        return _context_var.get()

    @property
    def request_id(self) -> Optional[str]:
        """Convenience accessor for the current request ID (if any)."""
        return self.context.get("request_id")

    # -- simple helpers ------------------------------------------------- #
    def update(self, kv: Dict[str, Any]) -> None:
        """Merge *kv* into the current context."""
        ctx = self.context.copy()
        ctx.update(kv)
        _context_var.set(ctx)

    def clear(self) -> None:
        """Drop **all** contextual data."""
        _context_var.set({})

    def get_copy(self) -> Dict[str, Any]:
        """Return a **copy** of the current context."""
        return self.context.copy()

    # -- request helpers ------------------------------------------------ #
    def start_request(self, request_id: Optional[str] = None) -> str:
        """
        Start a new *request* scope.

        Returns the request ID (generated if not supplied).
        """
        rid = request_id or str(uuid.uuid4())
        ctx = self.context.copy()
        ctx["request_id"] = rid
        _context_var.set(ctx)
        return rid

    def end_request(self) -> None:
        """Clear request data (alias for :py:meth:`clear`)."""
        self.clear()

    # ------------------------------------------------------------------ #
    # Async context helpers
    # ------------------------------------------------------------------ #
    async def _context_scope_gen(
        self, **kwargs: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        prev_ctx = self.get_copy()
        try:
            self.update(kwargs)
            yield self.context
        finally:
            _context_var.set(prev_ctx)

    def context_scope(self, **kwargs: Any) -> AsyncContextManager:
        """
        Temporarily add *kwargs* to the context.

        Usage
        -----
        ```python
        async with log_context.context_scope(user_id=42):
            ...
        ```
        """
        return AsyncContextManagerWrapper(self._context_scope_gen(**kwargs))

    async def _request_scope_gen(
        self, request_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        prev_ctx = self.get_copy()
        try:
            rid = self.start_request(request_id)
            await asyncio.sleep(0)  # allow caller code to run
            yield rid
        finally:
            _context_var.set(prev_ctx)

    def request_scope(self, request_id: Optional[str] = None) -> AsyncContextManager:
        """
        Manage a full request lifecycle::

            async with log_context.request_scope():
                ...
        """
        return AsyncContextManagerWrapper(self._request_scope_gen(request_id))


# A convenient global instance that most code can just import and use.
log_context = LogContext()

# --------------------------------------------------------------------------- #
# StructuredAdapter
# --------------------------------------------------------------------------- #
class StructuredAdapter(logging.LoggerAdapter):
    """
    `logging.LoggerAdapter` that injects the current async context.

    We also override the convenience level-methods (`info`, `debug`, …) to call
    the **public** methods of the wrapped logger instead of the private
    `Logger._log()`.  This makes it straightforward to patch / mock them in
    tests (see *tests/logging/test_context.py*).
    """

    # --------------------------- core hook -------------------------------- #
    def process(self, msg, kwargs):  # noqa: D401 – keep signature from base
        kwargs = kwargs or {}
        extra = kwargs.get("extra", {}).copy()
        ctx = log_context.context
        if ctx:
            extra["context"] = {**extra.get("context", {}), **ctx}
        kwargs["extra"] = extra
        return msg, kwargs

    # ----------------------- convenience wrappers ------------------------ #
    def _forward(self, method_name: str, msg, *args, **kwargs):
        """Common helper: process + forward to `self.logger.<method_name>`."""
        msg, kwargs = self.process(msg, kwargs)
        getattr(self.logger, method_name)(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self._forward("debug", msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._forward("info", msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._forward("warning", msg, *args, **kwargs)

    warn = warning  # compat

    def error(self, msg, *args, **kwargs):
        self._forward("error", msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._forward("critical", msg, *args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        # `exc_info` defaults to True - align with stdlib behaviour
        self._forward("exception", msg, *args, exc_info=exc_info, **kwargs)


# --------------------------------------------------------------------------- #
# Public helper
# --------------------------------------------------------------------------- #
def get_logger(name: str) -> StructuredAdapter:
    """
    Return a :class:`StructuredAdapter` wrapping ``logging.getLogger(name)``.
    """
    return StructuredAdapter(logging.getLogger(name), {})
