# chuk_tool_processor/execution/wrappers/observable.py
"""
ObservableExecutor: Execution wrapper that produces ExecutionSpans.

This wrapper intercepts tool execution to:
- Build ExecutionSpan records
- Record to TraceSink
- Capture guard decisions
- Track timing and outcomes

This is the integration point between execution and observability.

Example:
    >>> sink = InMemoryTraceSink()
    >>> executor = ObservableExecutor(
    ...     strategy=InProcessStrategy(registry),
    ...     sink=sink,
    ... )
    >>> results = await executor.run([tool_call])
    >>> # Span automatically recorded to sink
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from chuk_tool_processor.core.context import ExecutionContext, get_current_context
from chuk_tool_processor.guards.base import GuardResult
from chuk_tool_processor.models.execution_span import (
    ErrorInfo,
    ExecutionStrategy,
    GuardDecision,
    SandboxType,
    SpanBuilder,
)
from chuk_tool_processor.models.execution_trace import ExecutionTrace, TraceBuilder
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.observability.trace_sink import BaseTraceSink, get_trace_sink

if TYPE_CHECKING:
    from chuk_tool_processor.execution.strategies.interface import ExecutionStrategy as StrategyInterface
    from chuk_tool_processor.guards.chain import GuardChain


class ObservableExecutor:
    """
    Execution wrapper that produces ExecutionSpans for observability.

    This wrapper sits between the caller and the underlying execution
    strategy, intercepting calls to:

    1. Build span data before execution
    2. Record guard decisions
    3. Capture timing
    4. Record outcome (success/failure/blocked)
    5. Write spans to TraceSink

    Example:
        >>> from chuk_tool_processor.observability.trace_sink import InMemoryTraceSink
        >>> sink = InMemoryTraceSink()
        >>> executor = ObservableExecutor(
        ...     strategy=InProcessStrategy(registry),
        ...     sink=sink,
        ...     guard_chain=guard_chain,
        ... )
        >>>
        >>> results = await executor.run([tool_call])
        >>>
        >>> # Query recorded spans
        >>> async for span in sink.query_spans():
        ...     print(f"{span.tool_name}: {span.outcome}")
    """

    def __init__(
        self,
        strategy: StrategyInterface,
        sink: BaseTraceSink | None = None,
        guard_chain: GuardChain | None = None,
        trace_id: str | None = None,
        record_results: bool = True,
        record_arguments: bool = True,
    ):
        """
        Initialize observable executor.

        Args:
            strategy: Underlying execution strategy
            sink: TraceSink to record spans to (uses global if None)
            guard_chain: Optional guard chain for recording guard decisions
            trace_id: Trace ID to use for all spans (generates new if None)
            record_results: Whether to record result values in spans
            record_arguments: Whether to record argument values in spans
        """
        self._strategy = strategy
        self._sink = sink
        self._guard_chain = guard_chain
        self._trace_id = trace_id
        self._record_results = record_results
        self._record_arguments = record_arguments

    @property
    def sink(self) -> BaseTraceSink:
        """Get the trace sink (global if not explicitly set)."""
        return self._sink or get_trace_sink()

    def _get_sandbox_type(self) -> SandboxType:
        """Determine sandbox type from strategy."""
        strategy_name = type(self._strategy).__name__.lower()

        if "subprocess" in strategy_name:
            return SandboxType.PROCESS
        elif "mcp" in strategy_name:
            return SandboxType.MCP
        elif "container" in strategy_name:
            return SandboxType.CONTAINER
        else:
            return SandboxType.NONE

    def _get_execution_strategy(self) -> ExecutionStrategy:
        """Determine execution strategy enum from strategy instance."""
        strategy_name = type(self._strategy).__name__.lower()

        if "subprocess" in strategy_name:
            return ExecutionStrategy.SUBPROCESS
        elif "mcp" in strategy_name:
            if "sse" in strategy_name:
                return ExecutionStrategy.MCP_SSE
            elif "http" in strategy_name:
                return ExecutionStrategy.MCP_HTTP
            else:
                return ExecutionStrategy.MCP_STDIO
        elif "sandbox" in strategy_name:
            return ExecutionStrategy.CODE_SANDBOX
        else:
            return ExecutionStrategy.INPROCESS

    def _create_span_builder(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None,
    ) -> SpanBuilder:
        """Create a span builder for a tool call."""
        return SpanBuilder(
            tool_name=tool_call.tool,
            arguments=tool_call.arguments if self._record_arguments else {},
            namespace=tool_call.namespace,
            trace_id=self._trace_id,
            request_id=context.request_id if context else None,
            tool_call_id=tool_call.id,
        )

    def _record_guard_decision(
        self,
        builder: SpanBuilder,
        guard_result: GuardResult,
        guard_name: str,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a guard decision in the span builder."""
        decision = GuardDecision(
            guard_name=guard_name,
            guard_class=type(guard_result).__module__,
            verdict=guard_result.verdict.value.upper(),
            reason=guard_result.reason,
            details=guard_result.details,
            duration_ms=duration_ms,
            repaired_args=guard_result.repaired_args,
        )
        builder.add_guard_decision(decision)

    async def run(
        self,
        tool_calls: list[ToolCall],
        context: ExecutionContext | None = None,
    ) -> list[ToolResult]:
        """
        Execute tool calls with span recording.

        Args:
            tool_calls: List of tool calls to execute
            context: Execution context (uses current if None)

        Returns:
            List of tool results
        """
        context = context or get_current_context()

        # Create span builders for each call
        builders: dict[str, SpanBuilder] = {}
        for call in tool_calls:
            builder = self._create_span_builder(call, context)
            builder.set_sandbox(self._get_sandbox_type())
            builder.set_strategy(self._get_execution_strategy())
            builders[call.id] = builder

        # Run guard checks if we have a guard chain
        blocked_calls: set[str] = set()
        if self._guard_chain:
            for call in tool_calls:
                builder = builders[call.id]
                builder.start_guard_phase()

                start = datetime.now(UTC)
                result = self._guard_chain.check(call.tool, call.arguments)
                duration = (datetime.now(UTC) - start).total_seconds() * 1000

                # Record each guard's decision
                self._record_guard_decision(builder, result, "GuardChain", duration)
                builder.end_guard_phase()

                if result.blocked:
                    blocked_calls.add(call.id)
                    builder.set_blocked()

        # Filter out blocked calls
        executable_calls = [c for c in tool_calls if c.id not in blocked_calls]
        results: list[ToolResult] = []

        # Execute non-blocked calls
        if executable_calls:
            for call in executable_calls:
                builders[call.id].set_started()

            try:
                strategy_results = await self._strategy.run(executable_calls)

                # Match results to calls and update builders
                for call, result in zip(executable_calls, strategy_results, strict=False):
                    builder = builders[call.id]

                    if result.error:
                        # Handle both string errors and structured error_info
                        if result.error_info:
                            builder.set_error(
                                ErrorInfo(
                                    error_type=result.error_info.code.value if result.error_info.code else "Error",
                                    message=result.error_info.message,
                                    retryable=result.error_info.retryable,
                                )
                            )
                        else:
                            builder.set_error(
                                ErrorInfo(
                                    error_type="Error",
                                    message=str(result.error),
                                    retryable=False,
                                )
                            )
                    else:
                        builder.set_result(result.result if self._record_results else None)

                results.extend(strategy_results)

            except Exception as e:
                # Execution failed entirely
                for call in executable_calls:
                    builders[call.id].set_error(e)

                raise

        # Build and record all spans
        for call in tool_calls:
            span = builders[call.id].build()
            await self.sink.record_span(span)

        # Add blocked results
        for call in tool_calls:
            if call.id in blocked_calls:
                blocking_guard = builders[call.id]._guard_decisions[-1] if builders[call.id]._guard_decisions else None
                reason = blocking_guard.reason if blocking_guard else "Blocked by guard"
                results.append(
                    ToolResult(
                        tool=call.tool,
                        result=None,
                        error=f"GuardBlocked: {reason}",
                    )
                )

        return results

    async def run_with_trace(
        self,
        tool_calls: list[ToolCall],
        context: ExecutionContext | None = None,
        trace_name: str = "",
        trace_tags: list[str] | None = None,
    ) -> tuple[list[ToolResult], ExecutionTrace]:
        """
        Execute tool calls and return both results and complete trace.

        This is useful for:
        - Capturing traces for replay
        - Debugging complex executions
        - Training data generation

        Args:
            tool_calls: List of tool calls to execute
            context: Execution context
            trace_name: Name for the trace
            trace_tags: Tags for the trace

        Returns:
            Tuple of (results, trace)
        """
        context = context or get_current_context()

        # Build trace
        trace_builder = TraceBuilder(name=trace_name, context=context)
        trace_builder.start()
        trace_builder.capture_environment()

        for tag in trace_tags or []:
            trace_builder.with_tag(tag)

        for call in tool_calls:
            trace_builder.add_tool_call(call)

        # Execute
        results = await self.run(tool_calls, context)

        # Collect spans for the trace
        async for span in self.sink.query_spans():
            if any(span.tool_call_id == call.id for call in tool_calls):
                trace_builder.add_span(span)

        trace = trace_builder.build()

        # Record complete trace
        await self.sink.record_trace(trace)

        return results, trace


class TracingExecutorMixin:
    """
    Mixin that adds tracing to any execution strategy.

    Use this to add observability to custom execution strategies.

    Example:
        >>> class MyStrategy(TracingExecutorMixin, BaseStrategy):
        ...     async def run(self, tool_calls):
        ...         async with self.trace_execution(tool_calls) as builders:
        ...             results = await self._execute(tool_calls)
        ...             for call, result in zip(tool_calls, results):
        ...                 builders[call.id].set_result(result.result)
        ...         return results
    """

    _sink: BaseTraceSink | None = None
    _trace_id: str | None = None

    @property
    def trace_sink(self) -> BaseTraceSink:
        """Get trace sink."""
        return self._sink or get_trace_sink()

    async def __aenter__(self):
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        pass

    class TraceContext:
        """Context manager for tracing a batch of executions."""

        def __init__(
            self,
            mixin: TracingExecutorMixin,
            tool_calls: list[ToolCall],
        ):
            self._mixin = mixin
            self._tool_calls = tool_calls
            self._builders: dict[str, SpanBuilder] = {}

        async def __aenter__(self) -> dict[str, SpanBuilder]:
            """Start tracing."""
            context = get_current_context()

            for call in self._tool_calls:
                builder = SpanBuilder(
                    tool_name=call.tool,
                    arguments=call.arguments,
                    namespace=call.namespace,
                    trace_id=self._mixin._trace_id,
                    request_id=context.request_id if context else None,
                    tool_call_id=call.id,
                )
                builder.set_started()
                self._builders[call.id] = builder

            return self._builders

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            """End tracing and record spans."""
            for _call_id, builder in self._builders.items():
                if exc_type is not None:
                    builder.set_error(exc_val)

                span = builder.build()
                await self._mixin.trace_sink.record_span(span)

    def trace_execution(self, tool_calls: list[ToolCall]) -> TraceContext:
        """
        Create a trace context for a batch of executions.

        Example:
            >>> async with self.trace_execution(calls) as builders:
            ...     results = await self._do_execute(calls)
            ...     for call, result in zip(calls, results):
            ...         builders[call.id].set_result(result)
        """
        return self.TraceContext(self, tool_calls)
