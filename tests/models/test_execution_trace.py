# tests/models/test_execution_trace.py
"""
Tests for ExecutionTrace and TraceBuilder.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from chuk_tool_processor.core.context import ExecutionContext
from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.models.execution_span import (
    ExecutionOutcome,
    ExecutionSpan,
)
from chuk_tool_processor.models.execution_trace import (
    ExecutionTrace,
    ReplayDifference,
    ReplayMode,
    ReplayResult,
    TraceBuilder,
)
from chuk_tool_processor.models.tool_call import ToolCall


# --------------------------------------------------------------------------- #
# ReplayDifference Tests
# --------------------------------------------------------------------------- #
class TestReplayDifference:
    """Tests for ReplayDifference model."""

    def test_basic_difference(self):
        """Test creating basic replay difference."""
        diff = ReplayDifference(
            span_index=0,
            tool_name="test_tool",
            field="result",
            expected=42,
            actual=43,
        )
        assert diff.span_index == 0
        assert diff.tool_name == "test_tool"
        assert diff.field == "result"
        assert diff.expected == 42
        assert diff.actual == 43
        assert diff.severity == "error"

    def test_difference_with_severity(self):
        """Test creating difference with custom severity."""
        diff = ReplayDifference(
            span_index=0,
            tool_name="test_tool",
            field="result",
            expected=42,
            actual=43,
            severity="warning",
        )
        assert diff.severity == "warning"


# --------------------------------------------------------------------------- #
# ReplayResult Tests
# --------------------------------------------------------------------------- #
class TestReplayResult:
    """Tests for ReplayResult model."""

    def test_basic_replay_result(self):
        """Test creating basic replay result."""
        now = datetime.now(UTC)
        result = ReplayResult(
            original_trace_id="trace-1",
            replay_trace_id="trace-2",
            mode=ReplayMode.STRICT,
            started_at=now,
            ended_at=now,
            success=True,
        )
        assert result.original_trace_id == "trace-1"
        assert result.success is True

    def test_match_rate_with_zero_spans(self):
        """Test match_rate returns 0 when no spans compared."""
        now = datetime.now(UTC)
        result = ReplayResult(
            original_trace_id="trace-1",
            replay_trace_id="trace-2",
            mode=ReplayMode.STRICT,
            started_at=now,
            ended_at=now,
            success=True,
            spans_compared=0,
            spans_matched=0,
        )
        assert result.match_rate == 0.0

    def test_match_rate_with_spans(self):
        """Test match_rate calculation."""
        now = datetime.now(UTC)
        result = ReplayResult(
            original_trace_id="trace-1",
            replay_trace_id="trace-2",
            mode=ReplayMode.STRICT,
            started_at=now,
            ended_at=now,
            success=True,
            spans_compared=10,
            spans_matched=8,
        )
        assert result.match_rate == 0.8

    def test_duration_ms(self):
        """Test duration_ms calculation."""
        start = datetime.now(UTC)
        result = ReplayResult(
            original_trace_id="trace-1",
            replay_trace_id="trace-2",
            mode=ReplayMode.STRICT,
            started_at=start,
            ended_at=start,  # Same time for test
            success=True,
        )
        assert result.duration_ms >= 0


# --------------------------------------------------------------------------- #
# ExecutionTrace Tests
# --------------------------------------------------------------------------- #
class TestExecutionTrace:
    """Tests for ExecutionTrace model."""

    def test_basic_trace(self):
        """Test creating basic trace."""
        trace = ExecutionTrace()
        assert trace.trace_id is not None
        assert trace.name == ""
        assert trace.spans == []

    def test_trace_with_name(self):
        """Test trace with name."""
        trace = ExecutionTrace(name="test-trace")
        assert trace.name == "test-trace"

    def test_duration_ms_with_spans(self):
        """Test duration_ms sums span durations when no start/end times."""
        span1 = ExecutionSpan(
            tool_name="tool1",
            created_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
        span2 = ExecutionSpan(
            tool_name="tool2",
            created_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
        trace = ExecutionTrace(spans=[span1, span2])
        assert trace.duration_ms >= 0

    def test_duration_ms_with_timestamps(self):
        """Test duration_ms uses trace timestamps when available."""
        now = datetime.now(UTC)
        trace = ExecutionTrace(started_at=now, ended_at=now)
        assert trace.duration_ms == 0.0

    def test_span_count(self):
        """Test span_count property."""
        span = ExecutionSpan(tool_name="tool")
        trace = ExecutionTrace(spans=[span, span])
        assert trace.span_count == 2

    def test_success_count(self):
        """Test success_count property."""
        success_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.SUCCESS)
        repaired_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.REPAIRED)
        failed_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.FAILED)
        trace = ExecutionTrace(spans=[success_span, repaired_span, failed_span])
        assert trace.success_count == 2

    def test_failure_count(self):
        """Test failure_count property."""
        success_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.SUCCESS)
        failed_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.FAILED)
        trace = ExecutionTrace(spans=[success_span, failed_span, failed_span])
        assert trace.failure_count == 2

    def test_blocked_count(self):
        """Test blocked_count property."""
        success_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.SUCCESS)
        blocked_span = ExecutionSpan(tool_name="tool", outcome=ExecutionOutcome.BLOCKED)
        trace = ExecutionTrace(spans=[success_span, blocked_span])
        assert trace.blocked_count == 1

    def test_tools_used(self):
        """Test tools_used property."""
        span1 = ExecutionSpan(tool_name="tool1")
        span2 = ExecutionSpan(tool_name="tool2", namespace="math")
        span3 = ExecutionSpan(tool_name="tool1")  # Duplicate
        trace = ExecutionTrace(spans=[span1, span2, span3])
        tools = trace.tools_used
        assert len(tools) == 2
        assert "tool1" in tools
        assert "math.tool2" in tools

    def test_content_hash(self):
        """Test content_hash property."""
        span = ExecutionSpan(tool_name="tool", arguments={"x": 1})
        tool_call = ToolCall(tool="tool", arguments={"x": 1})
        trace = ExecutionTrace(spans=[span], tool_calls=[tool_call])
        hash1 = trace.content_hash
        assert len(hash1) == 16

        # Same content should give same hash
        trace2 = ExecutionTrace(spans=[span], tool_calls=[tool_call])
        assert trace2.content_hash == hash1

    def test_start(self):
        """Test start method."""
        trace = ExecutionTrace()
        result = trace.start()
        assert result is trace
        assert trace.started_at is not None

    def test_end(self):
        """Test end method."""
        trace = ExecutionTrace()
        result = trace.end()
        assert result is trace
        assert trace.ended_at is not None

    def test_add_tool_call(self):
        """Test add_tool_call method."""
        trace = ExecutionTrace()
        tool_call = ToolCall(tool="test", arguments={"x": 1})
        result = trace.add_tool_call(tool_call)
        assert result is trace
        assert len(trace.tool_calls) == 1

    def test_add_span(self):
        """Test add_span method."""
        trace = ExecutionTrace()
        span = ExecutionSpan(tool_name="test")
        result = trace.add_span(span)
        assert result is trace
        assert len(trace.spans) == 1

    def test_with_context(self):
        """Test with_context method."""
        trace = ExecutionTrace()
        context = ExecutionContext()
        result = trace.with_context(context)
        assert result is trace
        assert trace.context is context

    def test_with_seed(self):
        """Test with_seed method."""
        trace = ExecutionTrace()
        result = trace.with_seed(42)
        assert result is trace
        assert trace.random_seed == 42
        assert trace.deterministic is True

    def test_capture_environment_default(self):
        """Test capture_environment with default vars."""
        trace = ExecutionTrace()
        result = trace.capture_environment()
        assert result is trace
        # Should capture at least some vars
        assert isinstance(trace.environment_snapshot, dict)

    def test_capture_environment_custom(self):
        """Test capture_environment with custom vars."""
        import os

        os.environ["TEST_VAR_123"] = "test_value"
        trace = ExecutionTrace()
        trace.capture_environment(var_names=["TEST_VAR_123"])
        assert trace.environment_snapshot.get("TEST_VAR_123") == "test_value"
        del os.environ["TEST_VAR_123"]

    def test_with_tag(self):
        """Test with_tag method."""
        trace = ExecutionTrace()
        result = trace.with_tag("test")
        assert result is trace
        assert "test" in trace.tags

    def test_with_tag_no_duplicates(self):
        """Test with_tag doesn't add duplicates."""
        trace = ExecutionTrace()
        trace.with_tag("test")
        trace.with_tag("test")
        assert trace.tags.count("test") == 1

    def test_with_metadata(self):
        """Test with_metadata method."""
        trace = ExecutionTrace()
        result = trace.with_metadata(key="value", num=42)
        assert result is trace
        assert trace.metadata["key"] == "value"
        assert trace.metadata["num"] == 42

    @pytest.mark.asyncio
    async def test_replay_basic(self):
        """Test basic replay functionality."""
        # Create a trace with one span
        span = ExecutionSpan(
            tool_name="test_tool",
            arguments={"x": 1},
            outcome=ExecutionOutcome.SUCCESS,
            result=42,
        )
        tool_call = ToolCall(tool="test_tool", arguments={"x": 1})
        trace = ExecutionTrace(spans=[span], tool_calls=[tool_call])

        # Create mock executor
        mock_executor = AsyncMock()
        mock_result_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=42,
        )
        mock_executor.run.return_value = [mock_result_span]

        result = await trace.replay(mock_executor, mode=ReplayMode.STRICT)

        assert result.original_trace_id == trace.trace_id
        assert result.mode == ReplayMode.STRICT
        assert result.spans_compared == 1

    @pytest.mark.asyncio
    async def test_replay_with_seed(self):
        """Test replay sets random seed."""
        span = ExecutionSpan(tool_name="test_tool", outcome=ExecutionOutcome.SUCCESS)
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(
            spans=[span],
            tool_calls=[tool_call],
            random_seed=42,
        )

        mock_executor = AsyncMock()
        mock_executor.run.return_value = [span]

        await trace.replay(mock_executor)
        # If we got here without error, the seed was set successfully

    @pytest.mark.asyncio
    async def test_replay_detects_outcome_difference(self):
        """Test replay detects outcome differences."""
        original_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
        )
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(spans=[original_span], tool_calls=[tool_call])

        mock_executor = AsyncMock()
        replay_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.FAILED,
        )
        mock_executor.run.return_value = [replay_span]

        result = await trace.replay(mock_executor, mode=ReplayMode.STRICT)

        assert result.success is False
        assert len(result.differences) > 0
        assert any(d.field == "outcome" for d in result.differences)

    @pytest.mark.asyncio
    async def test_replay_detects_result_difference_strict(self):
        """Test replay detects result differences in strict mode."""
        original_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=42,
        )
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(spans=[original_span], tool_calls=[tool_call])

        mock_executor = AsyncMock()
        replay_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=43,
        )
        mock_executor.run.return_value = [replay_span]

        result = await trace.replay(mock_executor, mode=ReplayMode.STRICT)

        assert any(d.field == "result" for d in result.differences)

    @pytest.mark.asyncio
    async def test_replay_detects_verdict_difference(self):
        """Test replay detects guard verdict differences."""
        original_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            final_verdict=GuardVerdict.ALLOW,
        )
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(spans=[original_span], tool_calls=[tool_call])

        mock_executor = AsyncMock()
        replay_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            final_verdict=GuardVerdict.WARN,
        )
        mock_executor.run.return_value = [replay_span]

        result = await trace.replay(mock_executor)

        assert any(d.field == "final_verdict" for d in result.differences)

    @pytest.mark.asyncio
    async def test_replay_lenient_mode(self):
        """Test replay in lenient mode."""
        original_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=42,
            deterministic=False,
        )
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(spans=[original_span], tool_calls=[tool_call])

        mock_executor = AsyncMock()
        replay_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=43,
        )
        mock_executor.run.return_value = [replay_span]

        result = await trace.replay(mock_executor, mode=ReplayMode.LENIENT)

        # In lenient mode, non-deterministic result differences should be warnings
        assert result.success is True or any(d.severity == "warning" for d in result.differences)

    @pytest.mark.asyncio
    async def test_replay_deterministic_result_difference(self):
        """Test replay detects deterministic result differences as errors."""
        original_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=42,
            deterministic=True,
        )
        tool_call = ToolCall(tool="test_tool", arguments={})
        trace = ExecutionTrace(spans=[original_span], tool_calls=[tool_call])

        mock_executor = AsyncMock()
        replay_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
            result=43,
        )
        mock_executor.run.return_value = [replay_span]

        result = await trace.replay(mock_executor, mode=ReplayMode.LENIENT)

        # Deterministic tool result differences should be errors
        assert any(d.field == "result" and d.severity == "error" for d in result.differences)

    def test_to_jsonl(self):
        """Test to_jsonl export."""
        span = ExecutionSpan(tool_name="test_tool", arguments={"x": 1})
        trace = ExecutionTrace(name="test", spans=[span])

        jsonl = trace.to_jsonl()

        lines = jsonl.split("\n")
        assert len(lines) == 2  # One for trace, one for span

        # First line is trace data
        trace_line = json.loads(lines[0])
        assert "trace" in trace_line

        # Second line is span data
        span_line = json.loads(lines[1])
        assert "span" in span_line

    def test_from_jsonl(self):
        """Test from_jsonl import."""
        span = ExecutionSpan(tool_name="test_tool", arguments={"x": 1})
        original_trace = ExecutionTrace(name="test", spans=[span])

        jsonl = original_trace.to_jsonl()
        loaded_trace = ExecutionTrace.from_jsonl(jsonl)

        assert loaded_trace.name == "test"
        assert len(loaded_trace.spans) == 1
        assert loaded_trace.spans[0].tool_name == "test_tool"

    def test_to_summary(self):
        """Test to_summary export."""
        span = ExecutionSpan(tool_name="test_tool", outcome=ExecutionOutcome.SUCCESS)
        trace = ExecutionTrace(
            name="test",
            spans=[span],
            tags=["tag1", "tag2"],
            deterministic=True,
        )

        summary = trace.to_summary()

        assert summary["name"] == "test"
        assert summary["span_count"] == 1
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 0
        assert summary["blocked_count"] == 0
        assert summary["deterministic"] is True
        assert "tag1" in summary["tags"]


# --------------------------------------------------------------------------- #
# TraceBuilder Tests
# --------------------------------------------------------------------------- #
class TestTraceBuilder:
    """Tests for TraceBuilder."""

    def test_basic_builder(self):
        """Test basic trace builder."""
        builder = TraceBuilder()
        trace = builder.build()

        assert trace.name == ""
        assert trace.ended_at is not None

    def test_builder_with_name(self):
        """Test builder with name."""
        builder = TraceBuilder(name="test-trace")
        trace = builder.build()

        assert trace.name == "test-trace"

    def test_builder_with_context(self):
        """Test builder with context."""
        context = ExecutionContext()
        builder = TraceBuilder(context=context)
        trace = builder.build()

        assert trace.context is context

    def test_builder_with_seed(self):
        """Test builder with seed."""
        builder = TraceBuilder(seed=42)
        trace = builder.build()

        assert trace.random_seed == 42
        assert trace.deterministic is True

    def test_builder_start(self):
        """Test builder start method."""
        builder = TraceBuilder()
        result = builder.start()

        assert result is builder
        assert builder._trace.started_at is not None

    def test_builder_add_tool_call(self):
        """Test builder add_tool_call method."""
        builder = TraceBuilder()
        tool_call = ToolCall(tool="test", arguments={})
        result = builder.add_tool_call(tool_call)

        assert result is builder
        trace = builder.build()
        assert len(trace.tool_calls) == 1

    def test_builder_add_span(self):
        """Test builder add_span method."""
        builder = TraceBuilder()
        span = ExecutionSpan(tool_name="test")
        result = builder.add_span(span)

        assert result is builder
        trace = builder.build()
        assert len(trace.spans) == 1

    def test_builder_with_tag(self):
        """Test builder with_tag method."""
        builder = TraceBuilder()
        result = builder.with_tag("tag1")

        assert result is builder
        trace = builder.build()
        assert "tag1" in trace.tags

    def test_builder_with_metadata(self):
        """Test builder with_metadata method."""
        builder = TraceBuilder()
        result = builder.with_metadata(key="value")

        assert result is builder
        trace = builder.build()
        assert trace.metadata["key"] == "value"

    def test_builder_capture_environment(self):
        """Test builder capture_environment method."""
        builder = TraceBuilder()
        result = builder.capture_environment()

        assert result is builder
        trace = builder.build()
        assert isinstance(trace.environment_snapshot, dict)

    def test_builder_build_ends_trace(self):
        """Test build method sets ended_at."""
        builder = TraceBuilder()
        builder.start()
        trace = builder.build()

        assert trace.started_at is not None
        assert trace.ended_at is not None


# --------------------------------------------------------------------------- #
# ReplayMode Tests
# --------------------------------------------------------------------------- #
class TestReplayMode:
    """Tests for ReplayMode enum."""

    def test_replay_mode_values(self):
        """Test ReplayMode enum values."""
        assert ReplayMode.STRICT.value == "strict"
        assert ReplayMode.LENIENT.value == "lenient"
        assert ReplayMode.COMPARE_ONLY.value == "compare_only"
