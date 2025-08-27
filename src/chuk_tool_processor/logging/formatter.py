# chuk_tool_processor/logging/formatter.py
"""
Structured JSON formatter for logging.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

__all__ = ["StructuredFormatter"]


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter that can serialize BaseModels, datetimes, sets, etc.

    This formatter converts log records to JSON format with proper handling
    of various Python types, ensuring logs are machine-readable and structured.
    """

    @staticmethod
    def _json_default(obj: Any) -> Any:
        """
        Custom JSON serializer for handling special types.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable representation
        """
        # Pydantic models → dict (use try/except to avoid ImportError)
        try:
            # Import pydantic inside the method to avoid global import errors
            # This allows the formatter to work even if pydantic is not installed
            from pydantic import BaseModel

            if isinstance(obj, BaseModel):
                return obj.model_dump()
        except (ImportError, AttributeError):
            # Either pydantic is not installed or the object doesn't have model_dump
            pass

        # Handle dates and datetimes
        try:
            from datetime import date

            if isinstance(obj, datetime | date):
                return obj.isoformat()
        except ImportError:
            pass

        # Sets → list
        if isinstance(obj, set | frozenset):
            return list(obj)

        # Fall back to string representation
        return str(obj)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON string representation
        """
        # Build base data structure
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "pid": record.process,
            "thread": record.thread,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception traceback if present
        if record.exc_info:
            data["traceback"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra"):
            data.update(record.extra)

        # Add context if present
        if hasattr(record, "context"):
            data["context"] = record.context

        # Serialize to JSON
        return json.dumps(data, default=self._json_default)
