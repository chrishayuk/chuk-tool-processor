# chuk_tool_processor/models/streaming_tool.py
"""
Base class for tools that support streaming results.

This enables tools to yield incremental results during their execution,
which is useful for long-running operations or real-time data processing.
"""
from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, TypeVar, Generic

from pydantic import BaseModel

from chuk_tool_processor.models.validated_tool import ValidatedTool

T = TypeVar('T')

class StreamingTool(ValidatedTool):
    """
    Base class for tools that support streaming responses.
    
    Subclass it like so:
    
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
    """
    
    # Override the execute method to handle streaming
    async def execute(self, **kwargs: Any) -> List[Any]:
        """
        Execute with arguments and return complete stream results.
        
        For streaming tools, this collects all streamed results into a list.
        """
        try:
            args = self.Arguments(**kwargs)
            
            # Collect all streamed results
            results = []
            async for chunk in self._stream_execute(**args.model_dump()):
                results.append(chunk)
                
            return results
        except Exception as e:
            raise e
            
    # Regular _execute is replaced with _stream_execute
    async def _execute(self, **kwargs: Any) -> List[Any]:
        """Default implementation collects stream results."""
        results = []
        async for chunk in self._stream_execute(**kwargs):
            results.append(chunk)
        return results
    
    @abstractmethod
    async def _stream_execute(self, **kwargs: Any) -> AsyncIterator[Any]:
        """
        Execute the tool and yield results incrementally.
        
        This must be implemented by streaming tool classes.
        """
        yield NotImplemented


# Decorator for adding streaming validation to a class
def with_streaming_validation(cls):
    """
    Decorator that wraps an existing async `stream_execute` method with validation.
    
    Similar to with_validation, but for streaming tools.
    """
    from chuk_tool_processor.utils.validation import validate_arguments
    
    original = cls.stream_execute
    if not inspect.iscoroutinefunction(original):
        raise TypeError(f"Tool {cls.__name__} must have an async stream_execute method")
        
    # Create a wrapper that validates arguments and iterates through results
    async def _async_stream_wrapper(self, **kwargs):
        tool_name = cls.__name__
        validated = validate_arguments(tool_name, original, kwargs)
        
        async for chunk in original(self, **validated):
            # Could validate each chunk here if needed
            yield chunk
            
    cls.stream_execute = _async_stream_wrapper
    return cls