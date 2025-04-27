# chuk_tool_processor/logging/__init__.py
"""
Public façade for chuk_tool_processor structured logging.

Other modules can continue to import:

    from chuk_tool_processor.logging import get_logger, log_context_span, ...
"""
from __future__ import annotations
import logging, sys

from .formatter import StructuredFormatter
from .context   import get_logger, log_context, StructuredAdapter
from .helpers   import log_context_span, request_logging, log_tool_call, metrics

__all__ = [
    "get_logger",
    "log_context_span",
    "request_logging",
    "log_tool_call",
    "metrics",
]

# --------------------------------------------------------------------------- #
# root logger & handler wiring (done once at import time)
# --------------------------------------------------------------------------- #
root_logger = logging.getLogger("chuk_tool_processor")
root_logger.setLevel(logging.WARNING)           # ← quieter default

_handler = logging.StreamHandler(sys.stderr)
_handler.setLevel(logging.WARNING)              # match the logger
_handler.setFormatter(StructuredFormatter())
root_logger.addHandler(_handler)
