# chuk_tool_processor/models/execution_trace.py
"""
ExecutionTrace: Complete trace for deterministic replay.

This module provides the capability to:
- Capture complete execution traces
- Replay executions for testing/debugging
- Compare actual vs expected outputs
- Generate training data from real executions

ExecutionTrace is the foundation for:
- Regression testing agent behavior
- RL-style training loops
- A/B testing model changes
- "Why did this fail?" forensics

Example:
    >>> # Capture a trace
    >>> trace = ExecutionTrace(...)
    >>> trace.add_span(span)
    >>>
    >>> # Later: replay it
    >>> replay_result = await trace.replay(executor)
    >>> assert replay_result.matches(trace)
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from chuk_tool_processor.core.context import ExecutionContext
from chuk_tool_processor.models.execution_span import ExecutionOutcome, ExecutionSpan
from chuk_tool_processor.models.tool_call import ToolCall


class ReplayMode(str, Enum):
    """Mode for replay execution."""

    STRICT = "strict"  # Fail if any output differs
    LENIENT = "lenient"  # Allow non-deterministic differences
    COMPARE_ONLY = "compare_only"  # Don't re-execute, just compare traces


class ReplayDifference(BaseModel):
    """A difference found during replay comparison."""

    model_config = ConfigDict(frozen=True)

    span_index: int = Field(..., description="Index of the span in the trace")
    tool_name: str = Field(..., description="Name of the tool")
    field: str = Field(..., description="Field that differed")
    expected: Any = Field(..., description="Expected value from original trace")
    actual: Any = Field(..., description="Actual value from replay")
    severity: str = Field(
        default="error",
        description="Severity: 'error' (deterministic mismatch), 'warning' (acceptable variance)",
    )


class ReplayResult(BaseModel):
    """Result of replaying a trace."""

    model_config = ConfigDict(frozen=True)

    original_trace_id: str = Field(..., description="ID of the original trace")
    replay_trace_id: str = Field(..., description="ID of the replay trace")
    mode: ReplayMode = Field(..., description="Mode used for replay")
    started_at: datetime = Field(..., description="When replay started")
    ended_at: datetime = Field(..., description="When replay ended")

    # Results
    success: bool = Field(..., description="Whether replay matched original")
    differences: list[ReplayDifference] = Field(
        default_factory=list,
        description="List of differences found",
    )
    replay_spans: list[ExecutionSpan] = Field(
        default_factory=list,
        description="Spans from the replay execution",
    )

    # Statistics
    spans_compared: int = Field(default=0, description="Number of spans compared")
    spans_matched: int = Field(default=0, description="Number of spans that matched")

    @property
    def match_rate(self) -> float:
        """Percentage of spans that matched."""
        if self.spans_compared == 0:
            return 0.0
        return self.spans_matched / self.spans_compared

    @property
    def duration_ms(self) -> float:
        """Total replay duration in milliseconds."""
        return (self.ended_at - self.started_at).total_seconds() * 1000


class ExecutionTrace(BaseModel):
    """
    Complete trace of one or more tool executions for replay.

    ExecutionTrace captures everything needed to:
    - Reproduce an execution exactly
    - Compare new executions against a baseline
    - Generate training data

    The trace includes:
    - All tool calls made
    - The execution context
    - All spans (execution records)
    - Environment snapshot
    - Random seed (if seeded)

    Example:
        >>> # Create a trace
        >>> trace = ExecutionTrace(
        ...     context=ExecutionContext(user_id="test-user"),
        ... )
        >>>
        >>> # Add spans as execution progresses
        >>> trace.add_span(span1)
        >>> trace.add_span(span2)
        >>>
        >>> # Save for later replay
        >>> trace_json = trace.model_dump_json()
        >>>
        >>> # Later: replay
        >>> loaded = ExecutionTrace.model_validate_json(trace_json)
        >>> result = await loaded.replay(executor)

    For deterministic replay, ensure:
    - random_seed is set
    - Tools are marked as deterministic
    - No external dependencies changed
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    trace_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this trace",
    )
    name: str = Field(
        default="",
        description="Optional name for this trace (for organization)",
    )
    description: str = Field(
        default="",
        description="Optional description of what this trace represents",
    )

    # ------------------------------------------------------------------ #
    # Timestamps
    # ------------------------------------------------------------------ #
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the trace was created",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When execution started",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="When execution ended",
    )

    # ------------------------------------------------------------------ #
    # Input capture
    # ------------------------------------------------------------------ #
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Original tool calls that were executed",
    )
    context: ExecutionContext | None = Field(
        default=None,
        description="Execution context used",
    )

    # ------------------------------------------------------------------ #
    # Execution spans (in order)
    # ------------------------------------------------------------------ #
    spans: list[ExecutionSpan] = Field(
        default_factory=list,
        description="Ordered list of execution spans",
    )

    # ------------------------------------------------------------------ #
    # Replay support
    # ------------------------------------------------------------------ #
    random_seed: int | None = Field(
        default=None,
        description="Random seed used (if seeded execution)",
    )
    environment_snapshot: dict[str, str] = Field(
        default_factory=dict,
        description="Relevant environment variables at execution time",
    )
    deterministic: bool = Field(
        default=False,
        description="Whether all tools in this trace are deterministic",
    )

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #
    @property
    def duration_ms(self) -> float:
        """Total trace duration in milliseconds."""
        if self.started_at is None or self.ended_at is None:
            return sum(s.duration_ms for s in self.spans)
        return (self.ended_at - self.started_at).total_seconds() * 1000

    @property
    def span_count(self) -> int:
        """Number of spans in the trace."""
        return len(self.spans)

    @property
    def success_count(self) -> int:
        """Number of successful spans."""
        return sum(1 for s in self.spans if s.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed spans."""
        return sum(1 for s in self.spans if s.outcome == ExecutionOutcome.FAILED)

    @property
    def blocked_count(self) -> int:
        """Number of blocked spans."""
        return sum(1 for s in self.spans if s.blocked)

    @property
    def tools_used(self) -> list[str]:
        """Unique tools used in this trace."""
        return list(dict.fromkeys(s.full_tool_name for s in self.spans))

    @property
    def content_hash(self) -> str:
        """Hash of trace contents for comparison."""
        payload = {
            "tool_calls": [
                {"tool": tc.tool, "namespace": tc.namespace, "arguments": tc.arguments} for tc in self.tool_calls
            ],
            "spans": [
                {
                    "tool": s.tool_name,
                    "arguments": s.arguments,
                    "outcome": s.outcome.value,
                    "result": str(s.result) if s.result is not None else None,
                }
                for s in self.spans
            ],
        }
        json_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode(), usedforsecurity=False).hexdigest()[:16]

    # ------------------------------------------------------------------ #
    # Builder methods
    # ------------------------------------------------------------------ #
    def start(self) -> Self:
        """Mark the trace as started."""
        self.started_at = datetime.now(UTC)
        return self

    def end(self) -> Self:
        """Mark the trace as ended."""
        self.ended_at = datetime.now(UTC)
        return self

    def add_tool_call(self, tool_call: ToolCall) -> Self:
        """Add a tool call to the trace."""
        self.tool_calls.append(tool_call)
        return self

    def add_span(self, span: ExecutionSpan) -> Self:
        """Add an execution span to the trace."""
        self.spans.append(span)
        return self

    def with_context(self, context: ExecutionContext) -> Self:
        """Set the execution context."""
        self.context = context
        return self

    def with_seed(self, seed: int) -> Self:
        """Set random seed for reproducibility."""
        self.random_seed = seed
        self.deterministic = True
        return self

    def capture_environment(self, var_names: list[str] | None = None) -> Self:
        """
        Capture environment variables for replay.

        Args:
            var_names: Specific variables to capture. If None, captures common ones.
        """
        if var_names is None:
            # Default: capture common relevant vars
            var_names = [
                "PATH",
                "PYTHONPATH",
                "HOME",
                "USER",
                "TZ",
                "LANG",
                "LC_ALL",
            ]

        for name in var_names:
            value = os.environ.get(name)
            if value is not None:
                self.environment_snapshot[name] = value

        return self

    def with_tag(self, tag: str) -> Self:
        """Add a tag to the trace."""
        if tag not in self.tags:
            self.tags.append(tag)
        return self

    def with_metadata(self, **kwargs: Any) -> Self:
        """Add metadata to the trace."""
        self.metadata.update(kwargs)
        return self

    # ------------------------------------------------------------------ #
    # Replay
    # ------------------------------------------------------------------ #
    async def replay(
        self,
        executor: Any,  # ExecutionStrategy
        mode: ReplayMode = ReplayMode.STRICT,
    ) -> ReplayResult:
        """
        Replay this trace using the given executor.

        Args:
            executor: ExecutionStrategy to use for replay
            mode: How strictly to compare results

        Returns:
            ReplayResult with comparison details
        """
        started_at = datetime.now(UTC)
        replay_trace_id = str(uuid4())
        replay_spans: list[ExecutionSpan] = []
        differences: list[ReplayDifference] = []

        # Set random seed if we have one
        if self.random_seed is not None:
            import random

            random.seed(self.random_seed)

        # Re-execute each tool call
        for i, tool_call in enumerate(self.tool_calls):
            # Execute
            results = await executor.run([tool_call])

            # Get the span (assuming one result per call)
            if results:
                replay_span = results[0]
                replay_spans.append(replay_span)

                # Compare with original
                if i < len(self.spans):
                    original_span = self.spans[i]
                    span_diffs = self._compare_spans(i, original_span, replay_span, mode)
                    differences.extend(span_diffs)

        ended_at = datetime.now(UTC)

        # Calculate match statistics
        spans_matched = len(self.spans) - len([d for d in differences if d.severity == "error"])

        success = len([d for d in differences if d.severity == "error"]) == 0

        return ReplayResult(
            original_trace_id=self.trace_id,
            replay_trace_id=replay_trace_id,
            mode=mode,
            started_at=started_at,
            ended_at=ended_at,
            success=success,
            differences=differences,
            replay_spans=replay_spans,
            spans_compared=len(self.spans),
            spans_matched=spans_matched,
        )

    def _compare_spans(
        self,
        index: int,
        original: ExecutionSpan,
        replay: ExecutionSpan,
        mode: ReplayMode,
    ) -> list[ReplayDifference]:
        """Compare two spans and return differences."""
        differences: list[ReplayDifference] = []

        # Always compare outcome
        if original.outcome != replay.outcome:
            differences.append(
                ReplayDifference(
                    span_index=index,
                    tool_name=original.tool_name,
                    field="outcome",
                    expected=original.outcome.value,
                    actual=replay.outcome.value,
                    severity="error",
                )
            )

        # Compare result for deterministic tools
        should_compare = original.deterministic or mode == ReplayMode.STRICT
        if should_compare and str(original.result) != str(replay.result):
            severity = "error" if original.deterministic else "warning"
            differences.append(
                ReplayDifference(
                    span_index=index,
                    tool_name=original.tool_name,
                    field="result",
                    expected=original.result,
                    actual=replay.result,
                    severity=severity,
                )
            )

        # Compare guard verdicts
        if original.final_verdict != replay.final_verdict:
            differences.append(
                ReplayDifference(
                    span_index=index,
                    tool_name=original.tool_name,
                    field="final_verdict",
                    expected=original.final_verdict,
                    actual=replay.final_verdict,
                    severity="error",
                )
            )

        return differences

    # ------------------------------------------------------------------ #
    # Export / Import
    # ------------------------------------------------------------------ #
    def to_jsonl(self) -> str:
        """Export trace as JSON Lines format (one span per line)."""
        lines = [json.dumps({"trace": self.model_dump(exclude={"spans"})}, default=str)]
        for span in self.spans:
            lines.append(json.dumps({"span": span.model_dump()}, default=str))
        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, jsonl: str) -> ExecutionTrace:
        """Import trace from JSON Lines format."""
        lines = jsonl.strip().split("\n")
        trace_data = json.loads(lines[0])["trace"]
        trace = cls.model_validate(trace_data)

        for line in lines[1:]:
            span_data = json.loads(line)["span"]
            span = ExecutionSpan.model_validate(span_data)
            trace.add_span(span)

        return trace

    def to_summary(self) -> dict[str, Any]:
        """Export a summary of the trace (without full span details)."""
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "span_count": self.span_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "blocked_count": self.blocked_count,
            "tools_used": self.tools_used,
            "deterministic": self.deterministic,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


class TraceBuilder:
    """
    Builder for constructing ExecutionTrace incrementally.

    Example:
        >>> builder = TraceBuilder(name="test-trace")
        >>> builder.start()
        >>> builder.add_span(span1)
        >>> builder.add_span(span2)
        >>> trace = builder.build()
    """

    def __init__(
        self,
        name: str = "",
        context: ExecutionContext | None = None,
        seed: int | None = None,
    ):
        self._trace = ExecutionTrace(
            name=name,
            context=context,
            random_seed=seed,
            deterministic=seed is not None,
        )

    def start(self) -> TraceBuilder:
        """Mark trace as started."""
        self._trace.start()
        return self

    def add_tool_call(self, tool_call: ToolCall) -> TraceBuilder:
        """Add a tool call."""
        self._trace.add_tool_call(tool_call)
        return self

    def add_span(self, span: ExecutionSpan) -> TraceBuilder:
        """Add a span."""
        self._trace.add_span(span)
        return self

    def with_tag(self, tag: str) -> TraceBuilder:
        """Add a tag."""
        self._trace.with_tag(tag)
        return self

    def with_metadata(self, **kwargs: Any) -> TraceBuilder:
        """Add metadata."""
        self._trace.with_metadata(**kwargs)
        return self

    def capture_environment(self, var_names: list[str] | None = None) -> TraceBuilder:
        """Capture environment variables."""
        self._trace.capture_environment(var_names)
        return self

    def build(self) -> ExecutionTrace:
        """Build the final trace."""
        self._trace.end()
        return self._trace
