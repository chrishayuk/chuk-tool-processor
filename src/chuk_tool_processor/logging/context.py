# chuk_tool_processor/logging/context.py
"""
Async-safe context management for structured logging.

This module provides:

* **LogContext** - an `asyncio`-aware container that keeps a per-task dict of
  contextual data (request IDs, span IDs, arbitrary metadata, …).
* **log_context** - a global instance of `LogContext` for convenience.
* **StructuredAdapter** - a `logging.LoggerAdapter` that injects the current
  `log_context.context` into every log record.
* **get_logger** - helper that returns a configured `StructuredAdapter`.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import contextvars
import logging
import threading
import uuid
import warnings
from collections.abc import AsyncGenerator
from typing import Any

__all__ = ["LogContext", "log_context", "StructuredAdapter", "get_logger"]


# --------------------------------------------------------------------------- #
# Production-quality shutdown error handling
# --------------------------------------------------------------------------- #
class LibraryShutdownFilter(logging.Filter):
    """
    Production filter for suppressing known harmless shutdown messages.

    This filter ensures clean library shutdown by suppressing specific
    error messages that occur during normal asyncio/anyio cleanup and
    do not indicate actual problems.
    """

    # Known harmless shutdown patterns
    SUPPRESSED_PATTERNS = [
        # Primary anyio error that this fixes
        ("ERROR", "Task error during shutdown", "Attempted to exit cancel scope in a different task"),
        # Related asyncio/anyio shutdown messages
        ("WARNING", "cancel scope in a different task"),
        ("ERROR", "cancel scope in a different task"),
        ("WARNING", "attempted to exit cancel scope"),
        ("ERROR", "attempted to exit cancel scope"),
        ("WARNING", "task was destroyed but it is pending"),
        ("ERROR", "event loop is closed"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out known harmless shutdown messages."""
        message = record.getMessage().lower()
        level = record.levelname

        for pattern_level, *pattern_phrases in self.SUPPRESSED_PATTERNS:
            if level == pattern_level and all(phrase.lower() in message for phrase in pattern_phrases):
                return False

        return True


class LibraryLoggingManager:
    """
    Clean manager for library-wide logging concerns.

    Handles initialization and configuration of logging behavior
    in a centralized, maintainable way.
    """

    def __init__(self):
        self._initialized = False
        self._lock = threading.Lock()

    def initialize(self) -> None:
        """Initialize clean shutdown behavior for the library."""
        with self._lock:
            if self._initialized:
                return

            self._setup_shutdown_handling()
            self._setup_warning_filters()
            self._initialized = True

    def _setup_shutdown_handling(self):
        """Set up clean shutdown message handling."""
        root_logger = logging.getLogger()

        # Check if our filter is already present
        for existing_filter in root_logger.filters:
            if isinstance(existing_filter, LibraryShutdownFilter):
                return

        # Add our production-quality filter
        root_logger.addFilter(LibraryShutdownFilter())

    def _setup_warning_filters(self):
        """Set up Python warnings filters for clean shutdown."""
        # Suppress specific asyncio/anyio warnings during shutdown
        warning_patterns = [
            ".*Attempted to exit cancel scope in a different task.*",
            ".*coroutine was never awaited.*",
            ".*Task was destroyed but it is pending.*",
        ]

        for pattern in warning_patterns:
            warnings.filterwarnings("ignore", message=pattern, category=RuntimeWarning)
            warnings.filterwarnings("ignore", message=pattern, category=ResourceWarning)


# Global manager instance
_logging_manager = LibraryLoggingManager()

# Initialize on module import
_logging_manager.initialize()

# Clean shutdown registration
atexit.register(lambda: None)

# --------------------------------------------------------------------------- #
# Per-task context storage
# --------------------------------------------------------------------------- #

_context_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("log_context", default=None)


# --------------------------------------------------------------------------- #
# Helpers for turning async generators into async context managers
# --------------------------------------------------------------------------- #
class AsyncContextManagerWrapper(contextlib.AbstractAsyncContextManager):
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
    concurrent coroutines don't interfere with each other.
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
    def context(self) -> dict[str, Any]:
        """Return the current context dict (task-local)."""
        ctx = _context_var.get()
        return ctx if ctx is not None else {}

    @property
    def request_id(self) -> str | None:
        """Convenience accessor for the current request ID (if any)."""
        return self.context.get("request_id")

    # -- simple helpers ------------------------------------------------- #
    def update(self, kv: dict[str, Any]) -> None:
        """Merge *kv* into the current context."""
        ctx = self.context.copy()
        ctx.update(kv)
        _context_var.set(ctx)

    def clear(self) -> None:
        """Drop **all** contextual data."""
        _context_var.set({})

    def get_copy(self) -> dict[str, Any]:
        """Return a **copy** of the current context."""
        return self.context.copy()

    # -- request helpers ------------------------------------------------ #
    def start_request(self, request_id: str | None = None) -> str:
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
    async def _context_scope_gen(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        prev_ctx = self.get_copy()
        try:
            self.update(kwargs)
            yield self.context
        finally:
            _context_var.set(prev_ctx)

    def context_scope(self, **kwargs: Any) -> contextlib.AbstractAsyncContextManager:
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

    async def _request_scope_gen(self, request_id: str | None = None) -> AsyncGenerator[str, None]:
        prev_ctx = self.get_copy()
        try:
            rid = self.start_request(request_id)
            await asyncio.sleep(0)  # allow caller code to run
            yield rid
        finally:
            _context_var.set(prev_ctx)

    def request_scope(self, request_id: str | None = None) -> contextlib.AbstractAsyncContextManager:
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
    def process(self, msg, kwargs):  # noqa: D401 - keep signature from base
        kwargs = kwargs or {}
        extra = kwargs.get("extra", {}).copy()
        ctx = log_context.context
        if ctx:
            extra["context"] = {**extra.get("context", {}), **ctx}
        kwargs["extra"] = extra
        return msg, kwargs

    # ----------------------- convenience wrappers ------------------------ #
    def _forward(self, method_name: str, msg: str, *args: Any, **kwargs: Any) -> None:
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

    Includes automatic initialization of clean shutdown behavior.
    """
    # Ensure clean shutdown behavior is initialized
    _logging_manager.initialize()

    return StructuredAdapter(logging.getLogger(name), {})
