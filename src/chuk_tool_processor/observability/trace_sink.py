# chuk_tool_processor/observability/trace_sink.py
"""
TraceSink: Pluggable sink for execution traces.

This module provides the protocol and implementations for recording
and querying execution traces. TraceSink is the bridge between
execution and observability.

Available implementations:
- InMemoryTraceSink: For testing and debugging
- FileTraceSink: JSON Lines format for persistence
- CompositeTraceSink: Fan-out to multiple sinks
- (Future) SQLiteTraceSink, OTelTraceSink, etc.

Example:
    >>> sink = InMemoryTraceSink()
    >>> await sink.record_span(span)
    >>> await sink.record_trace(trace)
    >>>
    >>> # Query later
    >>> async for span in sink.query_spans(tool="calculator"):
    ...     print(span.outcome)
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.models.execution_span import ExecutionOutcome, ExecutionSpan
from chuk_tool_processor.models.execution_trace import ExecutionTrace

logger = get_logger("chuk_tool_processor.observability.trace_sink")


class SpanQuery(BaseModel):
    """Query parameters for span retrieval."""

    model_config = ConfigDict(frozen=True)

    tool: str | None = Field(default=None, description="Filter by tool name (glob pattern)")
    namespace: str | None = Field(default=None, description="Filter by namespace")
    outcome: ExecutionOutcome | None = Field(default=None, description="Filter by outcome")
    trace_id: str | None = Field(default=None, description="Filter by trace ID")
    request_id: str | None = Field(default=None, description="Filter by request ID")
    since: datetime | None = Field(default=None, description="Only spans after this time")
    until: datetime | None = Field(default=None, description="Only spans before this time")
    min_duration_ms: float | None = Field(default=None, description="Minimum duration")
    max_duration_ms: float | None = Field(default=None, description="Maximum duration")
    blocked_only: bool = Field(default=False, description="Only blocked spans")
    failed_only: bool = Field(default=False, description="Only failed spans")
    limit: int = Field(default=100, description="Maximum results to return")
    offset: int = Field(default=0, description="Skip first N results")


class TraceQuery(BaseModel):
    """Query parameters for trace retrieval."""

    model_config = ConfigDict(frozen=True)

    trace_id: str | None = Field(default=None, description="Filter by trace ID")
    name: str | None = Field(default=None, description="Filter by trace name")
    tags: list[str] = Field(default_factory=list, description="Filter by tags (all must match)")
    since: datetime | None = Field(default=None, description="Only traces after this time")
    until: datetime | None = Field(default=None, description="Only traces before this time")
    deterministic_only: bool = Field(default=False, description="Only deterministic traces")
    limit: int = Field(default=100, description="Maximum results to return")
    offset: int = Field(default=0, description="Skip first N results")


class TraceSinkStats(BaseModel):
    """Statistics from a trace sink."""

    model_config = ConfigDict(frozen=True)

    span_count: int = Field(default=0, description="Total spans recorded")
    trace_count: int = Field(default=0, description="Total traces recorded")
    oldest_span: datetime | None = Field(default=None, description="Oldest span timestamp")
    newest_span: datetime | None = Field(default=None, description="Newest span timestamp")
    tools_seen: list[str] = Field(default_factory=list, description="Unique tools seen")
    outcome_counts: dict[str, int] = Field(default_factory=dict, description="Counts by outcome")


@runtime_checkable
class TraceSink(Protocol):
    """
    Protocol for trace sinks.

    TraceSink defines the interface for recording and querying execution
    traces. Implementations can store traces in memory, files, databases,
    or forward them to external systems.
    """

    async def record_span(self, span: ExecutionSpan) -> None:
        """
        Record a single execution span.

        Args:
            span: The span to record
        """
        ...

    async def record_trace(self, trace: ExecutionTrace) -> None:
        """
        Record a complete execution trace.

        Args:
            trace: The trace to record
        """
        ...

    async def query_spans(
        self,
        _query: SpanQuery | None = None,
    ) -> AsyncIterator[ExecutionSpan]:
        """
        Query recorded spans.

        Args:
            _query: Query parameters (None = return all)

        Yields:
            Matching spans
        """
        return
        yield  # type: ignore[unreachable]

    async def query_traces(
        self,
        _query: TraceQuery | None = None,
    ) -> AsyncIterator[ExecutionTrace]:
        """
        Query recorded traces.

        Args:
            _query: Query parameters (None = return all)

        Yields:
            Matching traces
        """
        return
        yield  # type: ignore[unreachable]

    async def get_stats(self) -> TraceSinkStats:
        """Get statistics about recorded data."""
        ...


class BaseTraceSink(ABC):
    """Abstract base class for trace sinks with common functionality."""

    @abstractmethod
    async def record_span(self, span: ExecutionSpan) -> None:
        """Record a single execution span."""
        ...

    @abstractmethod
    async def record_trace(self, trace: ExecutionTrace) -> None:
        """Record a complete execution trace."""
        ...

    @abstractmethod
    async def query_spans(self, query: SpanQuery | None = None) -> AsyncIterator[ExecutionSpan]:
        """Query recorded spans."""
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    @abstractmethod
    async def query_traces(self, query: TraceQuery | None = None) -> AsyncIterator[ExecutionTrace]:
        """Query recorded traces."""
        raise NotImplementedError
        yield  # type: ignore[unreachable]

    @abstractmethod
    async def get_stats(self) -> TraceSinkStats:
        """Get statistics about recorded data."""
        ...

    def _span_matches_query(self, span: ExecutionSpan, query: SpanQuery) -> bool:
        """Check if a span matches query criteria."""
        import fnmatch

        if query.tool and not fnmatch.fnmatch(span.tool_name, query.tool):
            return False
        if query.namespace and span.namespace != query.namespace:
            return False
        if query.outcome and span.outcome != query.outcome:
            return False
        if query.trace_id and span.trace_id != query.trace_id:
            return False
        if query.request_id and span.request_id != query.request_id:
            return False
        if query.since and span.created_at < query.since:
            return False
        if query.until and span.created_at > query.until:
            return False
        if query.min_duration_ms and span.duration_ms < query.min_duration_ms:
            return False
        if query.max_duration_ms and span.duration_ms > query.max_duration_ms:
            return False
        if query.blocked_only and not span.blocked:
            return False
        return not (query.failed_only and span.outcome != ExecutionOutcome.FAILED)

    def _trace_matches_query(self, trace: ExecutionTrace, query: TraceQuery) -> bool:
        """Check if a trace matches query criteria."""
        if query.trace_id and trace.trace_id != query.trace_id:
            return False
        if query.name and query.name not in trace.name:
            return False
        if query.tags and not all(tag in trace.tags for tag in query.tags):
            return False
        if query.since and trace.created_at < query.since:
            return False
        if query.until and trace.created_at > query.until:
            return False
        return not (query.deterministic_only and not trace.deterministic)


class InMemoryTraceSink(BaseTraceSink):
    """
    In-memory trace sink for testing and debugging.

    This sink stores all spans and traces in memory. Useful for:
    - Unit tests
    - Interactive debugging
    - Short-lived processes

    Note: Data is lost when the process exits.

    Example:
        >>> sink = InMemoryTraceSink(max_spans=1000)
        >>> await sink.record_span(span)
        >>> async for s in sink.query_spans(SpanQuery(tool="calc*")):
        ...     print(s.outcome)
    """

    def __init__(
        self,
        max_spans: int = 10000,
        max_traces: int = 1000,
    ):
        """
        Initialize in-memory sink.

        Args:
            max_spans: Maximum spans to keep (FIFO eviction)
            max_traces: Maximum traces to keep (FIFO eviction)
        """
        self._max_spans = max_spans
        self._max_traces = max_traces
        self._spans: list[ExecutionSpan] = []
        self._traces: list[ExecutionTrace] = []
        self._lock = asyncio.Lock()

    async def record_span(self, span: ExecutionSpan) -> None:
        """Record a span, evicting oldest if at capacity."""
        async with self._lock:
            self._spans.append(span)
            # FIFO eviction
            while len(self._spans) > self._max_spans:
                self._spans.pop(0)

    async def record_trace(self, trace: ExecutionTrace) -> None:
        """Record a trace, evicting oldest if at capacity."""
        async with self._lock:
            self._traces.append(trace)
            while len(self._traces) > self._max_traces:
                self._traces.pop(0)

    async def query_spans(self, query: SpanQuery | None = None) -> AsyncIterator[ExecutionSpan]:
        """Query spans with filtering."""
        query = query or SpanQuery()
        count = 0
        skipped = 0

        async with self._lock:
            for span in reversed(self._spans):  # Newest first
                if not self._span_matches_query(span, query):
                    continue

                if skipped < query.offset:
                    skipped += 1
                    continue

                yield span
                count += 1

                if count >= query.limit:
                    break

    async def query_traces(self, query: TraceQuery | None = None) -> AsyncIterator[ExecutionTrace]:
        """Query traces with filtering."""
        query = query or TraceQuery()
        count = 0
        skipped = 0

        async with self._lock:
            for trace in reversed(self._traces):
                if not self._trace_matches_query(trace, query):
                    continue

                if skipped < query.offset:
                    skipped += 1
                    continue

                yield trace
                count += 1

                if count >= query.limit:
                    break

    async def get_stats(self) -> TraceSinkStats:
        """Get statistics."""
        async with self._lock:
            outcome_counts: dict[str, int] = defaultdict(int)
            tools_seen: set[str] = set()
            oldest: datetime | None = None
            newest: datetime | None = None

            for span in self._spans:
                outcome_counts[span.outcome.value] += 1
                tools_seen.add(span.full_tool_name)

                if oldest is None or span.created_at < oldest:
                    oldest = span.created_at
                if newest is None or span.created_at > newest:
                    newest = span.created_at

            return TraceSinkStats(
                span_count=len(self._spans),
                trace_count=len(self._traces),
                oldest_span=oldest,
                newest_span=newest,
                tools_seen=sorted(tools_seen),
                outcome_counts=dict(outcome_counts),
            )

    async def clear(self) -> None:
        """Clear all stored data."""
        async with self._lock:
            self._spans.clear()
            self._traces.clear()

    def get_all_spans(self) -> list[ExecutionSpan]:
        """Get all spans (sync, for testing)."""
        return list(self._spans)

    def get_all_traces(self) -> list[ExecutionTrace]:
        """Get all traces (sync, for testing)."""
        return list(self._traces)


class FileTraceSink(BaseTraceSink):
    """
    File-based trace sink using JSON Lines format.

    Stores spans and traces in append-only files for persistence.
    Good for:
    - Local development
    - Log aggregation pipelines
    - Post-mortem analysis

    Example:
        >>> sink = FileTraceSink(directory="/var/log/traces")
        >>> await sink.record_span(span)
        >>> # Later
        >>> async for s in sink.query_spans():
        ...     print(s.tool_name)
    """

    def __init__(
        self,
        directory: str | Path,
        spans_file: str = "spans.jsonl",
        traces_file: str = "traces.jsonl",
        rotate_size_mb: int = 100,
    ):
        """
        Initialize file sink.

        Args:
            directory: Directory for trace files
            spans_file: Filename for spans
            traces_file: Filename for traces
            rotate_size_mb: Rotate files when they reach this size
        """
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

        self._spans_path = self._directory / spans_file
        self._traces_path = self._directory / traces_file
        self._rotate_size = rotate_size_mb * 1024 * 1024
        self._lock = asyncio.Lock()

    async def record_span(self, span: ExecutionSpan) -> None:
        """Append span to file."""
        async with self._lock:
            await self._maybe_rotate(self._spans_path)
            line = json.dumps(span.model_dump(), default=str) + "\n"
            with self._spans_path.open("a") as f:
                f.write(line)

    async def record_trace(self, trace: ExecutionTrace) -> None:
        """Append trace to file."""
        async with self._lock:
            await self._maybe_rotate(self._traces_path)
            line = json.dumps(trace.model_dump(), default=str) + "\n"
            with self._traces_path.open("a") as f:
                f.write(line)

    async def _maybe_rotate(self, path: Path) -> None:
        """Rotate file if it exceeds size limit."""
        if not path.exists():
            return
        if path.stat().st_size < self._rotate_size:
            return

        # Rotate: file.jsonl -> file.jsonl.1, file.jsonl.1 -> file.jsonl.2, etc.
        for i in range(9, 0, -1):
            old = path.with_suffix(f".jsonl.{i}")
            new = path.with_suffix(f".jsonl.{i + 1}")
            if old.exists():
                old.rename(new)

        path.rename(path.with_suffix(".jsonl.1"))
        logger.info(f"Rotated trace file: {path}")

    async def query_spans(self, query: SpanQuery | None = None) -> AsyncIterator[ExecutionSpan]:
        """Query spans from file."""
        query = query or SpanQuery()

        if not self._spans_path.exists():
            return

        count = 0
        skipped = 0

        # Read file in reverse for newest-first ordering would be expensive
        # For now, just read forward
        with self._spans_path.open() as f:
            for line in f:
                try:
                    data = json.loads(line)
                    span = ExecutionSpan.model_validate(data)

                    if not self._span_matches_query(span, query):
                        continue

                    if skipped < query.offset:
                        skipped += 1
                        continue

                    yield span
                    count += 1

                    if count >= query.limit:
                        break

                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse span line: {e}")

    async def query_traces(self, query: TraceQuery | None = None) -> AsyncIterator[ExecutionTrace]:
        """Query traces from file."""
        query = query or TraceQuery()

        if not self._traces_path.exists():
            return

        count = 0
        skipped = 0

        with self._traces_path.open() as f:
            for line in f:
                try:
                    data = json.loads(line)
                    trace = ExecutionTrace.model_validate(data)

                    if not self._trace_matches_query(trace, query):
                        continue

                    if skipped < query.offset:
                        skipped += 1
                        continue

                    yield trace
                    count += 1

                    if count >= query.limit:
                        break

                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse trace line: {e}")

    async def get_stats(self) -> TraceSinkStats:
        """Get statistics (expensive - reads entire file)."""
        outcome_counts: dict[str, int] = defaultdict(int)
        tools_seen: set[str] = set()
        oldest: datetime | None = None
        newest: datetime | None = None
        span_count = 0
        trace_count = 0

        if self._spans_path.exists():
            with self._spans_path.open() as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        span_count += 1
                        outcome_counts[data.get("outcome", "unknown")] += 1
                        tools_seen.add(data.get("tool_name", "unknown"))

                        created = datetime.fromisoformat(data.get("created_at", ""))
                        if oldest is None or created < oldest:
                            oldest = created
                        if newest is None or created > newest:
                            newest = created
                    except Exception:
                        pass

        if self._traces_path.exists():
            with self._traces_path.open() as f:
                trace_count = sum(1 for _ in f)

        return TraceSinkStats(
            span_count=span_count,
            trace_count=trace_count,
            oldest_span=oldest,
            newest_span=newest,
            tools_seen=sorted(tools_seen),
            outcome_counts=dict(outcome_counts),
        )


class CompositeTraceSink(BaseTraceSink):
    """
    Fan-out sink that writes to multiple sinks.

    Useful for:
    - Writing to both file and memory
    - Forwarding to multiple systems
    - Conditional routing

    Example:
        >>> sink = CompositeTraceSink([
        ...     InMemoryTraceSink(),
        ...     FileTraceSink("/var/log/traces"),
        ... ])
        >>> await sink.record_span(span)  # Written to both
    """

    def __init__(self, sinks: list[BaseTraceSink]):
        """
        Initialize composite sink.

        Args:
            sinks: List of sinks to write to
        """
        self._sinks = sinks

    async def record_span(self, span: ExecutionSpan) -> None:
        """Record to all sinks."""
        await asyncio.gather(*[sink.record_span(span) for sink in self._sinks], return_exceptions=True)

    async def record_trace(self, trace: ExecutionTrace) -> None:
        """Record to all sinks."""
        await asyncio.gather(*[sink.record_trace(trace) for sink in self._sinks], return_exceptions=True)

    async def query_spans(self, query: SpanQuery | None = None) -> AsyncIterator[ExecutionSpan]:
        """Query from first sink only (for simplicity)."""
        if not self._sinks:
            return
        async for span in self._sinks[0].query_spans(query):
            yield span

    async def query_traces(self, query: TraceQuery | None = None) -> AsyncIterator[ExecutionTrace]:
        """Query from first sink only."""
        if not self._sinks:
            return
        async for trace in self._sinks[0].query_traces(query):
            yield trace

    async def get_stats(self) -> TraceSinkStats:
        """Get stats from first sink."""
        if self._sinks:
            return await self._sinks[0].get_stats()
        return TraceSinkStats()


class NoOpTraceSink(BaseTraceSink):
    """No-op sink that discards all data. Useful for disabling tracing."""

    async def record_span(self, span: ExecutionSpan) -> None:
        """Discard span."""
        pass

    async def record_trace(self, trace: ExecutionTrace) -> None:
        """Discard trace."""
        pass

    async def query_spans(
        self,
        _query: SpanQuery | None = None,
    ) -> AsyncIterator[ExecutionSpan]:
        """Return nothing."""
        return
        yield  # type: ignore[unreachable]

    async def query_traces(
        self,
        _query: TraceQuery | None = None,
    ) -> AsyncIterator[ExecutionTrace]:
        """Return nothing."""
        return
        yield  # type: ignore[unreachable]

    async def get_stats(self) -> TraceSinkStats:
        """Return empty stats."""
        return TraceSinkStats()


# ------------------------------------------------------------------ #
# Global sink management
# ------------------------------------------------------------------ #

_global_sink: BaseTraceSink | None = None


def get_trace_sink() -> BaseTraceSink:
    """Get the global trace sink."""
    global _global_sink
    if _global_sink is None:
        _global_sink = NoOpTraceSink()
    return _global_sink


def set_trace_sink(sink: BaseTraceSink) -> None:
    """Set the global trace sink."""
    global _global_sink
    _global_sink = sink


def init_trace_sink(
    sink_type: str = "memory",
    **kwargs: Any,
) -> BaseTraceSink:
    """
    Initialize and set the global trace sink.

    Args:
        sink_type: "memory", "file", "noop"
        **kwargs: Additional arguments for sink constructor

    Returns:
        The initialized sink
    """
    sink: BaseTraceSink
    if sink_type == "memory":
        sink = InMemoryTraceSink(**kwargs)
    elif sink_type == "file":
        sink = FileTraceSink(**kwargs)
    elif sink_type == "noop":
        sink = NoOpTraceSink()
    else:
        raise ValueError(f"Unknown sink type: {sink_type}")

    set_trace_sink(sink)
    return sink
