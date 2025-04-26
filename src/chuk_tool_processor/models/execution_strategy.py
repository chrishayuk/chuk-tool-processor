# chuk_tool_processor/models/execution_strategy.py
from abc import ABC, abstractmethod
from typing import List, Optional

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult


class ExecutionStrategy(ABC):
    """
    Strategy interface for executing ToolCall objects.
    """
    @abstractmethod
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        pass