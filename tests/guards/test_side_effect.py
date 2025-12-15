# tests/guards/test_side_effect.py
"""Tests for SideEffectGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.side_effect import (
    Environment,
    ExecutionMode,
    SideEffectClass,
    SideEffectConfig,
    SideEffectGuard,
)


class TestSideEffectGuard:
    """Tests for SideEffectGuard."""

    @pytest.fixture
    def guard(self) -> SideEffectGuard:
        """Default guard in write-allowed mode."""
        return SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.WRITE_ALLOWED,
                environment=Environment.DEV,
            )
        )

    def test_read_only_tool_allowed(self, guard: SideEffectGuard):
        """Test read-only tools are allowed."""
        result = guard.check("get_user", {})
        assert result.allowed

    def test_write_tool_allowed_in_write_mode(self, guard: SideEffectGuard):
        """Test write tools are allowed in write mode."""
        result = guard.check("create_user", {})
        assert result.allowed

    def test_destructive_blocked_in_write_mode(self, guard: SideEffectGuard):
        """Test destructive tools are blocked in write mode."""
        result = guard.check("delete_user", {})
        assert result.blocked
        assert "destructive" in result.reason.lower()

    def test_read_only_mode_blocks_writes(self):
        """Test read-only mode blocks write operations."""
        guard = SideEffectGuard(config=SideEffectConfig(mode=ExecutionMode.READ_ONLY))

        result = guard.check("get_user", {})
        assert result.allowed

        result = guard.check("create_user", {})
        assert result.blocked
        assert "read-only" in result.reason.lower()

    def test_destructive_allowed_mode(self):
        """Test destructive-allowed mode allows all operations."""
        guard = SideEffectGuard(config=SideEffectConfig(mode=ExecutionMode.DESTRUCTIVE_ALLOWED))

        result = guard.check("delete_user", {})
        assert result.allowed

    def test_production_blocks_destructive(self):
        """Test production environment blocks destructive by default."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.DESTRUCTIVE_ALLOWED,
                environment=Environment.PROD,
            )
        )

        result = guard.check("delete_user", {})
        assert result.blocked
        assert "production" in result.reason.lower()

    def test_production_allows_reads(self):
        """Test production allows read operations."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.WRITE_ALLOWED,
                environment=Environment.PROD,
            )
        )

        result = guard.check("get_user", {})
        assert result.allowed

    def test_explicit_classification(self):
        """Test explicit tool classification override."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.READ_ONLY,
                explicit_classifications={
                    "safe_update": SideEffectClass.READ_ONLY,
                },
            )
        )

        # Normally would be write, but explicitly marked read-only
        result = guard.check("safe_update", {})
        assert result.allowed

    def test_capability_token_required(self):
        """Test capability token requirement."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.WRITE_ALLOWED,
                require_capability_token=True,
            )
        )

        # Write without token should fail
        result = guard.check("create_user", {"name": "Alice"})
        assert result.blocked
        assert "capability token" in result.reason.lower()

        # Write with token should succeed
        result = guard.check("create_user", {"name": "Alice", "_capability_token": "valid_token"})
        assert result.allowed

    def test_capability_token_not_required_for_reads(self):
        """Test capability token not required for read operations."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.WRITE_ALLOWED,
                require_capability_token=True,
            )
        )

        result = guard.check("get_user", {"id": 123})
        assert result.allowed

    def test_custom_classification_callback(self):
        """Test custom classification callback."""

        def custom_classifier(tool_name: str) -> SideEffectClass:
            if "admin" in tool_name:
                return SideEffectClass.DESTRUCTIVE
            return SideEffectClass.READ_ONLY

        guard = SideEffectGuard(
            config=SideEffectConfig(mode=ExecutionMode.WRITE_ALLOWED),
            get_classification=custom_classifier,
        )

        result = guard.check("admin_action", {})
        assert result.blocked

        result = guard.check("user_action", {})
        assert result.allowed

    def test_warn_mode(self):
        """Test warn mode returns warning."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.READ_ONLY,
                enforcement_level=EnforcementLevel.WARN,
            )
        )

        result = guard.check("create_user", {})
        assert result.verdict == GuardVerdict.WARN

    def test_set_mode(self, guard: SideEffectGuard):
        """Test changing mode at runtime."""
        guard.set_mode(ExecutionMode.READ_ONLY)

        result = guard.check("create_user", {})
        assert result.blocked

    def test_set_environment(self, guard: SideEffectGuard):
        """Test changing environment at runtime."""
        guard.set_mode(ExecutionMode.DESTRUCTIVE_ALLOWED)
        guard.set_environment(Environment.PROD)

        result = guard.check("delete_user", {})
        assert result.blocked


class TestToolClassificationHeuristics:
    """Tests for automatic tool classification."""

    @pytest.fixture
    def guard(self) -> SideEffectGuard:
        return SideEffectGuard()

    def test_read_patterns(self, guard: SideEffectGuard):
        """Test read-only pattern detection."""
        read_tools = [
            "get_user",
            "list_items",
            "search_products",
            "read_file",
            "fetch_data",
            "query_database",
            "describe_table",
        ]
        for tool in read_tools:
            classification = guard._heuristic_classification(tool)
            assert classification == SideEffectClass.READ_ONLY, f"{tool} should be read_only"

    def test_write_patterns(self, guard: SideEffectGuard):
        """Test write pattern detection."""
        write_tools = [
            "create_user",
            "update_record",
            "save_file",
            "insert_row",
            "send_email",
        ]
        for tool in write_tools:
            classification = guard._heuristic_classification(tool)
            assert classification == SideEffectClass.WRITE, f"{tool} should be write"

    def test_destructive_patterns(self, guard: SideEffectGuard):
        """Test destructive pattern detection."""
        destructive_tools = [
            "delete_user",
            "remove_item",
            "drop_table",
            "destroy_resource",
            "purge_cache",
        ]
        for tool in destructive_tools:
            classification = guard._heuristic_classification(tool)
            assert classification == SideEffectClass.DESTRUCTIVE, f"{tool} should be destructive"


class TestSideEffectGuardAsync:
    """Tests for async methods of SideEffectGuard."""

    @pytest.mark.asyncio
    async def test_check_async_with_sync_classifier(self):
        """Test check_async with synchronous classification callback (lines 172-176)."""

        def sync_classifier(tool_name: str) -> SideEffectClass:
            if "delete" in tool_name:
                return SideEffectClass.DESTRUCTIVE
            return SideEffectClass.READ_ONLY

        guard = SideEffectGuard(
            config=SideEffectConfig(mode=ExecutionMode.WRITE_ALLOWED),
            get_classification=sync_classifier,
        )

        # Test with read-only classified tool
        result = await guard.check_async("get_user", {})
        assert result.allowed

        # Test with destructive classified tool
        result = await guard.check_async("delete_user", {})
        assert result.blocked

    @pytest.mark.asyncio
    async def test_check_async_with_async_classifier(self):
        """Test check_async with asynchronous classification callback (lines 173-175)."""

        async def async_classifier(tool_name: str) -> SideEffectClass:
            # Simulate async operation
            if "admin" in tool_name:
                return SideEffectClass.DESTRUCTIVE
            return SideEffectClass.WRITE

        guard = SideEffectGuard(
            config=SideEffectConfig(mode=ExecutionMode.WRITE_ALLOWED),
            get_classification=async_classifier,
        )

        # Test with write classified tool
        result = await guard.check_async("update_user", {})
        assert result.allowed

        # Test with destructive classified tool
        result = await guard.check_async("admin_delete", {})
        assert result.blocked

    @pytest.mark.asyncio
    async def test_check_async_with_explicit_classification(self):
        """Test check_async uses explicit classification (lines 169-170)."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.READ_ONLY,
                explicit_classifications={"safe_write": SideEffectClass.READ_ONLY},
            )
        )

        # Explicitly classified as read_only should pass in read_only mode
        result = await guard.check_async("safe_write", {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_async_without_classifier(self):
        """Test check_async falls back to heuristic (line 178)."""
        guard = SideEffectGuard(config=SideEffectConfig(mode=ExecutionMode.WRITE_ALLOWED))

        # Should use heuristic classification
        result = await guard.check_async("get_user", {})
        assert result.allowed

        result = await guard.check_async("delete_user", {})
        assert result.blocked

    @pytest.mark.asyncio
    async def test_check_async_env_violation(self):
        """Test check_async environment check (lines 138-140)."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.DESTRUCTIVE_ALLOWED,
                environment=Environment.PROD,
            )
        )

        result = await guard.check_async("delete_user", {})
        assert result.blocked
        assert "production" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_async_mode_violation(self):
        """Test check_async mode check (lines 142-144)."""
        guard = SideEffectGuard(config=SideEffectConfig(mode=ExecutionMode.READ_ONLY))

        result = await guard.check_async("create_user", {})
        assert result.blocked
        assert "read-only" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_async_token_violation(self):
        """Test check_async capability token check (lines 146-148)."""
        guard = SideEffectGuard(
            config=SideEffectConfig(
                mode=ExecutionMode.WRITE_ALLOWED,
                require_capability_token=True,
            )
        )

        result = await guard.check_async("create_user", {"name": "Alice"})
        assert result.blocked
        assert "capability token" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_async_success(self):
        """Test check_async returns allow on success (line 150)."""
        guard = SideEffectGuard(config=SideEffectConfig(mode=ExecutionMode.WRITE_ALLOWED))

        result = await guard.check_async("create_user", {})
        assert result.allowed
