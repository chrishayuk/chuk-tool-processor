#!/usr/bin/env python
# chuk_tool_processor/models/streaming_tool.py
"""
Base class for tools that support streaming results.

This enables tools to yield incremental results during their execution,
which is useful for long-running operations or real-time data processing.
"""
from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any, AsyncIterator, List, TypeVar, Generic, ClassVar, Optional, Dict

from pydantic import BaseModel, ConfigDict

from chuk_tool_processor.models.validated_tool import ValidatedTool

T = TypeVar('T')

class StreamingTool(ValidatedTool):
    """
    Base class for tools that support streaming responses.
    
    Subclasses must implement _stream_execute which yields results one by one.
    The executor should use stream_execute to access streaming results directly.
    
    Example:
    ```python
    class Counter(StreamingTool):
        class Arguments(BaseModel):
            count: int = 10
            delay: float = 0.5
            
        class Result(BaseModel):
            value: int
            
        async def _stream_execute(self, count: int, delay: float) -> AsyncIterator[Result]:
            for i in range(count):
                await asyncio.sleep(delay)
                yield self.Result(value=i)
    ```
    
    Streaming usage:
    ```python
    counter_tool = Counter()
    async for result in counter_tool.stream_execute(count=5, delay=0.1):
        print(f"Count: {result.value}")
    ```
    """
    # Mark this as a ClassVar so Pydantic doesn't treat it as a field
    supports_streaming: ClassVar[bool] = True
    
    # Use ConfigDict to configure model behavior
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    async def stream_execute(self, **kwargs: Any) -> AsyncIterator[Any]:
        """
        Execute the tool and stream results incrementally.
        
        This public method validates arguments and then delegates to _stream_execute.
        It should be used directly by the executor to support true streaming.
        
        Args:
            **kwargs: Keyword arguments for the tool
            
        Yields:
            Results as they are generated by the tool
        """
        # Validate arguments using the Arguments model
        args = self.Arguments(**kwargs)
        
        # Stream results directly from _stream_execute
        async for result in self._stream_execute(**args.model_dump()):
            yield result
    
    async def execute(self, **kwargs: Any) -> Any:
        """
        Execute the tool and collect all results.
        
        For streaming tools, this collects all results from stream_execute
        into a list for compatibility with the regular execution model.
        
        Args:
            **kwargs: Keyword arguments for the tool
            
        Returns:
            List of all streamed results
        """
        # Collect all streamed results into a list
        results = []
        async for chunk in self.stream_execute(**kwargs):
            results.append(chunk)
            
        return results
    
    @abstractmethod
    async def _stream_execute(self, **kwargs: Any) -> AsyncIterator[Any]:
        """
        Execute the tool and yield results incrementally.
        
        This must be implemented by streaming tool subclasses.
        
        Args:
            **kwargs: Tool-specific arguments
            
        Yields:
            Results as they are generated
        """
        yield NotImplemented