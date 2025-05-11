# chuk_tool_processor/parsers/base.py
"""Async-native parser-plugin base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from chuk_tool_processor.models.tool_call import ToolCall

__all__ = ["ParserPlugin"]


class ParserPlugin(ABC):
    """
    Every parser plugin **must** implement the async ``try_parse`` coroutine.

    The processor awaits it and expects *a list* of :class:`ToolCall`
    objects. If the plugin doesn’t recognise the input it should return an
    empty list.
    """

    @abstractmethod
    async def try_parse(self, raw: str | object) -> List[ToolCall]:  # noqa: D401
        """Attempt to parse *raw* into one or more :class:`ToolCall` objects."""
        ...
