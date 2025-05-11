# chuk_tool_processor/logging/helpers.py
"""
Async-native logging helpers for tracing and monitoring tool execution.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional, AsyncGenerator

# Import context directly - avoid circular imports
from .context import get_logger, log_context

__all__ = [
    "log_context_span",
    "request_logging",
    "log_tool_call"
]

# --------------------------------------------------------------------------- #
# async context-manager helpers
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def log_context_span(
    operation: str, 
    extra: Optional[Dict[str, Any]] = None, 
    *, 
    log_duration: bool = True
) -> AsyncGenerator[None, None]:
    """
    Create an async context manager for a logging span.
    
    This context manager tracks the execution of an operation,
    logging its start, completion, and duration.
    
    Args:
        operation: Name of the operation
        extra: Optional additional context to include
        log_duration: Whether to log the duration
        
    Yields:
        Nothing
    """
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


@asynccontextmanager
async def request_logging(
    request_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Create an async context manager for request logging.
    
    This context manager tracks a request from start to finish,
    including duration and any errors.
    
    Args:
        request_id: Optional request ID (generated if not provided)
        
    Yields:
        The request ID
    """
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
async def log_tool_call(tool_call: Any, tool_result: Any) -> None:
    """
    Log a tool call and its result.
    
    Args:
        tool_call: The tool call object
        tool_result: The tool result object
    """
    logger = get_logger("chuk_tool_processor.tool_call")
    # Calculate duration safely, handling potential MagicMock objects
    try:
        dur = (tool_result.end_time - tool_result.start_time).total_seconds()
    except (TypeError, AttributeError):
        # Handle case where start_time or end_time might be a MagicMock in tests
        dur = 0.0

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
    
    # Add optional fields safely (handle MagicMock in tests)
    try:
        if hasattr(tool_result, "cached") and tool_result.cached:
            ctx["cached"] = True
    except (TypeError, ValueError):
        pass
    
    # Handle attempts field specifically    
    if hasattr(tool_result, "attempts"):
        try:
            # First, try direct attribute access and direct comparison
            # This works if attempts is a real int
            if tool_result.attempts > 0:
                ctx["attempts"] = tool_result.attempts
        except (TypeError, ValueError):
            # If that fails, try to convert to int
            try:
                attempts = int(tool_result.attempts)
                if attempts > 0:
                    ctx["attempts"] = attempts
            except (TypeError, ValueError):
                # If all else fails, just include the value
                ctx["attempts"] = tool_result.attempts
            
    try:
        if hasattr(tool_result, "stream_id") and tool_result.stream_id:
            ctx["stream_id"] = tool_result.stream_id
            ctx["is_partial"] = bool(getattr(tool_result, "is_partial", False))
    except (TypeError, ValueError):
        pass

    if tool_result.error:
        logger.error("Tool %s failed: %s", tool_call.tool, tool_result.error, extra={"context": ctx})
    else:
        logger.info("Tool %s succeeded in %.3fs", tool_call.tool, dur, extra={"context": ctx})
