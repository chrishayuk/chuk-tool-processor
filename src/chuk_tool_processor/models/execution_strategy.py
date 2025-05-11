# chuk_tool_processor/models/execution_strategy.py
"""
Abstract base class for tool execution strategies.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

class ExecutionStrategy(ABC):
    """
    Strategy interface for executing ToolCall objects.
    
    All execution strategies must implement at least the run method,
    and optionally stream_run for streaming support.
    """
    @abstractmethod
    async def run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> List[ToolResult]:
        """
        Execute a list of tool calls and return their results.
        
        Args:
            calls: List of ToolCall objects to execute
            timeout: Optional timeout in seconds for each call
            
        Returns:
            List of ToolResult objects in the same order as the calls
        """
        pass
    
    async def stream_run(
        self,
        calls: List[ToolCall],
        timeout: Optional[float] = None
    ) -> AsyncIterator[ToolResult]:
        """
        Execute tool calls and yield results as they become available.
        
        Default implementation executes all calls with run() and yields the results.
        Subclasses can override for true streaming behavior.
        
        Args:
            calls: List of ToolCall objects to execute
            timeout: Optional timeout in seconds for each call
            
        Yields:
            ToolResult objects as they become available
        """
        results = await self.run(calls, timeout=timeout)
        for result in results:
            yield result
    
    @property
    def supports_streaming(self) -> bool:
        """
        Check if this strategy supports true streaming.
        
        Default implementation returns False. Streaming-capable strategies
        should override this to return True.
        """
        return False