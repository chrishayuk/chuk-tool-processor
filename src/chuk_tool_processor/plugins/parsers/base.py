# chuk_tool_processor/parsers/base.py
from abc import ABC, abstractmethod
from typing import List
from chuk_tool_processor.models.tool_call import ToolCall


class ParserPlugin(ABC):
    """
    Minimal interface every parser plug-in must implement.

    The processor will feed the *raw text* (or dict) it receives from upstream
    into `try_parse`.  If the plugin recognises the format it should return a
    list of ToolCall objects; otherwise return an empty list.
    """

    @abstractmethod
    def try_parse(self, raw: str) -> List[ToolCall]:
        ...
