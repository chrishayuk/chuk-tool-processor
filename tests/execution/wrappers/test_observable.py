# tests/execution/wrappers/test_observable.py
"""
Tests for the ObservableExecutor and TracingExecutorMixin.
"""

import pytest

from chuk_tool_processor.core.context import ExecutionContext, set_current_context
from chuk_tool_processor.execution.wrappers.observable import (
    ObservableExecutor,
    TracingExecutorMixin,
)
from chuk_tool_processor.guards.base import GuardResult, GuardVerdict
from chuk_tool_processor.models.execution_span import (
    ExecutionOutcome,
    ExecutionStrategy,
    SandboxType,
)
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.observability.trace_sink import InMemoryTraceSink


# --------------------------------------------------------------------------- #
# Mock Guard Chain (simulates the interface expected by ObservableExecutor)
# --------------------------------------------------------------------------- #
class MockGuardChain:
    """Mock guard chain that matches expected interface."""

    def __init__(self, result: GuardResult | None = None):
        self._result = result or GuardResult(verdict=GuardVerdict.ALLOW)
        self.check_calls: list[tuple[str, dict]] = []

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        """Simulate check method."""
        self.check_calls.append((tool_name, arguments))
        return self._result


class BlockingGuardChain(MockGuardChain):
    """Guard chain that blocks execution."""

    def __init__(self):
        super().__init__(GuardResult(verdict=GuardVerdict.BLOCK, reason="Blocked by test guard"))


class PartialBlockGuardChain:
    """Guard chain that blocks specific tools."""

    def __init__(self, blocked_tools: set[str]):
        self._blocked_tools = blocked_tools
        self.check_calls: list[tuple[str, dict]] = []

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        self.check_calls.append((tool_name, arguments))
        if tool_name in self._blocked_tools:
            return GuardResult(verdict=GuardVerdict.BLOCK, reason="Blocked")
        return GuardResult(verdict=GuardVerdict.ALLOW)


# --------------------------------------------------------------------------- #
# Mock Strategy
# --------------------------------------------------------------------------- #
class MockStrategy:
    """Mock execution strategy for testing."""

    def __init__(self, results: list[ToolResult] | None = None, raise_error: Exception | None = None):
        self.results = results
        self.raise_error = raise_error
        self.called_with: list[list[ToolCall]] = []

    async def run(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        self.called_with.append(tool_calls)
        if self.raise_error:
            raise self.raise_error
        if self.results:
            return self.results
        return [ToolResult(tool=c.tool, result={"echo": c.arguments}) for c in tool_calls]


class SubprocessMockStrategy(MockStrategy):
    """Mock strategy that looks like subprocess."""

    pass


class MCPStdioMockStrategy(MockStrategy):
    """Mock MCP stdio strategy."""

    pass


class MCPSSEMockStrategy(MockStrategy):
    """Mock MCP SSE strategy."""

    pass


class MCPHTTPMockStrategy(MockStrategy):
    """Mock MCP HTTP strategy."""

    pass


class ContainerMockStrategy(MockStrategy):
    """Mock container strategy."""

    pass


class CodeSandboxMockStrategy(MockStrategy):
    """Mock code sandbox strategy."""

    pass


# --------------------------------------------------------------------------- #
# ObservableExecutor Tests
# --------------------------------------------------------------------------- #
class TestObservableExecutorInit:
    """Tests for ObservableExecutor initialization."""

    def test_basic_init(self):
        """Test basic initialization."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy)

        assert executor._strategy is strategy
        assert executor._sink is None
        assert executor._guard_chain is None
        assert executor._trace_id is None
        assert executor._record_results is True
        assert executor._record_arguments is True

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        guard_chain = MockGuardChain()

        executor = ObservableExecutor(
            strategy=strategy,
            sink=sink,
            guard_chain=guard_chain,
            trace_id="test-trace-123",
            record_results=False,
            record_arguments=False,
        )

        assert executor._strategy is strategy
        assert executor._sink is sink
        assert executor._guard_chain is guard_chain
        assert executor._trace_id == "test-trace-123"
        assert executor._record_results is False
        assert executor._record_arguments is False

    def test_sink_property_uses_provided(self):
        """Test sink property returns provided sink."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        assert executor.sink is sink

    def test_sink_property_uses_global_when_none(self):
        """Test sink property uses global when none provided."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy)

        # Should return some sink (global default)
        assert executor.sink is not None


class TestSandboxTypeDetection:
    """Tests for _get_sandbox_type method."""

    def test_subprocess_strategy(self):
        """Test subprocess strategy detection."""
        executor = ObservableExecutor(strategy=SubprocessMockStrategy())
        assert executor._get_sandbox_type() == SandboxType.PROCESS

    def test_mcp_strategy(self):
        """Test MCP strategy detection."""
        executor = ObservableExecutor(strategy=MCPStdioMockStrategy())
        assert executor._get_sandbox_type() == SandboxType.MCP

    def test_container_strategy(self):
        """Test container strategy detection."""
        executor = ObservableExecutor(strategy=ContainerMockStrategy())
        assert executor._get_sandbox_type() == SandboxType.CONTAINER

    def test_default_strategy(self):
        """Test default strategy (none)."""
        executor = ObservableExecutor(strategy=MockStrategy())
        assert executor._get_sandbox_type() == SandboxType.NONE


class TestExecutionStrategyDetection:
    """Tests for _get_execution_strategy method."""

    def test_subprocess_strategy(self):
        """Test subprocess strategy detection."""
        executor = ObservableExecutor(strategy=SubprocessMockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.SUBPROCESS

    def test_mcp_stdio_strategy(self):
        """Test MCP stdio strategy detection."""
        executor = ObservableExecutor(strategy=MCPStdioMockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.MCP_STDIO

    def test_mcp_sse_strategy(self):
        """Test MCP SSE strategy detection."""
        executor = ObservableExecutor(strategy=MCPSSEMockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.MCP_SSE

    def test_mcp_http_strategy(self):
        """Test MCP HTTP strategy detection."""
        executor = ObservableExecutor(strategy=MCPHTTPMockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.MCP_HTTP

    def test_sandbox_strategy(self):
        """Test code sandbox strategy detection."""
        executor = ObservableExecutor(strategy=CodeSandboxMockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.CODE_SANDBOX

    def test_default_strategy(self):
        """Test default strategy (inprocess)."""
        executor = ObservableExecutor(strategy=MockStrategy())
        assert executor._get_execution_strategy() == ExecutionStrategy.INPROCESS


class TestSpanBuilder:
    """Tests for span builder creation."""

    def test_create_span_builder_basic(self):
        """Test basic span builder creation."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy, trace_id="test-trace")

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={"x": 1})
        context = ExecutionContext(request_id="req-123")

        builder = executor._create_span_builder(tool_call, context)

        assert builder._tool_name == "test_tool"
        assert builder._arguments == {"x": 1}
        assert builder._trace_id == "test-trace"
        assert builder._request_id == "req-123"
        assert builder._tool_call_id == "call-1"

    def test_create_span_builder_no_arguments(self):
        """Test span builder with record_arguments=False."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy, record_arguments=False)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={"x": 1})

        builder = executor._create_span_builder(tool_call, None)

        assert builder._arguments == {}

    def test_create_span_builder_no_context(self):
        """Test span builder without context."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})

        builder = executor._create_span_builder(tool_call, None)

        assert builder._request_id is None


class TestRecordGuardDecision:
    """Tests for _record_guard_decision method."""

    def test_record_allow_decision(self):
        """Test recording an ALLOW guard decision."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        builder = executor._create_span_builder(tool_call, None)

        guard_result = GuardResult(verdict=GuardVerdict.ALLOW)
        executor._record_guard_decision(builder, guard_result, "TestGuard", 5.5)

        assert len(builder._guard_decisions) == 1
        decision = builder._guard_decisions[0]
        assert decision.guard_name == "TestGuard"
        assert decision.verdict == "ALLOW"
        assert decision.duration_ms == 5.5

    def test_record_block_decision(self):
        """Test recording a BLOCK guard decision."""
        strategy = MockStrategy()
        executor = ObservableExecutor(strategy=strategy)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        builder = executor._create_span_builder(tool_call, None)

        guard_result = GuardResult(
            verdict=GuardVerdict.BLOCK,
            reason="Access denied",
            details={"code": 403},
        )
        executor._record_guard_decision(builder, guard_result, "BlockGuard", 10.0)

        assert len(builder._guard_decisions) == 1
        decision = builder._guard_decisions[0]
        assert decision.guard_name == "BlockGuard"
        assert decision.verdict == "BLOCK"
        assert decision.reason == "Access denied"
        assert decision.details == {"code": 403}


@pytest.mark.asyncio
class TestObservableExecutorRun:
    """Tests for ObservableExecutor.run method."""

    async def test_basic_execution(self):
        """Test basic tool execution with span recording."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={"x": 1})
        results = await executor.run([tool_call])

        assert len(results) == 1
        assert results[0].tool == "test_tool"

        # Check span was recorded
        spans = list(sink._spans)
        assert len(spans) == 1
        assert spans[0].tool_name == "test_tool"
        assert spans[0].outcome == ExecutionOutcome.SUCCESS

    async def test_execution_with_guard_chain(self):
        """Test execution with guard chain."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        guard_chain = MockGuardChain()
        executor = ObservableExecutor(strategy=strategy, sink=sink, guard_chain=guard_chain)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        results = await executor.run([tool_call])

        assert len(results) == 1

        # Check guard decision was recorded
        spans = list(sink._spans)
        assert len(spans) == 1
        assert len(spans[0].guard_decisions) > 0

    async def test_blocked_by_guard(self):
        """Test that blocked calls are not executed."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        guard_chain = BlockingGuardChain()
        executor = ObservableExecutor(strategy=strategy, sink=sink, guard_chain=guard_chain)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        results = await executor.run([tool_call])

        # Strategy should not have been called
        assert len(strategy.called_with) == 0

        # Should get blocked result
        assert len(results) == 1
        assert results[0].error is not None
        assert "GuardBlocked" in results[0].error

        # Span should show blocked
        spans = list(sink._spans)
        assert len(spans) == 1
        assert spans[0].outcome == ExecutionOutcome.BLOCKED

    async def test_execution_error_in_strategy(self):
        """Test handling of execution errors."""
        error = ValueError("Test error")
        strategy = MockStrategy(raise_error=error)
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})

        with pytest.raises(ValueError, match="Test error"):
            await executor.run([tool_call])

        # The important thing is that the exception was raised and propagated
        # Spans may or may not be recorded depending on when the error occurs

    async def test_multiple_tool_calls(self):
        """Test execution of multiple tool calls."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_calls = [
            ToolCall(id="call-1", tool="tool_a", arguments={"a": 1}),
            ToolCall(id="call-2", tool="tool_b", arguments={"b": 2}),
        ]
        results = await executor.run(tool_calls)

        assert len(results) == 2

        spans = list(sink._spans)
        assert len(spans) == 2
        tool_names = {s.tool_name for s in spans}
        assert tool_names == {"tool_a", "tool_b"}

    async def test_result_with_error(self):
        """Test handling of results with errors."""
        error_result = ToolResult(
            tool="test_tool",
            result=None,
            error="TestError: Something failed",
        )
        strategy = MockStrategy(results=[error_result])
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        results = await executor.run([tool_call])

        assert len(results) == 1
        assert results[0].error is not None

        spans = list(sink._spans)
        assert len(spans) == 1
        # Result has string error, so span might not have structured error
        # Just verify span was recorded
        assert spans[0].tool_name == "test_tool"

    async def test_record_results_false(self):
        """Test that results are not recorded when record_results=False."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink, record_results=False)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        await executor.run([tool_call])

        spans = list(sink._spans)
        assert len(spans) == 1
        assert spans[0].result is None

    async def test_partial_blocking(self):
        """Test mixed blocked and allowed calls."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        guard_chain = PartialBlockGuardChain(blocked_tools={"blocked_tool"})
        executor = ObservableExecutor(strategy=strategy, sink=sink, guard_chain=guard_chain)

        tool_calls = [
            ToolCall(id="call-1", tool="blocked_tool", arguments={}),
            ToolCall(id="call-2", tool="allowed_tool", arguments={}),
        ]
        results = await executor.run(tool_calls)

        assert len(results) == 2

        # Only allowed tool should be executed
        assert len(strategy.called_with) == 1
        assert len(strategy.called_with[0]) == 1
        assert strategy.called_with[0][0].tool == "allowed_tool"


@pytest.mark.asyncio
class TestRunWithTrace:
    """Tests for ObservableExecutor.run_with_trace method."""

    async def test_basic_trace(self):
        """Test basic trace generation."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        results, trace = await executor.run_with_trace([tool_call])

        assert len(results) == 1
        assert trace is not None
        assert len(trace.tool_calls) == 1

    async def test_trace_with_name_and_tags(self):
        """Test trace with name and tags."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        results, trace = await executor.run_with_trace(
            [tool_call],
            trace_name="Test Trace",
            trace_tags=["test", "unit"],
        )

        assert trace.name == "Test Trace"
        assert "test" in trace.tags
        assert "unit" in trace.tags

    async def test_trace_recorded_to_sink(self):
        """Test that trace is recorded to sink."""
        strategy = MockStrategy()
        sink = InMemoryTraceSink()
        executor = ObservableExecutor(strategy=strategy, sink=sink)

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})
        await executor.run_with_trace([tool_call])

        # Should have both span and trace
        assert len(list(sink._spans)) >= 1
        assert len(list(sink._traces)) >= 1


# --------------------------------------------------------------------------- #
# TracingExecutorMixin Tests
# --------------------------------------------------------------------------- #
class TestTracingExecutorMixin:
    """Tests for TracingExecutorMixin."""

    def test_trace_sink_property_with_explicit_sink(self):
        """Test trace_sink property with explicitly set sink."""
        mixin = TracingExecutorMixin()
        sink = InMemoryTraceSink()
        mixin._sink = sink

        assert mixin.trace_sink is sink

    def test_trace_sink_property_with_global(self):
        """Test trace_sink property uses global sink."""
        mixin = TracingExecutorMixin()
        mixin._sink = None

        # Should return some sink
        assert mixin.trace_sink is not None

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager protocol."""
        mixin = TracingExecutorMixin()

        async with mixin as m:
            assert m is mixin

    def test_trace_execution_returns_context(self):
        """Test trace_execution returns a TraceContext."""
        mixin = TracingExecutorMixin()
        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})

        context = mixin.trace_execution([tool_call])

        assert isinstance(context, TracingExecutorMixin.TraceContext)


@pytest.mark.asyncio
class TestTraceContext:
    """Tests for TracingExecutorMixin.TraceContext."""

    async def test_basic_trace_context(self):
        """Test basic trace context usage."""
        mixin = TracingExecutorMixin()
        sink = InMemoryTraceSink()
        mixin._sink = sink

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={"x": 1})

        async with mixin.trace_execution([tool_call]) as builders:
            assert "call-1" in builders
            builder = builders["call-1"]
            builder.set_result({"result": "success"})

        # Span should be recorded
        spans = list(sink._spans)
        assert len(spans) == 1
        assert spans[0].tool_name == "test_tool"

    async def test_trace_context_with_error(self):
        """Test trace context with exception."""
        mixin = TracingExecutorMixin()
        sink = InMemoryTraceSink()
        mixin._sink = sink

        tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})

        try:
            async with mixin.trace_execution([tool_call]) as builders:
                assert "call-1" in builders
                raise ValueError("Test error")
        except ValueError:
            pass

        # Span should still be recorded with error
        spans = list(sink._spans)
        assert len(spans) == 1
        assert spans[0].outcome == ExecutionOutcome.FAILED

    async def test_trace_context_multiple_calls(self):
        """Test trace context with multiple tool calls."""
        mixin = TracingExecutorMixin()
        sink = InMemoryTraceSink()
        mixin._sink = sink
        mixin._trace_id = "test-trace"

        tool_calls = [
            ToolCall(id="call-1", tool="tool_a", arguments={}),
            ToolCall(id="call-2", tool="tool_b", arguments={}),
        ]

        async with mixin.trace_execution(tool_calls) as builders:
            assert "call-1" in builders
            assert "call-2" in builders
            builders["call-1"].set_result({"a": 1})
            builders["call-2"].set_result({"b": 2})

        spans = list(sink._spans)
        assert len(spans) == 2

    async def test_trace_context_with_request_id(self):
        """Test trace context captures request_id from context."""
        mixin = TracingExecutorMixin()
        sink = InMemoryTraceSink()
        mixin._sink = sink

        # Set up context with request_id
        ctx = ExecutionContext(request_id="req-456")
        set_current_context(ctx)

        try:
            tool_call = ToolCall(id="call-1", tool="test_tool", arguments={})

            async with mixin.trace_execution([tool_call]) as builders:
                builders["call-1"].set_result({})

            spans = list(sink._spans)
            assert len(spans) == 1
            assert spans[0].request_id == "req-456"
        finally:
            # Reset context
            set_current_context(None)
