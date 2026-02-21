# tests/observability/test_trace_sink_coverage.py
"""Comprehensive tests for trace_sink.py targeting >90% coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from chuk_tool_processor.models.execution_span import ExecutionOutcome, ExecutionSpan
from chuk_tool_processor.models.execution_trace import ExecutionTrace
from chuk_tool_processor.observability.trace_sink import (
    CompositeTraceSink,
    FileTraceSink,
    InMemoryTraceSink,
    NoOpTraceSink,
    SpanQuery,
    TraceQuery,
    TraceSinkStats,
    TraceSinkType,
    get_trace_sink,
    init_trace_sink,
    set_trace_sink,
)

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_span(
    tool_name: str = "calculator",
    namespace: str = "default",
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCESS,
    trace_id: str = "trace-1",
    request_id: str | None = None,
    created_at: datetime | None = None,
    ended_at: datetime | None = None,
    blocked: bool = False,
) -> ExecutionSpan:
    """Create a minimal ExecutionSpan for testing."""
    now = created_at or datetime.now(UTC)
    end = ended_at or (now + timedelta(milliseconds=50))
    if blocked:
        outcome = ExecutionOutcome.BLOCKED
    return ExecutionSpan(
        tool_name=tool_name,
        namespace=namespace,
        outcome=outcome,
        trace_id=trace_id,
        request_id=request_id,
        created_at=now,
        ended_at=end,
        arguments={"a": 1},
    )


def _make_trace(
    trace_id: str = "trace-1",
    name: str = "test-trace",
    tags: list[str] | None = None,
    deterministic: bool = False,
    created_at: datetime | None = None,
) -> ExecutionTrace:
    """Create a minimal ExecutionTrace for testing."""
    return ExecutionTrace(
        trace_id=trace_id,
        name=name,
        tags=tags or [],
        deterministic=deterministic,
        created_at=created_at or datetime.now(UTC),
    )


async def _collect_spans(aiter) -> list[ExecutionSpan]:
    """Collect all spans from an async iterator."""
    result = []
    async for item in aiter:
        result.append(item)
    return result


async def _collect_traces(aiter) -> list[ExecutionTrace]:
    """Collect all traces from an async iterator."""
    result = []
    async for item in aiter:
        result.append(item)
    return result


# ------------------------------------------------------------------ #
# Pydantic model tests
# ------------------------------------------------------------------ #


class TestModels:
    """Tests for SpanQuery, TraceQuery, TraceSinkStats models."""

    def test_span_query_defaults(self):
        q = SpanQuery()
        assert q.tool is None
        assert q.namespace is None
        assert q.outcome is None
        assert q.trace_id is None
        assert q.request_id is None
        assert q.since is None
        assert q.until is None
        assert q.min_duration_ms is None
        assert q.max_duration_ms is None
        assert q.blocked_only is False
        assert q.failed_only is False
        assert q.limit == 100
        assert q.offset == 0

    def test_span_query_with_all_fields(self):
        now = datetime.now(UTC)
        q = SpanQuery(
            tool="calc*",
            namespace="math",
            outcome=ExecutionOutcome.SUCCESS,
            trace_id="t1",
            request_id="r1",
            since=now,
            until=now,
            min_duration_ms=10.0,
            max_duration_ms=100.0,
            blocked_only=True,
            failed_only=True,
            limit=50,
            offset=5,
        )
        assert q.tool == "calc*"
        assert q.namespace == "math"
        assert q.limit == 50

    def test_trace_query_defaults(self):
        q = TraceQuery()
        assert q.trace_id is None
        assert q.name is None
        assert q.tags == []
        assert q.since is None
        assert q.until is None
        assert q.deterministic_only is False
        assert q.limit == 100
        assert q.offset == 0

    def test_trace_query_with_all_fields(self):
        now = datetime.now(UTC)
        q = TraceQuery(
            trace_id="t1",
            name="my-trace",
            tags=["tag1", "tag2"],
            since=now,
            until=now,
            deterministic_only=True,
            limit=10,
            offset=2,
        )
        assert q.trace_id == "t1"
        assert q.tags == ["tag1", "tag2"]

    def test_trace_sink_stats_defaults(self):
        s = TraceSinkStats()
        assert s.span_count == 0
        assert s.trace_count == 0
        assert s.oldest_span is None
        assert s.newest_span is None
        assert s.tools_seen == []
        assert s.outcome_counts == {}

    def test_trace_sink_stats_populated(self):
        now = datetime.now(UTC)
        s = TraceSinkStats(
            span_count=10,
            trace_count=2,
            oldest_span=now,
            newest_span=now,
            tools_seen=["a", "b"],
            outcome_counts={"success": 8, "failed": 2},
        )
        assert s.span_count == 10
        assert s.tools_seen == ["a", "b"]


# ------------------------------------------------------------------ #
# TraceSinkType enum
# ------------------------------------------------------------------ #


class TestTraceSinkType:
    def test_enum_values(self):
        assert TraceSinkType.MEMORY == "memory"
        assert TraceSinkType.FILE == "file"
        assert TraceSinkType.NOOP == "noop"

    def test_enum_from_string(self):
        assert TraceSinkType("memory") == TraceSinkType.MEMORY
        assert TraceSinkType("file") == TraceSinkType.FILE
        assert TraceSinkType("noop") == TraceSinkType.NOOP


# ------------------------------------------------------------------ #
# InMemoryTraceSink
# ------------------------------------------------------------------ #


class TestInMemoryTraceSink:
    @pytest.mark.asyncio
    async def test_record_and_query_span(self):
        sink = InMemoryTraceSink()
        span = _make_span()
        await sink.record_span(span)

        results = await _collect_spans(sink.query_spans())
        assert len(results) == 1
        assert results[0].tool_name == "calculator"

    @pytest.mark.asyncio
    async def test_record_and_query_trace(self):
        sink = InMemoryTraceSink()
        trace = _make_trace()
        await sink.record_trace(trace)

        results = await _collect_traces(sink.query_traces())
        assert len(results) == 1
        assert results[0].name == "test-trace"

    @pytest.mark.asyncio
    async def test_fifo_eviction_spans(self):
        sink = InMemoryTraceSink(max_spans=3)
        for i in range(5):
            await sink.record_span(_make_span(tool_name=f"tool-{i}"))

        all_spans = sink.get_all_spans()
        assert len(all_spans) == 3
        # Oldest (tool-0, tool-1) should be evicted
        assert all_spans[0].tool_name == "tool-2"
        assert all_spans[1].tool_name == "tool-3"
        assert all_spans[2].tool_name == "tool-4"

    @pytest.mark.asyncio
    async def test_fifo_eviction_traces(self):
        sink = InMemoryTraceSink(max_traces=2)
        for i in range(4):
            await sink.record_trace(_make_trace(name=f"trace-{i}"))

        all_traces = sink.get_all_traces()
        assert len(all_traces) == 2
        assert all_traces[0].name == "trace-2"
        assert all_traces[1].name == "trace-3"

    @pytest.mark.asyncio
    async def test_query_spans_with_tool_glob(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(tool_name="calculator"))
        await sink.record_span(_make_span(tool_name="calendar"))
        await sink.record_span(_make_span(tool_name="weather"))

        results = await _collect_spans(sink.query_spans(SpanQuery(tool="cal*")))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_spans_with_namespace(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(namespace="math"))
        await sink.record_span(_make_span(namespace="science"))

        results = await _collect_spans(sink.query_spans(SpanQuery(namespace="math")))
        assert len(results) == 1
        assert results[0].namespace == "math"

    @pytest.mark.asyncio
    async def test_query_spans_with_outcome(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(outcome=ExecutionOutcome.SUCCESS))
        await sink.record_span(_make_span(outcome=ExecutionOutcome.FAILED))

        results = await _collect_spans(sink.query_spans(SpanQuery(outcome=ExecutionOutcome.FAILED)))
        assert len(results) == 1
        assert results[0].outcome == ExecutionOutcome.FAILED

    @pytest.mark.asyncio
    async def test_query_spans_with_trace_id(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(trace_id="t-1"))
        await sink.record_span(_make_span(trace_id="t-2"))

        results = await _collect_spans(sink.query_spans(SpanQuery(trace_id="t-1")))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_spans_with_request_id(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(request_id="r-1"))
        await sink.record_span(_make_span(request_id="r-2"))

        results = await _collect_spans(sink.query_spans(SpanQuery(request_id="r-1")))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_spans_with_since_until(self):
        sink = InMemoryTraceSink()
        now = datetime.now(UTC)
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=2)

        await sink.record_span(_make_span(created_at=past))
        await sink.record_span(_make_span(created_at=now))
        await sink.record_span(_make_span(created_at=future))

        # since: only those at or after 'now - 30min'
        threshold = now - timedelta(minutes=30)
        results = await _collect_spans(sink.query_spans(SpanQuery(since=threshold)))
        assert len(results) == 2

        # until: only those at or before 'now + 30min'
        threshold2 = now + timedelta(minutes=30)
        results2 = await _collect_spans(sink.query_spans(SpanQuery(until=threshold2)))
        assert len(results2) == 2

    @pytest.mark.asyncio
    async def test_query_spans_with_duration_filters(self):
        sink = InMemoryTraceSink()
        now = datetime.now(UTC)
        # span with ~50ms duration
        await sink.record_span(_make_span(created_at=now, ended_at=now + timedelta(milliseconds=50)))
        # span with ~200ms duration
        await sink.record_span(_make_span(created_at=now, ended_at=now + timedelta(milliseconds=200)))

        # min_duration_ms=100 -> only the 200ms one
        results = await _collect_spans(sink.query_spans(SpanQuery(min_duration_ms=100.0)))
        assert len(results) == 1

        # max_duration_ms=100 -> only the 50ms one
        results2 = await _collect_spans(sink.query_spans(SpanQuery(max_duration_ms=100.0)))
        assert len(results2) == 1

    @pytest.mark.asyncio
    async def test_query_spans_blocked_only(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(blocked=True))
        await sink.record_span(_make_span(outcome=ExecutionOutcome.SUCCESS))

        results = await _collect_spans(sink.query_spans(SpanQuery(blocked_only=True)))
        assert len(results) == 1
        assert results[0].outcome == ExecutionOutcome.BLOCKED

    @pytest.mark.asyncio
    async def test_query_spans_failed_only(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span(outcome=ExecutionOutcome.FAILED))
        await sink.record_span(_make_span(outcome=ExecutionOutcome.SUCCESS))

        results = await _collect_spans(sink.query_spans(SpanQuery(failed_only=True)))
        assert len(results) == 1
        assert results[0].outcome == ExecutionOutcome.FAILED

    @pytest.mark.asyncio
    async def test_query_spans_offset_and_limit(self):
        sink = InMemoryTraceSink()
        for i in range(10):
            await sink.record_span(_make_span(tool_name=f"tool-{i}"))

        # limit=3
        results = await _collect_spans(sink.query_spans(SpanQuery(limit=3)))
        assert len(results) == 3

        # offset=2, limit=3 (newest first, so offset skips 2 newest)
        results2 = await _collect_spans(sink.query_spans(SpanQuery(offset=2, limit=3)))
        assert len(results2) == 3

    @pytest.mark.asyncio
    async def test_query_traces_with_trace_id(self):
        sink = InMemoryTraceSink()
        await sink.record_trace(_make_trace(trace_id="t-1"))
        await sink.record_trace(_make_trace(trace_id="t-2"))

        results = await _collect_traces(sink.query_traces(TraceQuery(trace_id="t-1")))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_traces_with_name(self):
        sink = InMemoryTraceSink()
        await sink.record_trace(_make_trace(name="my-trace"))
        await sink.record_trace(_make_trace(name="other-trace"))

        results = await _collect_traces(sink.query_traces(TraceQuery(name="my-trace")))
        assert len(results) == 1
        assert results[0].name == "my-trace"

    @pytest.mark.asyncio
    async def test_query_traces_with_tags(self):
        sink = InMemoryTraceSink()
        await sink.record_trace(_make_trace(tags=["a", "b"]))
        await sink.record_trace(_make_trace(tags=["b", "c"]))

        # Must match ALL tags
        results = await _collect_traces(sink.query_traces(TraceQuery(tags=["a", "b"])))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_traces_with_since_until(self):
        sink = InMemoryTraceSink()
        now = datetime.now(UTC)
        past = now - timedelta(hours=2)
        future = now + timedelta(hours=2)

        await sink.record_trace(_make_trace(created_at=past))
        await sink.record_trace(_make_trace(created_at=now))
        await sink.record_trace(_make_trace(created_at=future))

        threshold = now - timedelta(minutes=30)
        results = await _collect_traces(sink.query_traces(TraceQuery(since=threshold)))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_traces_deterministic_only(self):
        sink = InMemoryTraceSink()
        await sink.record_trace(_make_trace(deterministic=True))
        await sink.record_trace(_make_trace(deterministic=False))

        results = await _collect_traces(sink.query_traces(TraceQuery(deterministic_only=True)))
        assert len(results) == 1
        assert results[0].deterministic is True

    @pytest.mark.asyncio
    async def test_query_traces_offset_and_limit(self):
        sink = InMemoryTraceSink()
        for i in range(10):
            await sink.record_trace(_make_trace(name=f"trace-{i}"))

        results = await _collect_traces(sink.query_traces(TraceQuery(limit=3)))
        assert len(results) == 3

        results2 = await _collect_traces(sink.query_traces(TraceQuery(offset=2, limit=3)))
        assert len(results2) == 3

    @pytest.mark.asyncio
    async def test_get_stats(self):
        sink = InMemoryTraceSink()
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)

        await sink.record_span(
            _make_span(
                tool_name="calc",
                outcome=ExecutionOutcome.SUCCESS,
                created_at=past,
            )
        )
        await sink.record_span(
            _make_span(
                tool_name="weather",
                outcome=ExecutionOutcome.FAILED,
                created_at=now,
            )
        )
        await sink.record_trace(_make_trace())

        stats = await sink.get_stats()
        assert stats.span_count == 2
        assert stats.trace_count == 1
        assert stats.oldest_span is not None
        assert stats.newest_span is not None
        assert stats.oldest_span <= stats.newest_span
        assert "success" in stats.outcome_counts
        assert "failed" in stats.outcome_counts
        assert len(stats.tools_seen) == 2

    @pytest.mark.asyncio
    async def test_get_stats_empty(self):
        sink = InMemoryTraceSink()
        stats = await sink.get_stats()
        assert stats.span_count == 0
        assert stats.trace_count == 0
        assert stats.oldest_span is None
        assert stats.newest_span is None

    @pytest.mark.asyncio
    async def test_clear(self):
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span())
        await sink.record_trace(_make_trace())

        await sink.clear()
        assert sink.get_all_spans() == []
        assert sink.get_all_traces() == []

    def test_get_all_spans_sync(self):
        sink = InMemoryTraceSink()
        assert sink.get_all_spans() == []

    def test_get_all_traces_sync(self):
        sink = InMemoryTraceSink()
        assert sink.get_all_traces() == []

    @pytest.mark.asyncio
    async def test_query_spans_no_query(self):
        """Passing None as query returns all."""
        sink = InMemoryTraceSink()
        await sink.record_span(_make_span())
        results = await _collect_spans(sink.query_spans(None))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_traces_no_query(self):
        """Passing None as query returns all."""
        sink = InMemoryTraceSink()
        await sink.record_trace(_make_trace())
        results = await _collect_traces(sink.query_traces(None))
        assert len(results) == 1


# ------------------------------------------------------------------ #
# FileTraceSink
# ------------------------------------------------------------------ #


class TestFileTraceSink:
    @pytest.mark.asyncio
    async def test_record_and_query_span(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        span = _make_span()
        await sink.record_span(span)

        results = await _collect_spans(sink.query_spans())
        assert len(results) == 1
        assert results[0].tool_name == "calculator"

    @pytest.mark.asyncio
    async def test_record_and_query_trace(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        trace = _make_trace()
        await sink.record_trace(trace)

        results = await _collect_traces(sink.query_traces())
        assert len(results) == 1
        assert results[0].name == "test-trace"

    @pytest.mark.asyncio
    async def test_query_spans_empty_file(self, tmp_path: Path):
        """No spans file => returns nothing."""
        sink = FileTraceSink(directory=tmp_path)
        results = await _collect_spans(sink.query_spans())
        assert results == []

    @pytest.mark.asyncio
    async def test_query_traces_empty_file(self, tmp_path: Path):
        """No traces file => returns nothing."""
        sink = FileTraceSink(directory=tmp_path)
        results = await _collect_traces(sink.query_traces())
        assert results == []

    @pytest.mark.asyncio
    async def test_query_spans_with_filter(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        await sink.record_span(_make_span(tool_name="calc"))
        await sink.record_span(_make_span(tool_name="weather"))

        results = await _collect_spans(sink.query_spans(SpanQuery(tool="calc")))
        assert len(results) == 1
        assert results[0].tool_name == "calc"

    @pytest.mark.asyncio
    async def test_query_spans_offset_limit(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        for i in range(5):
            await sink.record_span(_make_span(tool_name=f"tool-{i}"))

        results = await _collect_spans(sink.query_spans(SpanQuery(offset=1, limit=2)))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_traces_with_filter(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        await sink.record_trace(_make_trace(name="alpha"))
        await sink.record_trace(_make_trace(name="beta"))

        results = await _collect_traces(sink.query_traces(TraceQuery(name="alpha")))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_traces_offset_limit(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        for i in range(5):
            await sink.record_trace(_make_trace(name=f"trace-{i}"))

        results = await _collect_traces(sink.query_traces(TraceQuery(offset=1, limit=2)))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        await sink.record_span(_make_span(outcome=ExecutionOutcome.SUCCESS))
        await sink.record_span(_make_span(outcome=ExecutionOutcome.FAILED))
        await sink.record_trace(_make_trace())

        stats = await sink.get_stats()
        assert stats.span_count == 2
        assert stats.trace_count == 1
        assert stats.oldest_span is not None
        assert stats.newest_span is not None
        assert len(stats.tools_seen) >= 1

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, tmp_path: Path):
        sink = FileTraceSink(directory=tmp_path)
        stats = await sink.get_stats()
        assert stats.span_count == 0
        assert stats.trace_count == 0

    @pytest.mark.asyncio
    async def test_malformed_line_spans(self, tmp_path: Path):
        """Malformed lines should be skipped without error."""
        sink = FileTraceSink(directory=tmp_path)
        # Write a valid span first
        await sink.record_span(_make_span())
        # Append a malformed line
        spans_path = tmp_path / "spans.jsonl"
        with spans_path.open("a") as f:
            f.write("this is not json\n")

        results = await _collect_spans(sink.query_spans())
        assert len(results) == 1  # only the valid span

    @pytest.mark.asyncio
    async def test_malformed_line_traces(self, tmp_path: Path):
        """Malformed lines should be skipped without error."""
        sink = FileTraceSink(directory=tmp_path)
        await sink.record_trace(_make_trace())
        traces_path = tmp_path / "traces.jsonl"
        with traces_path.open("a") as f:
            f.write("{{bad json}}\n")

        results = await _collect_traces(sink.query_traces())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_malformed_line_stats(self, tmp_path: Path):
        """Stats should handle malformed lines gracefully."""
        sink = FileTraceSink(directory=tmp_path)
        await sink.record_span(_make_span())
        spans_path = tmp_path / "spans.jsonl"
        with spans_path.open("a") as f:
            f.write("not json\n")

        stats = await sink.get_stats()
        assert stats.span_count == 1  # only the valid one counted

    @pytest.mark.asyncio
    async def test_file_rotation(self, tmp_path: Path):
        # Set rotate_size_mb very small so rotation triggers
        sink = FileTraceSink(directory=tmp_path, rotate_size_mb=0)
        # The rotate size is 0 * 1024*1024 = 0, so any existing file triggers rotation
        await sink.record_span(_make_span(tool_name="first"))
        # Now the file exists with non-zero size, next write triggers rotation
        await sink.record_span(_make_span(tool_name="second"))

        # Check that rotated file exists
        rotated = tmp_path / "spans.jsonl.1"
        assert rotated.exists()

    @pytest.mark.asyncio
    async def test_maybe_rotate_nonexistent_file(self, tmp_path: Path):
        """Rotation on nonexistent file is a no-op."""
        sink = FileTraceSink(directory=tmp_path)
        # Directly call _maybe_rotate on a path that doesn't exist
        await sink._maybe_rotate(tmp_path / "doesnotexist.jsonl")
        # No error should occur

    @pytest.mark.asyncio
    async def test_maybe_rotate_below_threshold(self, tmp_path: Path):
        """File below threshold size should not be rotated."""
        sink = FileTraceSink(directory=tmp_path, rotate_size_mb=100)
        await sink.record_span(_make_span())
        spans_path = tmp_path / "spans.jsonl"
        assert spans_path.exists()

        rotated = tmp_path / "spans.jsonl.1"
        assert not rotated.exists()

    def test_write_line(self, tmp_path: Path):
        path = tmp_path / "test.jsonl"
        FileTraceSink._write_line(path, '{"test": true}\n')
        assert path.read_text() == '{"test": true}\n'

    def test_read_lines(self, tmp_path: Path):
        path = tmp_path / "test.jsonl"
        path.write_text("line1\nline2\nline3\n")
        lines = FileTraceSink._read_lines(path)
        assert len(lines) == 3

    def test_count_lines(self, tmp_path: Path):
        path = tmp_path / "test.jsonl"
        path.write_text("line1\nline2\nline3\n")
        count = FileTraceSink._count_lines(path)
        assert count == 3

    @pytest.mark.asyncio
    async def test_directory_created(self, tmp_path: Path):
        new_dir = tmp_path / "nested" / "deep"
        FileTraceSink(directory=new_dir)
        assert new_dir.exists()

    @pytest.mark.asyncio
    async def test_custom_filenames(self, tmp_path: Path):
        sink = FileTraceSink(
            directory=tmp_path,
            spans_file="my_spans.jsonl",
            traces_file="my_traces.jsonl",
        )
        await sink.record_span(_make_span())
        await sink.record_trace(_make_trace())

        assert (tmp_path / "my_spans.jsonl").exists()
        assert (tmp_path / "my_traces.jsonl").exists()

    @pytest.mark.asyncio
    async def test_multiple_rotations(self, tmp_path: Path):
        """Rotation cascades (file.1 -> file.2 etc.)."""
        sink = FileTraceSink(directory=tmp_path, rotate_size_mb=0)
        # Write 4 times to trigger multiple rotations
        for i in range(4):
            await sink.record_span(_make_span(tool_name=f"tool-{i}"))

        # We should have rotated files
        assert (tmp_path / "spans.jsonl").exists()
        assert (tmp_path / "spans.jsonl.1").exists()


# ------------------------------------------------------------------ #
# NoOpTraceSink
# ------------------------------------------------------------------ #


class TestNoOpTraceSink:
    @pytest.mark.asyncio
    async def test_record_span(self):
        sink = NoOpTraceSink()
        await sink.record_span(_make_span())  # should not raise

    @pytest.mark.asyncio
    async def test_record_trace(self):
        sink = NoOpTraceSink()
        await sink.record_trace(_make_trace())  # should not raise

    @pytest.mark.asyncio
    async def test_query_spans_empty(self):
        sink = NoOpTraceSink()
        results = await _collect_spans(sink.query_spans())
        assert results == []

    @pytest.mark.asyncio
    async def test_query_traces_empty(self):
        sink = NoOpTraceSink()
        results = await _collect_traces(sink.query_traces())
        assert results == []

    @pytest.mark.asyncio
    async def test_get_stats_empty(self):
        sink = NoOpTraceSink()
        stats = await sink.get_stats()
        assert stats.span_count == 0
        assert stats.trace_count == 0


# ------------------------------------------------------------------ #
# CompositeTraceSink
# ------------------------------------------------------------------ #


class TestCompositeTraceSink:
    @pytest.mark.asyncio
    async def test_fan_out_record_span(self):
        s1 = InMemoryTraceSink()
        s2 = InMemoryTraceSink()
        composite = CompositeTraceSink([s1, s2])

        span = _make_span()
        await composite.record_span(span)

        assert len(s1.get_all_spans()) == 1
        assert len(s2.get_all_spans()) == 1

    @pytest.mark.asyncio
    async def test_fan_out_record_trace(self):
        s1 = InMemoryTraceSink()
        s2 = InMemoryTraceSink()
        composite = CompositeTraceSink([s1, s2])

        trace = _make_trace()
        await composite.record_trace(trace)

        assert len(s1.get_all_traces()) == 1
        assert len(s2.get_all_traces()) == 1

    @pytest.mark.asyncio
    async def test_query_from_first_sink(self):
        s1 = InMemoryTraceSink()
        s2 = InMemoryTraceSink()
        composite = CompositeTraceSink([s1, s2])

        await s1.record_span(_make_span(tool_name="from-s1"))
        await s2.record_span(_make_span(tool_name="from-s2"))

        results = await _collect_spans(composite.query_spans())
        assert len(results) == 1
        assert results[0].tool_name == "from-s1"

    @pytest.mark.asyncio
    async def test_query_traces_from_first_sink(self):
        s1 = InMemoryTraceSink()
        s2 = InMemoryTraceSink()
        composite = CompositeTraceSink([s1, s2])

        await s1.record_trace(_make_trace(name="from-s1"))
        await s2.record_trace(_make_trace(name="from-s2"))

        results = await _collect_traces(composite.query_traces())
        assert len(results) == 1
        assert results[0].name == "from-s1"

    @pytest.mark.asyncio
    async def test_get_stats_from_first_sink(self):
        s1 = InMemoryTraceSink()
        s2 = InMemoryTraceSink()
        composite = CompositeTraceSink([s1, s2])

        await s1.record_span(_make_span())

        stats = await composite.get_stats()
        assert stats.span_count == 1

    @pytest.mark.asyncio
    async def test_empty_composite_query_spans(self):
        composite = CompositeTraceSink([])
        results = await _collect_spans(composite.query_spans())
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_composite_query_traces(self):
        composite = CompositeTraceSink([])
        results = await _collect_traces(composite.query_traces())
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_composite_get_stats(self):
        composite = CompositeTraceSink([])
        stats = await composite.get_stats()
        assert stats.span_count == 0


# ------------------------------------------------------------------ #
# BaseTraceSink._span_matches_query & _trace_matches_query
# ------------------------------------------------------------------ #


class TestBaseTraceSinkMatchers:
    """Test the match methods directly using InMemoryTraceSink (a concrete subclass)."""

    def _sink(self) -> InMemoryTraceSink:
        return InMemoryTraceSink()

    def test_span_matches_all_empty_query(self):
        sink = self._sink()
        span = _make_span()
        assert sink._span_matches_query(span, SpanQuery()) is True

    def test_span_matches_tool_glob(self):
        sink = self._sink()
        span = _make_span(tool_name="calculator")
        assert sink._span_matches_query(span, SpanQuery(tool="calc*")) is True
        assert sink._span_matches_query(span, SpanQuery(tool="weather*")) is False

    def test_span_matches_namespace(self):
        sink = self._sink()
        span = _make_span(namespace="math")
        assert sink._span_matches_query(span, SpanQuery(namespace="math")) is True
        assert sink._span_matches_query(span, SpanQuery(namespace="science")) is False

    def test_span_matches_outcome(self):
        sink = self._sink()
        span = _make_span(outcome=ExecutionOutcome.SUCCESS)
        assert sink._span_matches_query(span, SpanQuery(outcome=ExecutionOutcome.SUCCESS)) is True
        assert sink._span_matches_query(span, SpanQuery(outcome=ExecutionOutcome.FAILED)) is False

    def test_span_matches_trace_id(self):
        sink = self._sink()
        span = _make_span(trace_id="t-1")
        assert sink._span_matches_query(span, SpanQuery(trace_id="t-1")) is True
        assert sink._span_matches_query(span, SpanQuery(trace_id="t-2")) is False

    def test_span_matches_request_id(self):
        sink = self._sink()
        span = _make_span(request_id="r-1")
        assert sink._span_matches_query(span, SpanQuery(request_id="r-1")) is True
        assert sink._span_matches_query(span, SpanQuery(request_id="r-2")) is False

    def test_span_matches_since(self):
        sink = self._sink()
        now = datetime.now(UTC)
        span = _make_span(created_at=now)
        assert sink._span_matches_query(span, SpanQuery(since=now - timedelta(hours=1))) is True
        assert sink._span_matches_query(span, SpanQuery(since=now + timedelta(hours=1))) is False

    def test_span_matches_until(self):
        sink = self._sink()
        now = datetime.now(UTC)
        span = _make_span(created_at=now)
        assert sink._span_matches_query(span, SpanQuery(until=now + timedelta(hours=1))) is True
        assert sink._span_matches_query(span, SpanQuery(until=now - timedelta(hours=1))) is False

    def test_span_matches_min_duration(self):
        sink = self._sink()
        now = datetime.now(UTC)
        span = _make_span(created_at=now, ended_at=now + timedelta(milliseconds=100))
        assert sink._span_matches_query(span, SpanQuery(min_duration_ms=50.0)) is True
        assert sink._span_matches_query(span, SpanQuery(min_duration_ms=200.0)) is False

    def test_span_matches_max_duration(self):
        sink = self._sink()
        now = datetime.now(UTC)
        span = _make_span(created_at=now, ended_at=now + timedelta(milliseconds=100))
        assert sink._span_matches_query(span, SpanQuery(max_duration_ms=200.0)) is True
        assert sink._span_matches_query(span, SpanQuery(max_duration_ms=50.0)) is False

    def test_span_matches_blocked_only(self):
        sink = self._sink()
        blocked_span = _make_span(blocked=True)
        normal_span = _make_span(outcome=ExecutionOutcome.SUCCESS)
        assert sink._span_matches_query(blocked_span, SpanQuery(blocked_only=True)) is True
        assert sink._span_matches_query(normal_span, SpanQuery(blocked_only=True)) is False

    def test_span_matches_failed_only(self):
        sink = self._sink()
        failed_span = _make_span(outcome=ExecutionOutcome.FAILED)
        success_span = _make_span(outcome=ExecutionOutcome.SUCCESS)
        assert sink._span_matches_query(failed_span, SpanQuery(failed_only=True)) is True
        assert sink._span_matches_query(success_span, SpanQuery(failed_only=True)) is False

    def test_trace_matches_all_empty_query(self):
        sink = self._sink()
        trace = _make_trace()
        assert sink._trace_matches_query(trace, TraceQuery()) is True

    def test_trace_matches_trace_id(self):
        sink = self._sink()
        trace = _make_trace(trace_id="t-1")
        assert sink._trace_matches_query(trace, TraceQuery(trace_id="t-1")) is True
        assert sink._trace_matches_query(trace, TraceQuery(trace_id="t-2")) is False

    def test_trace_matches_name(self):
        sink = self._sink()
        trace = _make_trace(name="my-trace")
        assert sink._trace_matches_query(trace, TraceQuery(name="my-trace")) is True
        assert sink._trace_matches_query(trace, TraceQuery(name="other")) is False

    def test_trace_matches_name_substring(self):
        """Name matching uses 'in' operator, so substring match works."""
        sink = self._sink()
        trace = _make_trace(name="my-important-trace")
        assert sink._trace_matches_query(trace, TraceQuery(name="important")) is True

    def test_trace_matches_tags(self):
        sink = self._sink()
        trace = _make_trace(tags=["a", "b", "c"])
        assert sink._trace_matches_query(trace, TraceQuery(tags=["a", "b"])) is True
        assert sink._trace_matches_query(trace, TraceQuery(tags=["a", "d"])) is False

    def test_trace_matches_since(self):
        sink = self._sink()
        now = datetime.now(UTC)
        trace = _make_trace(created_at=now)
        assert sink._trace_matches_query(trace, TraceQuery(since=now - timedelta(hours=1))) is True
        assert sink._trace_matches_query(trace, TraceQuery(since=now + timedelta(hours=1))) is False

    def test_trace_matches_until(self):
        sink = self._sink()
        now = datetime.now(UTC)
        trace = _make_trace(created_at=now)
        assert sink._trace_matches_query(trace, TraceQuery(until=now + timedelta(hours=1))) is True
        assert sink._trace_matches_query(trace, TraceQuery(until=now - timedelta(hours=1))) is False

    def test_trace_matches_deterministic_only(self):
        sink = self._sink()
        det_trace = _make_trace(deterministic=True)
        non_det_trace = _make_trace(deterministic=False)
        assert sink._trace_matches_query(det_trace, TraceQuery(deterministic_only=True)) is True
        assert sink._trace_matches_query(non_det_trace, TraceQuery(deterministic_only=True)) is False


# ------------------------------------------------------------------ #
# Global sink management
# ------------------------------------------------------------------ #


class TestGlobalSinkManagement:
    def test_get_trace_sink_default_is_noop(self):
        import chuk_tool_processor.observability.trace_sink as mod

        mod._global_sink = None  # Reset
        sink = get_trace_sink()
        assert isinstance(sink, NoOpTraceSink)

    def test_set_and_get_trace_sink(self):
        original = get_trace_sink()
        new_sink = InMemoryTraceSink()
        set_trace_sink(new_sink)
        assert get_trace_sink() is new_sink
        # Restore
        set_trace_sink(original)

    def test_init_trace_sink_memory(self):
        sink = init_trace_sink("memory")
        assert isinstance(sink, InMemoryTraceSink)
        assert get_trace_sink() is sink

    def test_init_trace_sink_memory_with_kwargs(self):
        sink = init_trace_sink("memory", max_spans=500, max_traces=50)
        assert isinstance(sink, InMemoryTraceSink)
        assert sink._max_spans == 500

    def test_init_trace_sink_file(self, tmp_path: Path):
        sink = init_trace_sink("file", directory=str(tmp_path))
        assert isinstance(sink, FileTraceSink)

    def test_init_trace_sink_noop(self):
        sink = init_trace_sink("noop")
        assert isinstance(sink, NoOpTraceSink)

    def test_init_trace_sink_enum(self):
        sink = init_trace_sink(TraceSinkType.MEMORY)
        assert isinstance(sink, InMemoryTraceSink)

    def test_init_trace_sink_unknown_string(self):
        with pytest.raises(ValueError, match="Unknown sink type"):
            init_trace_sink("unknown_type")

    def test_init_trace_sink_sets_global(self):
        sink = init_trace_sink(TraceSinkType.NOOP)
        assert get_trace_sink() is sink
