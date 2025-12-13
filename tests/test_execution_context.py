# tests/test_execution_context.py
"""Tests for ExecutionContext."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from chuk_tool_processor.core.context import (
    ContextHeader,
    ContextKey,
    ExecutionContext,
    execution_scope,
    get_current_context,
    set_current_context,
)


class TestExecutionContextCreation:
    """Test ExecutionContext creation and defaults."""

    def test_default_creation(self):
        """Test creating context with defaults."""
        ctx = ExecutionContext()

        assert ctx.request_id is not None
        assert len(ctx.request_id) == 36  # UUID format
        assert ctx.correlation_id is None
        assert ctx.user_id is None
        assert ctx.tenant_id is None
        assert ctx.traceparent is None
        assert ctx.deadline is None
        assert ctx.budget is None
        assert ctx.metadata == {}

    def test_explicit_values(self):
        """Test creating context with explicit values."""
        ctx = ExecutionContext(
            request_id="req-123",
            correlation_id="corr-456",
            user_id="user-789",
            tenant_id="tenant-abc",
            budget=100.0,
        )

        assert ctx.request_id == "req-123"
        assert ctx.correlation_id == "corr-456"
        assert ctx.user_id == "user-789"
        assert ctx.tenant_id == "tenant-abc"
        assert ctx.budget == 100.0

    def test_with_deadline(self):
        """Test creating context with deadline."""
        ctx = ExecutionContext.with_deadline(30)

        assert ctx.deadline is not None
        remaining = ctx.remaining_time
        assert remaining is not None
        assert 29 < remaining <= 30

    def test_with_timeout_alias(self):
        """Test with_timeout as alias for with_deadline."""
        ctx = ExecutionContext.with_timeout(15.0, user_id="test-user")

        assert ctx.deadline is not None
        assert ctx.user_id == "test-user"
        remaining = ctx.remaining_time
        assert remaining is not None
        assert 14 < remaining <= 15

    def test_traceparent_validation(self):
        """Test traceparent format validation."""
        # Valid traceparent
        ctx = ExecutionContext(traceparent="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
        assert ctx.traceparent == "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

        # Invalid traceparent (wrong format)
        with pytest.raises(ValueError, match="traceparent must have format"):
            ExecutionContext(traceparent="invalid-format")

    def test_budget_validation(self):
        """Test budget must be non-negative."""
        with pytest.raises(ValueError):
            ExecutionContext(budget=-1.0)

    def test_immutability(self):
        """Test that context is immutable (frozen)."""
        from pydantic import ValidationError

        ctx = ExecutionContext(user_id="user-123")

        with pytest.raises(ValidationError):
            ctx.user_id = "new-user"


class TestExecutionContextProperties:
    """Test ExecutionContext computed properties."""

    def test_remaining_time_with_deadline(self):
        """Test remaining_time with active deadline."""
        deadline = datetime.now(UTC) + timedelta(seconds=10)
        ctx = ExecutionContext(deadline=deadline)

        remaining = ctx.remaining_time
        assert remaining is not None
        assert 9 < remaining <= 10

    def test_remaining_time_without_deadline(self):
        """Test remaining_time without deadline."""
        ctx = ExecutionContext()
        assert ctx.remaining_time is None

    def test_remaining_time_expired(self):
        """Test remaining_time returns 0 when expired."""
        deadline = datetime.now(UTC) - timedelta(seconds=1)
        ctx = ExecutionContext(deadline=deadline)

        assert ctx.remaining_time == 0.0

    def test_is_expired_true(self):
        """Test is_expired when deadline passed."""
        deadline = datetime.now(UTC) - timedelta(seconds=1)
        ctx = ExecutionContext(deadline=deadline)

        assert ctx.is_expired is True

    def test_is_expired_false(self):
        """Test is_expired when deadline not passed."""
        deadline = datetime.now(UTC) + timedelta(seconds=10)
        ctx = ExecutionContext(deadline=deadline)

        assert ctx.is_expired is False

    def test_is_expired_no_deadline(self):
        """Test is_expired when no deadline set."""
        ctx = ExecutionContext()
        assert ctx.is_expired is False

    def test_elapsed_time(self):
        """Test elapsed_time calculation."""
        ctx = ExecutionContext()
        # Small delay to ensure measurable elapsed time
        import time

        time.sleep(0.01)
        assert ctx.elapsed_time >= 0.01


class TestExecutionContextMutators:
    """Test ExecutionContext copy methods."""

    def test_with_span(self):
        """Test creating child context with new span."""
        parent = ExecutionContext(
            request_id="req-123",
            user_id="user-456",
            span_id="span-parent",
        )

        child = parent.with_span("span-child")

        # Child has new span
        assert child.span_id == "span-child"
        # Child preserves other fields
        assert child.request_id == "req-123"
        assert child.user_id == "user-456"
        # Parent unchanged
        assert parent.span_id == "span-parent"

    def test_with_metadata(self):
        """Test adding metadata to context."""
        ctx = ExecutionContext(metadata={"key1": "value1"})

        new_ctx = ctx.with_metadata(key2="value2", key3="value3")

        # New context has merged metadata
        assert new_ctx.metadata == {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3",
        }
        # Original unchanged
        assert ctx.metadata == {"key1": "value1"}

    def test_with_budget(self):
        """Test updating budget."""
        ctx = ExecutionContext(budget=100.0)

        new_ctx = ctx.with_budget(50.0)

        assert new_ctx.budget == 50.0
        assert ctx.budget == 100.0


class TestExecutionContextSerialization:
    """Test ExecutionContext serialization."""

    def test_to_dict(self):
        """Test converting context to dict."""
        ctx = ExecutionContext(
            request_id="req-123",
            user_id="user-456",
            tenant_id="tenant-789",
        )

        d = ctx.to_dict()

        assert d[ContextKey.REQUEST_ID.value] == "req-123"
        assert d[ContextKey.USER_ID.value] == "user-456"
        assert d[ContextKey.TENANT_ID.value] == "tenant-789"
        # None values not included
        assert ContextKey.CORRELATION_ID.value not in d

    def test_to_dict_with_deadline(self):
        """Test to_dict includes deadline and remaining_time."""
        ctx = ExecutionContext.with_deadline(30)

        d = ctx.to_dict()

        assert ContextKey.DEADLINE.value in d
        assert ContextKey.REMAINING_TIME.value in d

    def test_to_headers(self):
        """Test converting context to HTTP headers."""
        ctx = ExecutionContext(
            request_id="req-123",
            user_id="user-456",
            traceparent="00-trace-id-00",
        )

        headers = ctx.to_headers()

        assert headers[ContextHeader.REQUEST_ID.value] == "req-123"
        assert headers[ContextHeader.USER_ID.value] == "user-456"
        assert headers[ContextHeader.TRACEPARENT.value] == "00-trace-id-00"

    def test_to_headers_with_deadline(self):
        """Test headers include deadline as remaining seconds."""
        ctx = ExecutionContext.with_deadline(30)

        headers = ctx.to_headers()

        assert ContextHeader.DEADLINE_SECONDS.value in headers
        deadline_seconds = int(headers[ContextHeader.DEADLINE_SECONDS.value])
        assert 29 <= deadline_seconds <= 30

    def test_from_headers(self):
        """Test creating context from HTTP headers."""
        headers = {
            ContextHeader.REQUEST_ID.value: "req-from-headers",
            ContextHeader.USER_ID.value: "user-from-headers",
            ContextHeader.TENANT_ID.value: "tenant-from-headers",
            ContextHeader.TRACEPARENT.value: "00-trace-id-00",
        }

        ctx = ExecutionContext.from_headers(headers)

        assert ctx.request_id == "req-from-headers"
        assert ctx.user_id == "user-from-headers"
        assert ctx.tenant_id == "tenant-from-headers"
        assert ctx.traceparent == "00-trace-id-00"

    def test_from_headers_with_overrides(self):
        """Test from_headers with explicit overrides."""
        headers = {
            ContextHeader.USER_ID.value: "header-user",
        }

        ctx = ExecutionContext.from_headers(headers, user_id="override-user")

        # Explicit kwarg takes precedence
        assert ctx.user_id == "override-user"


class TestExecutionContextScope:
    """Test execution_scope context manager."""

    @pytest.mark.asyncio
    async def test_async_context_scope(self):
        """Test async context scope."""
        ctx = ExecutionContext(user_id="scoped-user")

        assert get_current_context() is None

        async with execution_scope(ctx):
            current = get_current_context()
            assert current is not None
            assert current.user_id == "scoped-user"

        assert get_current_context() is None

    def test_sync_context_scope(self):
        """Test sync context scope."""
        ctx = ExecutionContext(user_id="scoped-user")

        assert get_current_context() is None

        with execution_scope(ctx):
            current = get_current_context()
            assert current is not None
            assert current.user_id == "scoped-user"

        assert get_current_context() is None

    @pytest.mark.asyncio
    async def test_nested_scopes(self):
        """Test nested context scopes."""
        outer_ctx = ExecutionContext(user_id="outer")
        inner_ctx = ExecutionContext(user_id="inner")

        async with execution_scope(outer_ctx):
            assert get_current_context().user_id == "outer"

            async with execution_scope(inner_ctx):
                assert get_current_context().user_id == "inner"

            # Back to outer
            assert get_current_context().user_id == "outer"

    @pytest.mark.asyncio
    async def test_concurrent_contexts(self):
        """Test contexts are isolated between concurrent tasks."""
        results = []

        async def task_with_context(user_id: str, delay: float):
            ctx = ExecutionContext(user_id=user_id)
            async with execution_scope(ctx):
                await asyncio.sleep(delay)
                current = get_current_context()
                results.append(current.user_id if current else None)

        # Run concurrently with different delays
        await asyncio.gather(
            task_with_context("user-a", 0.02),
            task_with_context("user-b", 0.01),
            task_with_context("user-c", 0.03),
        )

        # Each task should have seen its own context
        assert set(results) == {"user-a", "user-b", "user-c"}

    @pytest.mark.asyncio
    async def test_set_and_get_context(self):
        """Test direct set/get context functions."""
        ctx = ExecutionContext(user_id="direct-set")

        _token = set_current_context(ctx)  # noqa: F841
        assert get_current_context() == ctx

        # Reset to None
        set_current_context(None)
        assert get_current_context() is None
