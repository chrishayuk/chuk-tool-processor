# chuk_tool_processor/logging/context.py
from __future__ import annotations
import logging
import uuid
from typing import Any, Dict, Optional

__all__ = ["log_context", "StructuredAdapter", "get_logger"]


class LogContext:
    """Thread-local dict for request / span ids."""

    def __init__(self):
        self.context: Dict[str, Any] = {}
        self.request_id: str | None = None

    # simple helpers ----------------------------------------------------
    def update(self, kv: Dict[str, Any]):      self.context.update(kv)
    def clear(self):                           self.context.clear()
    def get_copy(self) -> Dict[str, Any]:      return self.context.copy()

    # convenience -------------------------------------------------------
    def start_request(self, request_id: str | None = None) -> str:
        self.request_id = request_id or str(uuid.uuid4())
        self.context["request_id"] = self.request_id
        return self.request_id

    def end_request(self): self.clear()


log_context = LogContext()


class StructuredAdapter(logging.LoggerAdapter):
    """Inject `log_context.context` into every log record."""

    def process(self, msg, kwargs):
        kwargs = kwargs or {}
        extra = kwargs.get("extra", {})
        if log_context.context:
            extra.setdefault("context", {}).update(log_context.get_copy())
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> StructuredAdapter:
    return StructuredAdapter(logging.getLogger(name), {})
