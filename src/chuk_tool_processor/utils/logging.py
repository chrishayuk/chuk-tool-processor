# chuk_tool_processor/logging.py
import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

# Configure the root logger
root_logger = logging.getLogger("chuk_tool_processor")
root_logger.setLevel(logging.INFO)

# Create a handler for stderr
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)

# Create a formatter for structured logging
class StructuredFormatter(logging.Formatter):
    """
    Custom formatter for structured JSON logging.
    """
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        """
        # Basic log data
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
                              .isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "pid": record.process,
            "thread": record.thread,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }
        
        # Add traceback if present
        if record.exc_info:
            log_data["traceback"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add structured logging context if present
        if hasattr(record, "context"):
            log_data["context"] = record.context
        
        return json.dumps(log_data)


# Configure the formatter
formatter = StructuredFormatter()
handler.setFormatter(formatter)

# Add the handler to the root logger
root_logger.addHandler(handler)

# Thread-local context storage
class LogContext:
    """
    Thread-local storage for log context.
    """
    def __init__(self):
        self.context = {}
        self.request_id = None
    
    def set(self, key: str, value: Any) -> None:
        self.context[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)
    
    def update(self, values: Dict[str, Any]) -> None:
        self.context.update(values)
    
    def clear(self) -> None:
        self.context = {}
        self.request_id = None
    
    def start_request(self, request_id: Optional[str] = None) -> str:
        self.request_id = request_id or str(uuid.uuid4())
        self.context["request_id"] = self.request_id
        return self.request_id
    
    def end_request(self) -> None:
        self.clear()


# Create global log context
log_context = LogContext()


class StructuredAdapter(logging.LoggerAdapter):
    """
    Adapter to add structured context to log messages.
    """
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        kwargs = kwargs.copy() if kwargs else {}
        extra = kwargs.get("extra", {})
        if log_context.context:
            context_copy = log_context.context.copy()
            if "context" in extra:
                extra["context"].update(context_copy)
            else:
                extra["context"] = context_copy
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> StructuredAdapter:
    logger = logging.getLogger(name)
    return StructuredAdapter(logger, {})


@contextmanager
def log_context_span(
    operation: str,
    extra: Optional[Dict[str, Any]] = None,
    log_duration: bool = True,
    level: int = logging.INFO
):
    logger = get_logger(f"chuk_tool_processor.span.{operation}")
    start_time = time.time()
    span_id = str(uuid.uuid4())
    span_context = {
        "span_id": span_id,
        "operation": operation,
        "start_time": datetime.fromtimestamp(start_time, timezone.utc)
                            .isoformat().replace("+00:00", "Z"),
    }
    if extra:
        span_context.update(extra)
    previous_context = log_context.context.copy() if log_context.context else {}
    log_context.update(span_context)
    logger.log(level, f"Starting {operation}")
    try:
        yield
        if log_duration:
            duration = time.time() - start_time
            logger.log(level, f"Completed {operation}", extra={"context": {"duration": duration}})
        else:
            logger.log(level, f"Completed {operation}")
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            f"Error in {operation}: {str(e)}",
            extra={"context": {"duration": duration, "error": str(e)}}
        )
        raise
    finally:
        log_context.clear()
        if previous_context:
            log_context.update(previous_context)


@contextmanager
def request_logging(request_id: Optional[str] = None):
    logger = get_logger("chuk_tool_processor.request")
    request_id = log_context.start_request(request_id)
    start_time = time.time()
    logger.info(f"Starting request {request_id}")
    try:
        yield request_id
        duration = time.time() - start_time
        logger.info(
            f"Completed request {request_id}",
            extra={"context": {"duration": duration}}
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            f"Error in request {request_id}: {str(e)}",
            extra={"context": {"duration": duration, "error": str(e)}}
        )
        raise
    finally:
        log_context.end_request()


def log_tool_call(tool_call, tool_result):
    logger = get_logger("chuk_tool_processor.tool_call")
    duration = (tool_result.end_time - tool_result.start_time).total_seconds()
    context = {
        "tool": tool_call.tool,
        "arguments": tool_call.arguments,
        "result": tool_result.result,
        "error": tool_result.error,
        "duration": duration,
        "machine": tool_result.machine,
        "pid": tool_result.pid,
    }
    if hasattr(tool_result, "cached") and tool_result.cached:
        context["cached"] = True
    if hasattr(tool_result, "attempts") and tool_result.attempts:
        context["attempts"] = tool_result.attempts
    if tool_result.error:
        logger.error(
            f"Tool {tool_call.tool} failed: {tool_result.error}",
            extra={"context": context}
        )
    else:
        logger.info(
            f"Tool {tool_call.tool} succeeded in {duration:.3f}s",
            extra={"context": context}
        )


class MetricsLogger:
    def __init__(self):
        self.logger = get_logger("chuk_tool_processor.metrics")
    def log_tool_execution(
        self,
        tool: str,
        success: bool,
        duration: float,
        error: Optional[str] = None,
        cached: bool = False,
        attempts: int = 1
    ):
        self.logger.info(
            f"Tool execution metric: {tool}",
            extra={
                "context": {
                    "metric_type": "tool_execution",
                    "tool": tool,
                    "success": success,
                    "duration": duration,
                    "error": error,
                    "cached": cached,
                    "attempts": attempts,
                }
            }
        )
    def log_parser_metric(
        self,
        parser: str,
        success: bool,
        duration: float,
        num_calls: int
    ):
        self.logger.info(
            f"Parser metric: {parser}",
            extra={
                "context": {
                    "metric_type": "parser",
                    "parser": parser,
                    "success": success,
                    "duration": duration,
                    "num_calls": num_calls,
                }
            }
        )

metrics = MetricsLogger()
