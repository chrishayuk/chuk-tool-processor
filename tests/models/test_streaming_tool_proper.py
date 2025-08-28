# tests/models/test_streaming_tool_proper.py
"""Tests for streaming tool that match actual implementation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from chuk_tool_processor.models.streaming_tool import StreamingTool

pytestmark = pytest.mark.asyncio


class TestStreamingToolProper:
    """Test StreamingTool with proper ValidatedTool structure."""

    async def test_streaming_tool_basic(self):
        """Test basic streaming tool implementation."""

        class SimpleStreamingTool(StreamingTool):
            """A simple streaming tool."""

            class Arguments(BaseModel):
                text: str
                count: int = 3

            class Result(BaseModel):
                chunk: str
                index: int

            async def _stream_execute(self, text: str, count: int) -> AsyncIterator[Result]:
                """Stream results."""
                for i in range(count):
                    yield self.Result(chunk=f"{text}_{i}", index=i)
                    await asyncio.sleep(0.01)

        tool = SimpleStreamingTool()

        # Test streaming directly
        results = []
        async for result in tool.stream_execute(text="hello", count=2):
            results.append(result)

        assert len(results) == 2
        assert results[0].chunk == "hello_0"
        assert results[0].index == 0
        assert results[1].chunk == "hello_1"
        assert results[1].index == 1

    async def test_streaming_tool_execute_collects_results(self):
        """Test that execute() collects all streamed results."""

        class CollectingStreamingTool(StreamingTool):
            """Tool that collects results."""

            class Arguments(BaseModel):
                prefix: str

            async def _stream_execute(self, prefix: str) -> AsyncIterator[str]:
                """Stream string results."""
                for i in range(3):
                    yield f"{prefix}_{i}"

        tool = CollectingStreamingTool()

        # execute() should collect all results into a list
        results = await tool.execute(prefix="test")
        assert results == ["test_0", "test_1", "test_2"]

    async def test_streaming_tool_argument_validation(self):
        """Test that arguments are validated."""

        class ValidatedStreamingTool(StreamingTool):
            """Tool with validation."""

            class Arguments(BaseModel):
                value: int
                required_field: str

            async def _stream_execute(self, value: int, required_field: str) -> AsyncIterator[dict]:
                """Stream results."""
                yield {"value": value, "field": required_field}

        tool = ValidatedStreamingTool()

        # Should validate arguments
        with pytest.raises(ValidationError):
            # Missing required_field
            async for _ in tool.stream_execute(value=42):
                pass

        # Valid arguments should work
        results = []
        async for result in tool.stream_execute(value=42, required_field="test"):
            results.append(result)
        assert len(results) == 1
        assert results[0]["value"] == 42

    async def test_streaming_tool_empty_stream(self):
        """Test tool that yields no results."""

        class EmptyStreamingTool(StreamingTool):
            """Tool that yields nothing."""

            class Arguments(BaseModel):
                pass

            async def _stream_execute(self, **kwargs) -> AsyncIterator[str]:
                """Stream nothing."""
                return
                yield  # Never reached

        tool = EmptyStreamingTool()

        results = await tool.execute()
        assert results == []

    async def test_streaming_tool_class_vars(self):
        """Test that streaming tool has proper class variables."""

        class MyStreamingTool(StreamingTool):
            """Test tool."""

            class Arguments(BaseModel):
                pass

            async def _stream_execute(self, **kwargs) -> AsyncIterator[str]:
                yield "test"

        assert MyStreamingTool.supports_streaming is True
        assert hasattr(MyStreamingTool, "model_config")

    async def test_streaming_tool_with_complex_types(self):
        """Test streaming tool with complex argument and result types."""

        class ComplexStreamingTool(StreamingTool):
            """Complex streaming tool."""

            class Arguments(BaseModel):
                items: list[str]
                config: dict[str, int]
                optional: str = "default"

            class Result(BaseModel):
                processed: dict[str, Any]
                count: int

            async def _stream_execute(
                self, items: list[str], config: dict[str, int], optional: str
            ) -> AsyncIterator[Result]:
                """Stream complex results."""
                for i, item in enumerate(items):
                    yield self.Result(processed={"item": item, "config": config, "opt": optional}, count=i)

        tool = ComplexStreamingTool()

        results = []
        async for result in tool.stream_execute(items=["a", "b"], config={"key": 1}):
            results.append(result)

        assert len(results) == 2
        assert results[0].processed["item"] == "a"
        assert results[0].processed["opt"] == "default"
        assert results[1].count == 1

    async def test_streaming_tool_inheritance(self):
        """Test that StreamingTool properly inherits from ValidatedTool."""
        from chuk_tool_processor.models.validated_tool import ValidatedTool

        assert issubclass(StreamingTool, ValidatedTool)

        class CustomStreamingTool(StreamingTool):
            """Custom tool."""

            class Arguments(BaseModel):
                value: str

            async def _stream_execute(self, value: str) -> AsyncIterator[str]:
                yield value

        tool = CustomStreamingTool()
        assert isinstance(tool, ValidatedTool)
        assert isinstance(tool, StreamingTool)
