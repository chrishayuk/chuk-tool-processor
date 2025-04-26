# chuk_tool_processor/logging/helpers.py
from __future__ import annotations
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Optional

from .context import get_logger, log_context
from .metrics import metrics  # re-export convenience

__all__ = [
    "log_context_span",
    "request_logging",
    "log_tool_call",
    "metrics",
]

# --------------------------------------------------------------------------- #
# context-manager helpers
# --------------------------------------------------------------------------- #
@contextmanager
def log_context_span(operation: str, extra: Dict | None = None, *, log_duration=True):
    logger = get_logger(f"chuk_tool_processor.span.{operation}")
    start = time.time()
    span_id = str(uuid.uuid4())
    span_ctx = {
        "span_id": span_id,
        "operation": operation,
        "start_time": datetime.fromtimestamp(start, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if extra:
        span_ctx.update(extra)
    prev = log_context.get_copy()
    log_context.update(span_ctx)

    logger.info("Starting %s", operation)
    try:
        yield
        if log_duration:
            logger.info(
                "Completed %s", operation, extra={"context": {"duration": time.time() - start}}
            )
        else:
            logger.info("Completed %s", operation)
    except Exception as exc:
        logger.exception(
            "Error in %s: %s", operation, exc, extra={"context": {"duration": time.time() - start}}
        )
        raise
    finally:
        log_context.clear()
        if prev:
            log_context.update(prev)


@contextmanager
def request_logging(request_id: str | None = None):
    logger = get_logger("chuk_tool_processor.request")
    request_id = log_context.start_request(request_id)
    start = time.time()
    logger.info("Starting request %s", request_id)
    try:
        yield request_id
        logger.info(
            "Completed request %s",
            request_id,
            extra={"context": {"duration": time.time() - start}},
        )
    except Exception as exc:
        logger.exception(
            "Error in request %s: %s",
            request_id,
            exc,
            extra={"context": {"duration": time.time() - start}},
        )
        raise
    finally:
        log_context.end_request()


# --------------------------------------------------------------------------- #
# high-level helper
# --------------------------------------------------------------------------- #
def log_tool_call(tool_call, tool_result):
    logger = get_logger("chuk_tool_processor.tool_call")
    dur = (tool_result.end_time - tool_result.start_time).total_seconds()

    ctx = {
        "tool": tool_call.tool,
        "arguments": tool_call.arguments,
        "result": (
            tool_result.result.model_dump()
            if hasattr(tool_result.result, "model_dump")
            else tool_result.result
        ),
        "error": tool_result.error,
        "duration": dur,
        "machine": tool_result.machine,
        "pid": tool_result.pid,
    }
    if getattr(tool_result, "cached", False):
        ctx["cached"] = True
    if getattr(tool_result, "attempts", 0):
        ctx["attempts"] = tool_result.attempts

    if tool_result.error:
        logger.error("Tool %s failed: %s", tool_call.tool, tool_result.error, extra={"context": ctx})
    else:
        logger.info("Tool %s succeeded in %.3fs", tool_call.tool, dur, extra={"context": ctx})
