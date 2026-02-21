# tests/models/test_execution_span.py
"""
Tests for ExecutionSpan and SpanBuilder.
"""

from datetime import UTC, datetime

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.models.execution_span import (
    ErrorInfo,
    ExecutionOutcome,
    ExecutionSpan,
    ExecutionStrategy,
    GuardDecision,
    SandboxType,
    SpanBuilder,
    _is_retryable,
)


# --------------------------------------------------------------------------- #
# ErrorInfo Tests
# --------------------------------------------------------------------------- #
class TestErrorInfo:
    """Tests for ErrorInfo model."""

    def test_basic_error_info(self):
        """Test creating basic error info."""
        error = ErrorInfo(error_type="ValueError", message="Invalid value")
        assert error.error_type == "ValueError"
        assert error.message == "Invalid value"
        assert error.traceback is None
        assert error.retryable is False

    def test_from_exception(self):
        """Test creating error info from exception."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = ErrorInfo.from_exception(e)

        assert error.error_type == "ValueError"
        assert error.message == "Test error"
        assert error.traceback is not None
        assert "ValueError" in error.traceback

    def test_from_exception_no_traceback(self):
        """Test creating error info without traceback."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = ErrorInfo.from_exception(e, include_traceback=False)

        assert error.error_type == "ValueError"
        assert error.traceback is None


class TestIsRetryable:
    """Tests for _is_retryable function."""

    def test_timeout_error_is_retryable(self):
        """Test TimeoutError is retryable."""
        assert _is_retryable(TimeoutError("Operation timed out")) is True

    def test_connection_error_is_retryable(self):
        """Test ConnectionError is retryable."""
        assert _is_retryable(ConnectionError("Connection refused")) is True

    def test_os_error_is_retryable(self):
        """Test OSError is retryable."""
        assert _is_retryable(OSError("OS error")) is True

    def test_value_error_not_retryable(self):
        """Test ValueError is not retryable."""
        assert _is_retryable(ValueError("Invalid value")) is False

    def test_timeout_in_message_is_retryable(self):
        """Test error with 'timeout' in message is retryable."""
        assert _is_retryable(Exception("Request timeout occurred")) is True

    def test_connection_in_message_is_retryable(self):
        """Test error with 'connection' in message is retryable."""
        assert _is_retryable(Exception("Lost connection to server")) is True

    def test_temporarily_in_message_is_retryable(self):
        """Test error with 'temporarily' in message is retryable."""
        assert _is_retryable(Exception("Service temporarily unavailable")) is True

    def test_rate_limit_in_message_is_retryable(self):
        """Test error with 'rate limit' in message is retryable."""
        assert _is_retryable(Exception("Rate limit exceeded")) is True

    def test_too_many_requests_in_message_is_retryable(self):
        """Test error with 'too many requests' in message is retryable."""
        assert _is_retryable(Exception("Too many requests")) is True


# --------------------------------------------------------------------------- #
# GuardDecision Tests
# --------------------------------------------------------------------------- #
class TestGuardDecision:
    """Tests for GuardDecision model."""

    def test_basic_guard_decision(self):
        """Test creating basic guard decision."""
        decision = GuardDecision(
            guard_name="SchemaGuard",
            guard_class="guards.schema.SchemaGuard",
            verdict=GuardVerdict.ALLOW,
        )
        assert decision.guard_name == "SchemaGuard"
        assert decision.verdict == GuardVerdict.ALLOW

    def test_guard_decision_with_repair(self):
        """Test guard decision with repaired args."""
        decision = GuardDecision(
            guard_name="RepairGuard",
            guard_class="guards.repair.RepairGuard",
            verdict=GuardVerdict.REPAIR,
            reason="Repaired invalid argument",
            repaired_args={"x": 10},
        )
        assert decision.repaired_args == {"x": 10}


# --------------------------------------------------------------------------- #
# ExecutionSpan Tests
# --------------------------------------------------------------------------- #
class TestExecutionSpan:
    """Tests for ExecutionSpan model."""

    def test_basic_span(self):
        """Test creating basic execution span."""
        span = ExecutionSpan(tool_name="test_tool")
        assert span.tool_name == "test_tool"
        assert span.namespace == "default"
        assert span.outcome == ExecutionOutcome.SUCCESS

    def test_span_with_arguments(self):
        """Test span with arguments."""
        span = ExecutionSpan(
            tool_name="calculator.add",
            arguments={"a": 5, "b": 3},
        )
        assert span.arguments == {"a": 5, "b": 3}

    def test_duration_ms_with_no_end(self):
        """Test duration_ms returns 0 when ended_at is None."""
        span = ExecutionSpan(tool_name="test_tool")
        assert span.duration_ms == 0.0

    def test_duration_ms_with_end(self):
        """Test duration_ms returns actual duration."""
        now = datetime.now(UTC)
        span = ExecutionSpan(
            tool_name="test_tool",
            created_at=now,
            ended_at=now,  # Same time for test
        )
        assert span.duration_ms == 0.0

    def test_full_tool_name_with_namespace(self):
        """Test full_tool_name with non-default namespace."""
        span = ExecutionSpan(tool_name="add", namespace="math")
        assert span.full_tool_name == "math.add"

    def test_full_tool_name_with_default_namespace(self):
        """Test full_tool_name with default namespace."""
        span = ExecutionSpan(tool_name="add", namespace="default")
        assert span.full_tool_name == "add"

    def test_full_tool_name_with_empty_namespace(self):
        """Test full_tool_name with empty namespace."""
        span = ExecutionSpan(tool_name="add", namespace="")
        assert span.full_tool_name == "add"

    def test_blocked_property(self):
        """Test blocked property."""
        blocked_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.BLOCKED,
        )
        assert blocked_span.blocked is True

        success_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
        )
        assert success_span.blocked is False

    def test_successful_property(self):
        """Test successful property."""
        success_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.SUCCESS,
        )
        assert success_span.successful is True

        repaired_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.REPAIRED,
        )
        assert repaired_span.successful is True

        failed_span = ExecutionSpan(
            tool_name="test_tool",
            outcome=ExecutionOutcome.FAILED,
        )
        assert failed_span.successful is False

    def test_guard_warnings_property(self):
        """Test guard_warnings property."""
        decisions = [
            GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.ALLOW),
            GuardDecision(guard_name="G2", guard_class="c2", verdict=GuardVerdict.WARN),
            GuardDecision(guard_name="G3", guard_class="c3", verdict=GuardVerdict.WARN),
        ]
        span = ExecutionSpan(tool_name="test_tool", guard_decisions=decisions)
        warnings = span.guard_warnings
        assert len(warnings) == 2
        assert all(w.verdict == GuardVerdict.WARN for w in warnings)

    def test_blocking_guard_property(self):
        """Test blocking_guard property."""
        decisions = [
            GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.ALLOW),
            GuardDecision(guard_name="G2", guard_class="c2", verdict=GuardVerdict.BLOCK),
        ]
        span = ExecutionSpan(tool_name="test_tool", guard_decisions=decisions)
        assert span.blocking_guard is not None
        assert span.blocking_guard.guard_name == "G2"

    def test_blocking_guard_property_none(self):
        """Test blocking_guard property when no blocking guard."""
        decisions = [
            GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.ALLOW),
        ]
        span = ExecutionSpan(tool_name="test_tool", guard_decisions=decisions)
        assert span.blocking_guard is None

    def test_compute_input_hash(self):
        """Test compute_input_hash."""
        span = ExecutionSpan(
            tool_name="add",
            namespace="math",
            arguments={"a": 5, "b": 3},
        )
        hash1 = span.compute_input_hash()
        assert len(hash1) == 16

        # Same inputs should give same hash
        span2 = ExecutionSpan(
            tool_name="add",
            namespace="math",
            arguments={"a": 5, "b": 3},
        )
        assert span2.compute_input_hash() == hash1

    def test_to_otel_attributes(self):
        """Test to_otel_attributes."""
        span = ExecutionSpan(
            tool_name="add",
            namespace="math",
            request_id="req-123",
            error=ErrorInfo(error_type="ValueError", message="Test error"),
            deterministic=True,
            memory_bytes=1024,
            cpu_time_ms=10.5,
        )
        attrs = span.to_otel_attributes()

        assert attrs["tool.name"] == "add"
        assert attrs["tool.namespace"] == "math"
        assert attrs["tool.full_name"] == "math.add"
        assert attrs["request.id"] == "req-123"
        assert attrs["error.type"] == "ValueError"
        assert attrs["error.message"] == "Test error"
        assert attrs["tool.deterministic"] is True
        assert attrs["resource.memory_bytes"] == 1024
        assert attrs["resource.cpu_time_ms"] == 10.5

    def test_to_log_dict(self):
        """Test to_log_dict."""
        span = ExecutionSpan(tool_name="add", namespace="math")
        log_dict = span.to_log_dict()

        assert log_dict["tool"] == "math.add"
        assert log_dict["outcome"] == "success"
        assert "span_id" in log_dict
        assert "trace_id" in log_dict


# --------------------------------------------------------------------------- #
# SpanBuilder Tests
# --------------------------------------------------------------------------- #
class TestSpanBuilder:
    """Tests for SpanBuilder."""

    def test_basic_builder(self):
        """Test basic span builder."""
        builder = SpanBuilder(tool_name="test_tool", arguments={"x": 1})
        span = builder.build()

        assert span.tool_name == "test_tool"
        assert span.arguments == {"x": 1}
        assert span.namespace == "default"

    def test_builder_with_all_init_params(self):
        """Test builder with all initialization parameters."""
        builder = SpanBuilder(
            tool_name="add",
            arguments={"a": 5},
            namespace="math",
            trace_id="trace-123",
            parent_span_id="parent-456",
            request_id="req-789",
            tool_call_id="call-abc",
        )
        span = builder.build()

        assert span.tool_name == "add"
        assert span.namespace == "math"
        assert span.trace_id == "trace-123"
        assert span.parent_span_id == "parent-456"
        assert span.request_id == "req-789"
        assert span.tool_call_id == "call-abc"

    def test_span_id_property(self):
        """Test span_id property."""
        builder = SpanBuilder(tool_name="test", arguments={})
        assert builder.span_id is not None

    def test_trace_id_property(self):
        """Test trace_id property."""
        builder = SpanBuilder(tool_name="test", arguments={})
        assert builder.trace_id is not None

    def test_start_guard_phase(self):
        """Test start_guard_phase."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.start_guard_phase()
        assert result is builder
        assert builder._guard_start is not None

    def test_end_guard_phase(self):
        """Test end_guard_phase."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.start_guard_phase()
        result = builder.end_guard_phase()
        assert result is builder
        assert builder._guard_duration_ms >= 0

    def test_end_guard_phase_without_start(self):
        """Test end_guard_phase without start."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.end_guard_phase()
        assert result is builder
        assert builder._guard_duration_ms == 0.0

    def test_add_guard_decision_allow(self):
        """Test adding ALLOW guard decision."""
        builder = SpanBuilder(tool_name="test", arguments={})
        decision = GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.ALLOW)
        result = builder.add_guard_decision(decision)

        assert result is builder
        assert len(builder._guard_decisions) == 1
        assert builder._final_verdict == GuardVerdict.ALLOW

    def test_add_guard_decision_warn(self):
        """Test adding WARN guard decision."""
        builder = SpanBuilder(tool_name="test", arguments={})
        decision = GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.WARN)
        builder.add_guard_decision(decision)

        assert builder._final_verdict == GuardVerdict.WARN

    def test_add_guard_decision_block(self):
        """Test adding BLOCK guard decision."""
        builder = SpanBuilder(tool_name="test", arguments={})
        decision = GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.BLOCK)
        builder.add_guard_decision(decision)

        assert builder._final_verdict == GuardVerdict.BLOCK

    def test_add_guard_decision_repair(self):
        """Test adding REPAIR guard decision."""
        builder = SpanBuilder(tool_name="test", arguments={})
        decision = GuardDecision(
            guard_name="G1",
            guard_class="c1",
            verdict=GuardVerdict.REPAIR,
            repaired_args={"x": 10},
        )
        builder.add_guard_decision(decision)

        assert builder._final_verdict == GuardVerdict.REPAIR
        assert builder._repaired_arguments == {"x": 10}

    def test_add_guard_decision_block_overrides_repair(self):
        """Test BLOCK verdict overrides REPAIR."""
        builder = SpanBuilder(tool_name="test", arguments={})
        repair = GuardDecision(guard_name="G1", guard_class="c1", verdict=GuardVerdict.REPAIR)
        block = GuardDecision(guard_name="G2", guard_class="c2", verdict=GuardVerdict.BLOCK)

        builder.add_guard_decision(repair)
        builder.add_guard_decision(block)

        assert builder._final_verdict == GuardVerdict.BLOCK

    def test_set_effective_arguments(self):
        """Test set_effective_arguments."""
        builder = SpanBuilder(tool_name="test", arguments={"x": 1})
        result = builder.set_effective_arguments({"x": 10})

        assert result is builder
        span = builder.build()
        assert span.effective_arguments == {"x": 10}

    def test_set_sandbox(self):
        """Test set_sandbox."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_sandbox(SandboxType.PROCESS)

        assert result is builder
        span = builder.build()
        assert span.sandbox_type == SandboxType.PROCESS

    def test_set_strategy(self):
        """Test set_strategy."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_strategy(ExecutionStrategy.SUBPROCESS)

        assert result is builder
        span = builder.build()
        assert span.execution_strategy == ExecutionStrategy.SUBPROCESS

    def test_set_retry_info(self):
        """Test set_retry_info."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_retry_info(attempt=2, max_retries=5)

        assert result is builder
        span = builder.build()
        assert span.retry_attempt == 2
        assert span.max_retries == 5

    def test_set_cache_hit(self):
        """Test set_cache_hit."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_cache_hit("cache-key-123")

        assert result is builder
        span = builder.build()
        assert span.from_cache is True
        assert span.cache_key == "cache-key-123"

    def test_set_started(self):
        """Test set_started."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_started()

        assert result is builder
        assert builder._started_at is not None

    def test_set_result(self):
        """Test set_result."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.set_started()
        result = builder.set_result(42)

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.SUCCESS
        assert span.result == 42
        assert span.result_type == "int"

    def test_set_result_with_repaired_args(self):
        """Test set_result with repaired arguments."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder._repaired_arguments = {"x": 10}
        builder.set_started()
        builder.set_result(42)

        span = builder.build()
        assert span.outcome == ExecutionOutcome.REPAIRED

    def test_set_result_with_none(self):
        """Test set_result with None value."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.set_started()
        builder.set_result(None)

        span = builder.build()
        assert span.result is None
        assert span.result_type is None

    def test_set_blocked(self):
        """Test set_blocked."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_blocked()

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.BLOCKED

    def test_set_error_from_exception(self):
        """Test set_error from exception."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.set_started()
        try:
            raise ValueError("Test error")
        except ValueError as e:
            result = builder.set_error(e)

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.FAILED
        assert span.error is not None
        assert span.error.error_type == "ValueError"

    def test_set_error_from_error_info(self):
        """Test set_error from ErrorInfo."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.set_started()
        error_info = ErrorInfo(error_type="CustomError", message="Custom message")
        result = builder.set_error(error_info)

        assert result is builder
        span = builder.build()
        assert span.error is error_info

    def test_set_timeout(self):
        """Test set_timeout."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_timeout()

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.TIMEOUT

    def test_set_skipped_without_reason(self):
        """Test set_skipped without reason."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_skipped()

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.SKIPPED
        assert span.error is None

    def test_set_skipped_with_reason(self):
        """Test set_skipped with reason."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_skipped("Dependency failed")

        assert result is builder
        span = builder.build()
        assert span.outcome == ExecutionOutcome.SKIPPED
        assert span.error is not None
        assert span.error.message == "Dependency failed"
        assert span.error.error_type == "SkipError"

    def test_set_deterministic(self):
        """Test set_deterministic."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_deterministic(deterministic=True, seed=42)

        assert result is builder
        span = builder.build()
        assert span.deterministic is True
        assert span.random_seed == 42

    def test_set_resource_usage(self):
        """Test set_resource_usage."""
        builder = SpanBuilder(tool_name="test", arguments={})
        result = builder.set_resource_usage(memory_bytes=1024, cpu_time_ms=10.5)

        assert result is builder
        span = builder.build()
        assert span.memory_bytes == 1024
        assert span.cpu_time_ms == 10.5

    def test_build_sets_end_time_if_not_set(self):
        """Test build sets ended_at if not already set."""
        builder = SpanBuilder(tool_name="test", arguments={})
        span = builder.build()
        assert span.ended_at is not None

    def test_build_with_execution_duration(self):
        """Test build computes execution duration."""
        builder = SpanBuilder(tool_name="test", arguments={})
        builder.set_started()
        builder.set_result(42)
        span = builder.build()

        assert span.execution_duration_ms >= 0

    def test_build_computes_input_hash(self):
        """Test build computes input hash."""
        builder = SpanBuilder(tool_name="test", arguments={"x": 1})
        span = builder.build()
        assert span.input_hash is not None
        assert len(span.input_hash) == 16


# --------------------------------------------------------------------------- #
# Enum Tests
# --------------------------------------------------------------------------- #
class TestEnums:
    """Tests for enum values."""

    def test_execution_outcome_values(self):
        """Test ExecutionOutcome enum values."""
        assert ExecutionOutcome.SUCCESS.value == "success"
        assert ExecutionOutcome.BLOCKED.value == "blocked"
        assert ExecutionOutcome.FAILED.value == "failed"
        assert ExecutionOutcome.TIMEOUT.value == "timeout"
        assert ExecutionOutcome.SKIPPED.value == "skipped"
        assert ExecutionOutcome.REPAIRED.value == "repaired"

    def test_sandbox_type_values(self):
        """Test SandboxType enum values."""
        assert SandboxType.NONE.value == "none"
        assert SandboxType.THREAD.value == "thread"
        assert SandboxType.PROCESS.value == "process"
        assert SandboxType.CONTAINER.value == "container"
        assert SandboxType.MCP.value == "mcp"

    def test_execution_strategy_values(self):
        """Test ExecutionStrategy enum values."""
        assert ExecutionStrategy.INPROCESS.value == "inprocess"
        assert ExecutionStrategy.SUBPROCESS.value == "subprocess"
        assert ExecutionStrategy.MCP_STDIO.value == "mcp_stdio"
        assert ExecutionStrategy.MCP_SSE.value == "mcp_sse"
        assert ExecutionStrategy.MCP_HTTP.value == "mcp_http"
        assert ExecutionStrategy.CODE_SANDBOX.value == "code_sandbox"
