# tests/core/test_context_coverage.py
"""Coverage tests for core.context module.

Targets the uncovered lines around from_headers edge cases,
to_dict conditional branches, to_headers conditional branches,
and the execution_scope context manager.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from chuk_tool_processor.core.context import (
    ContextHeader,
    ContextKey,
    ExecutionContext,
    execution_scope,
    get_current_context,
    set_current_context,
)


# ------------------------------------------------------------------ #
# from_headers - edge cases (lines 229, 237, 239-241, 243-244)
# ------------------------------------------------------------------ #
class TestFromHeaders:
    """Tests for ExecutionContext.from_headers() covering all branches."""

    def test_empty_headers(self):
        ctx = ExecutionContext.from_headers({})
        assert ctx.request_id  # auto-generated
        assert ctx.correlation_id is None
        assert ctx.user_id is None
        assert ctx.tenant_id is None

    def test_all_headers(self):
        headers = {
            "X-Request-ID": "req-abc",
            "X-Correlation-ID": "corr-def",
            "X-User-ID": "user-ghi",
            "X-Tenant-ID": "tenant-jkl",
            "traceparent": "00-aabbccdd-11223344-01",
            "tracestate": "vendor=value",
            "X-Deadline-Seconds": "30",
            "X-Budget": "100.5",
        }
        ctx = ExecutionContext.from_headers(headers)
        assert ctx.request_id == "req-abc"
        assert ctx.correlation_id == "corr-def"
        assert ctx.user_id == "user-ghi"
        assert ctx.tenant_id == "tenant-jkl"
        assert ctx.traceparent == "00-aabbccdd-11223344-01"
        assert ctx.tracestate == "vendor=value"
        assert ctx.deadline is not None
        assert ctx.budget == pytest.approx(100.5)

    def test_deadline_header_sets_future_deadline(self):
        headers = {"X-Deadline-Seconds": "60"}
        before = datetime.now(UTC)
        ctx = ExecutionContext.from_headers(headers)
        after = datetime.now(UTC)
        assert ctx.deadline is not None
        # Deadline should be roughly 60s from now
        assert ctx.deadline >= before + timedelta(seconds=59)
        assert ctx.deadline <= after + timedelta(seconds=61)

    def test_invalid_deadline_header_ignored(self):
        """Non-numeric deadline is silently ignored."""
        headers = {"X-Deadline-Seconds": "not_a_number"}
        ctx = ExecutionContext.from_headers(headers)
        assert ctx.deadline is None

    def test_invalid_budget_header_ignored(self):
        """Non-numeric budget is silently ignored."""
        headers = {"X-Budget": "not_a_number"}
        ctx = ExecutionContext.from_headers(headers)
        assert ctx.budget is None

    def test_kwargs_override_headers(self):
        headers = {"X-User-ID": "header_user"}
        ctx = ExecutionContext.from_headers(headers, user_id="kwarg_user")
        assert ctx.user_id == "kwarg_user"


# ------------------------------------------------------------------ #
# to_dict - conditional branches (lines 324, 330, 332, 334, 339, 341)
# ------------------------------------------------------------------ #
class TestToDict:
    """Tests for ExecutionContext.to_dict() covering all conditional branches."""

    def test_minimal_context(self):
        """Only request_id should be present for minimal context."""
        ctx = ExecutionContext(request_id="req-1")
        d = ctx.to_dict()
        assert d[ContextKey.REQUEST_ID.value] == "req-1"
        assert ContextKey.CORRELATION_ID.value not in d
        assert ContextKey.USER_ID.value not in d
        assert ContextKey.TENANT_ID.value not in d
        assert ContextKey.TRACEPARENT.value not in d
        assert ContextKey.TRACESTATE.value not in d
        assert ContextKey.SPAN_ID.value not in d
        assert ContextKey.DEADLINE.value not in d
        assert ContextKey.BUDGET.value not in d
        assert ContextKey.METADATA.value not in d

    def test_all_fields_populated(self):
        deadline = datetime.now(UTC) + timedelta(seconds=60)
        ctx = ExecutionContext(
            request_id="req-2",
            correlation_id="corr-2",
            user_id="user-2",
            tenant_id="tenant-2",
            traceparent="00-aabb-ccdd-01",
            tracestate="vendor=val",
            span_id="span-2",
            deadline=deadline,
            budget=50.0,
            metadata={"key": "value"},
        )
        d = ctx.to_dict()
        assert d[ContextKey.REQUEST_ID.value] == "req-2"
        assert d[ContextKey.CORRELATION_ID.value] == "corr-2"
        assert d[ContextKey.USER_ID.value] == "user-2"
        assert d[ContextKey.TENANT_ID.value] == "tenant-2"
        assert d[ContextKey.TRACEPARENT.value] == "00-aabb-ccdd-01"
        assert d[ContextKey.TRACESTATE.value] == "vendor=val"
        assert d[ContextKey.SPAN_ID.value] == "span-2"
        assert d[ContextKey.DEADLINE.value] == deadline.isoformat()
        assert d[ContextKey.REMAINING_TIME.value] is not None
        assert d[ContextKey.BUDGET.value] == 50.0
        assert d[ContextKey.METADATA.value] == {"key": "value"}

    def test_budget_zero_included(self):
        """Budget of 0.0 should still be included (it's not None)."""
        ctx = ExecutionContext(request_id="req-3", budget=0.0)
        d = ctx.to_dict()
        assert d[ContextKey.BUDGET.value] == 0.0

    def test_empty_metadata_excluded(self):
        """Empty metadata dict should be excluded."""
        ctx = ExecutionContext(request_id="req-4", metadata={})
        d = ctx.to_dict()
        assert ContextKey.METADATA.value not in d


# ------------------------------------------------------------------ #
# to_headers - conditional branches (lines 357, 361, 365, 371)
# ------------------------------------------------------------------ #
class TestToHeaders:
    """Tests for ExecutionContext.to_headers() covering all conditional branches."""

    def test_minimal_context(self):
        ctx = ExecutionContext(request_id="req-h1")
        h = ctx.to_headers()
        assert h[ContextHeader.REQUEST_ID.value] == "req-h1"
        assert ContextHeader.CORRELATION_ID.value not in h
        assert ContextHeader.USER_ID.value not in h
        assert ContextHeader.TENANT_ID.value not in h
        assert ContextHeader.TRACEPARENT.value not in h
        assert ContextHeader.TRACESTATE.value not in h
        assert ContextHeader.DEADLINE_SECONDS.value not in h
        assert ContextHeader.BUDGET.value not in h

    def test_all_fields_populated(self):
        deadline = datetime.now(UTC) + timedelta(seconds=120)
        ctx = ExecutionContext(
            request_id="req-h2",
            correlation_id="corr-h2",
            user_id="user-h2",
            tenant_id="tenant-h2",
            traceparent="00-1234-5678-01",
            tracestate="vendor=stuff",
            deadline=deadline,
            budget=75.5,
        )
        h = ctx.to_headers()
        assert h[ContextHeader.REQUEST_ID.value] == "req-h2"
        assert h[ContextHeader.CORRELATION_ID.value] == "corr-h2"
        assert h[ContextHeader.USER_ID.value] == "user-h2"
        assert h[ContextHeader.TENANT_ID.value] == "tenant-h2"
        assert h[ContextHeader.TRACEPARENT.value] == "00-1234-5678-01"
        assert h[ContextHeader.TRACESTATE.value] == "vendor=stuff"
        assert ContextHeader.DEADLINE_SECONDS.value in h
        # Should be roughly 120 seconds
        remaining_str = h[ContextHeader.DEADLINE_SECONDS.value]
        assert int(remaining_str) >= 118  # Allow for slight timing
        assert h[ContextHeader.BUDGET.value] == "75.5"

    def test_budget_zero_included(self):
        """Budget of 0.0 should still appear in headers."""
        ctx = ExecutionContext(request_id="req-h3", budget=0.0)
        h = ctx.to_headers()
        assert h[ContextHeader.BUDGET.value] == "0.0"

    def test_deadline_with_remaining_time(self):
        """Deadline should produce deadline-seconds header."""
        deadline = datetime.now(UTC) + timedelta(seconds=45)
        ctx = ExecutionContext(request_id="req-h4", deadline=deadline)
        h = ctx.to_headers()
        assert ContextHeader.DEADLINE_SECONDS.value in h


# ------------------------------------------------------------------ #
# execution_scope context manager (sync and async)
# ------------------------------------------------------------------ #
class TestExecutionScope:
    """Tests for execution_scope context manager."""

    @pytest.mark.asyncio
    async def test_async_scope(self):
        ctx = ExecutionContext(request_id="async-scope")
        assert get_current_context() is None or get_current_context().request_id != "async-scope"
        async with execution_scope(ctx) as entered:
            assert entered is ctx
            assert get_current_context() is ctx
        # After exiting, context should be restored
        assert get_current_context() is None or get_current_context().request_id != "async-scope"

    def test_sync_scope(self):
        ctx = ExecutionContext(request_id="sync-scope")
        with execution_scope(ctx) as entered:
            assert entered is ctx
            assert get_current_context() is ctx
        assert get_current_context() is None or get_current_context().request_id != "sync-scope"

    @pytest.mark.asyncio
    async def test_nested_scopes(self):
        ctx1 = ExecutionContext(request_id="outer")
        ctx2 = ExecutionContext(request_id="inner")
        async with execution_scope(ctx1):
            assert get_current_context().request_id == "outer"
            async with execution_scope(ctx2):
                assert get_current_context().request_id == "inner"
            assert get_current_context().request_id == "outer"

    @pytest.mark.asyncio
    async def test_scope_restores_on_exception(self):
        ctx = ExecutionContext(request_id="exc-scope")
        try:
            async with execution_scope(ctx):
                assert get_current_context() is ctx
                raise ValueError("test error")
        except ValueError:
            pass
        assert get_current_context() is None or get_current_context().request_id != "exc-scope"

    def test_sync_scope_restores_on_exception(self):
        ctx = ExecutionContext(request_id="sync-exc")
        try:
            with execution_scope(ctx):
                assert get_current_context() is ctx
                raise RuntimeError("test")
        except RuntimeError:
            pass
        assert get_current_context() is None or get_current_context().request_id != "sync-exc"


# ------------------------------------------------------------------ #
# set_current_context / get_current_context
# ------------------------------------------------------------------ #
class TestContextVarFunctions:
    """Tests for get_current_context and set_current_context."""

    def test_set_and_get(self):
        ctx = ExecutionContext(request_id="cv-test")
        set_current_context(ctx)
        try:
            assert get_current_context() is ctx
        finally:
            set_current_context(None)

    def test_set_none_clears(self):
        ctx = ExecutionContext(request_id="cv-clear")
        set_current_context(ctx)
        set_current_context(None)
        assert get_current_context() is None


# ------------------------------------------------------------------ #
# traceparent validation
# ------------------------------------------------------------------ #
class TestTraceparentValidation:
    """Tests for traceparent field validator."""

    def test_valid_traceparent(self):
        ctx = ExecutionContext(traceparent="00-aabb-ccdd-01")
        assert ctx.traceparent == "00-aabb-ccdd-01"

    def test_none_traceparent(self):
        ctx = ExecutionContext(traceparent=None)
        assert ctx.traceparent is None

    def test_invalid_traceparent_raises(self):
        with pytest.raises(ValidationError):
            ExecutionContext(traceparent="invalid-no-dashes")
