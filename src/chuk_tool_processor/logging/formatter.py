# chuk_tool_processor/logging/formatter.py
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any

__all__ = ["StructuredFormatter"]


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter that can serialise BaseModels, datetimes, sets, etc.
    """

    @staticmethod
    def _json_default(obj: Any):
        # pydantic models → dict
        try:
            from pydantic import BaseModel
            if isinstance(obj, BaseModel):
                return obj.model_dump()
        except ImportError:
            pass
        # datetimes → ISO
        from datetime import date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # sets → list
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        # fall back
        return str(obj)

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "pid": record.process,
            "thread": record.thread,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }
        if record.exc_info:
            data["traceback"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            data.update(record.extra)
        if hasattr(record, "context"):
            data["context"] = record.context
        return json.dumps(data, default=self._json_default)
