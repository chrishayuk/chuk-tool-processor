# tests/guards/test_chain.py
"""Tests for GuardChain."""

import pytest

from chuk_tool_processor.guards.base import BaseGuard, GuardResult, GuardVerdict
from chuk_tool_processor.guards.chain import GuardChain, GuardChainResult


class AllowGuard(BaseGuard):
    """Guard that always allows."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.allow(reason="Always allow")


class BlockGuard(BaseGuard):
    """Guard that always blocks."""

    def __init__(self, reason: str = "Blocked"):
        self.reason = reason

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.block(reason=self.reason)


class WarnGuard(BaseGuard):
    """Guard that always warns."""

    def __init__(self, reason: str = "Warning"):
        self.reason = reason

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.warn(reason=self.reason)


class RepairGuard(BaseGuard):
    """Guard that repairs arguments."""

    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        repaired = dict(arguments)
        repaired[self.key] = self.value
        return GuardResult(
            verdict=GuardVerdict.REPAIR,
            reason="Repaired",
            repaired_args=repaired,
        )


class OutputBlockGuard(BaseGuard):
    """Guard that blocks on output check."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.allow()

    def check_output(self, tool_name: str, arguments: dict, result: object) -> GuardResult:
        if isinstance(result, dict) and result.get("blocked"):
            return self.block(reason="Output blocked")
        return self.allow()


class ResettableGuard(BaseGuard):
    """Guard with reset method."""

    def __init__(self):
        self.reset_called = False

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return self.allow()

    def reset(self):
        self.reset_called = True


class TestGuardChain:
    """Tests for GuardChain."""

    def test_empty_chain_allows(self):
        """Test empty chain allows everything."""
        chain = GuardChain()
        result = chain.check_all("tool", {"arg": "value"})
        assert result.allowed
        assert result.final_verdict == GuardVerdict.ALLOW

    def test_all_allow_produces_allow(self):
        """Test all allowing guards produces ALLOW."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard2", AllowGuard()),
            ]
        )
        result = chain.check_all("tool", {})
        assert result.allowed
        assert result.final_verdict == GuardVerdict.ALLOW

    def test_any_block_produces_block(self):
        """Test any blocking guard produces BLOCK."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard2", BlockGuard("Blocked!")),
                ("guard3", AllowGuard()),
            ]
        )
        result = chain.check_all("tool", {})
        assert result.blocked
        assert result.stopped_at == "guard2"
        assert "Blocked!" in result.final_reason

    def test_block_stops_chain(self):
        """Test block stops chain execution."""
        guard3 = AllowGuard()
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard2", BlockGuard()),
                ("guard3", guard3),
            ]
        )
        result = chain.check_all("tool", {})
        assert result.blocked
        # Should have 2 results (stopped before guard3)
        assert len(result.guard_results) == 2

    def test_warn_continues_chain(self):
        """Test warn continues chain execution."""
        chain = GuardChain(
            [
                ("guard1", WarnGuard("Warning 1")),
                ("guard2", AllowGuard()),
                ("guard3", WarnGuard("Warning 2")),
            ]
        )
        result = chain.check_all("tool", {})
        assert result.allowed  # Warnings allow execution
        assert result.final_verdict == GuardVerdict.WARN
        assert len(result.guard_results) == 3

    def test_warn_reasons_collected(self):
        """Test warning reasons are collected."""
        chain = GuardChain(
            [
                ("guard1", WarnGuard("First warning")),
                ("guard2", WarnGuard("Second warning")),
            ]
        )
        result = chain.check_all("tool", {})
        assert "First warning" in result.final_reason
        assert "Second warning" in result.final_reason

    def test_repair_modifies_args(self):
        """Test repair verdict modifies arguments."""
        chain = GuardChain(
            [
                ("repair", RepairGuard("key", "repaired_value")),
                ("allow", AllowGuard()),
            ]
        )
        result = chain.check_all("tool", {"key": "original"})
        assert result.allowed
        assert result.repaired_args is not None
        assert result.repaired_args["key"] == "repaired_value"

    def test_repair_passes_modified_args(self):
        """Test repaired args are passed to subsequent guards."""

        # Create a guard that checks for specific value
        class CheckValueGuard(BaseGuard):
            def check(self, tool_name: str, arguments: dict) -> GuardResult:
                if arguments.get("key") == "expected":
                    return self.allow()
                return self.block(reason="Wrong value")

        chain = GuardChain(
            [
                ("repair", RepairGuard("key", "expected")),
                ("check", CheckValueGuard()),
            ]
        )
        result = chain.check_all("tool", {"key": "original"})
        assert result.allowed

    def test_add_guard(self):
        """Test adding guard to chain."""
        chain = GuardChain()
        chain.add("guard1", AllowGuard())
        chain.add("guard2", BlockGuard())

        assert len(chain) == 2
        result = chain.check_all("tool", {})
        assert result.blocked

    def test_add_chaining(self):
        """Test add returns self for chaining."""
        chain = GuardChain().add("guard1", AllowGuard()).add("guard2", AllowGuard())
        assert len(chain) == 2

    def test_insert_guard(self):
        """Test inserting guard at position."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard3", AllowGuard()),
            ]
        )
        chain.insert(1, "guard2", BlockGuard())

        result = chain.check_all("tool", {})
        assert result.stopped_at == "guard2"

    def test_remove_guard(self):
        """Test removing guard by name."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("blocker", BlockGuard()),
                ("guard2", AllowGuard()),
            ]
        )
        chain.remove("blocker")

        result = chain.check_all("tool", {})
        assert result.allowed
        assert len(chain) == 2

    def test_get_guard(self):
        """Test getting guard by name."""
        guard = AllowGuard()
        chain = GuardChain([("my_guard", guard)])

        retrieved = chain.get("my_guard")
        assert retrieved is guard

        missing = chain.get("nonexistent")
        assert missing is None

    def test_iteration(self):
        """Test iterating over chain."""
        guards = [
            ("guard1", AllowGuard()),
            ("guard2", AllowGuard()),
        ]
        chain = GuardChain(guards)

        items = list(chain)
        assert len(items) == 2
        assert items[0][0] == "guard1"

    def test_len(self):
        """Test len returns guard count."""
        chain = GuardChain(
            [
                ("g1", AllowGuard()),
                ("g2", AllowGuard()),
                ("g3", AllowGuard()),
            ]
        )
        assert len(chain) == 3


class TestGuardChainOutput:
    """Tests for output checking."""

    def test_check_output_all_allows(self):
        """Test check_output_all with all allowing guards."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard2", AllowGuard()),
            ]
        )
        result = chain.check_output_all("tool", {}, {"data": "result"})
        assert result.allowed

    def test_check_output_all_blocks(self):
        """Test check_output_all blocks on output."""
        chain = GuardChain(
            [
                ("allow", AllowGuard()),
                ("output_blocker", OutputBlockGuard()),
            ]
        )
        result = chain.check_output_all("tool", {}, {"blocked": True})
        assert result.blocked
        assert result.stopped_at == "output_blocker"

    def test_check_output_all_stops_on_block(self):
        """Test output check stops on block."""
        chain = GuardChain(
            [
                ("blocker", OutputBlockGuard()),
                ("allow", AllowGuard()),
            ]
        )
        result = chain.check_output_all("tool", {}, {"blocked": True})
        assert len(result.guard_results) == 1


class TestGuardChainAsync:
    """Tests for async chain checking."""

    @pytest.mark.asyncio
    async def test_check_all_async(self):
        """Test async chain checking."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("guard2", AllowGuard()),
            ]
        )
        result = await chain.check_all_async("tool", {})
        assert result.allowed

    @pytest.mark.asyncio
    async def test_check_all_async_blocks(self):
        """Test async chain blocks correctly."""
        chain = GuardChain(
            [
                ("guard1", AllowGuard()),
                ("blocker", BlockGuard("Async blocked")),
            ]
        )
        result = await chain.check_all_async("tool", {})
        assert result.blocked
        assert result.stopped_at == "blocker"


class TestGuardChainReset:
    """Tests for reset functionality."""

    def test_reset_all(self):
        """Test reset_all calls reset on all guards."""
        guard1 = ResettableGuard()
        guard2 = ResettableGuard()

        chain = GuardChain(
            [
                ("guard1", guard1),
                ("guard2", guard2),
            ]
        )
        chain.reset_all()

        assert guard1.reset_called
        assert guard2.reset_called

    def test_reset_all_skips_non_resettable(self):
        """Test reset_all skips guards without reset."""
        chain = GuardChain(
            [
                ("allow", AllowGuard()),  # No reset method
                ("resettable", ResettableGuard()),
            ]
        )
        # Should not raise
        chain.reset_all()


class TestGuardChainResult:
    """Tests for GuardChainResult."""

    def test_allowed_property(self):
        """Test allowed property."""
        result = GuardChainResult(final_verdict=GuardVerdict.ALLOW)
        assert result.allowed

        result = GuardChainResult(final_verdict=GuardVerdict.WARN)
        assert result.allowed  # Warnings still allow

        result = GuardChainResult(final_verdict=GuardVerdict.BLOCK)
        assert not result.allowed

    def test_blocked_property(self):
        """Test blocked property."""
        result = GuardChainResult(final_verdict=GuardVerdict.BLOCK)
        assert result.blocked

        result = GuardChainResult(final_verdict=GuardVerdict.ALLOW)
        assert not result.blocked


class TestGuardChainCreateDefault:
    """Tests for default chain creation."""

    def test_create_default(self):
        """Test creating default guard chain."""
        chain = GuardChain.create_default()

        # Should have multiple guards
        assert len(chain) > 0

        # Should include expected guards
        guard_names = [name for name, _ in chain]
        assert "schema" in guard_names
        assert "network" in guard_names
        assert "concurrency" in guard_names

    def test_create_default_checks_work(self):
        """Test default chain can perform checks."""
        chain = GuardChain.create_default()

        # Should allow basic tool call
        result = chain.check_all("get_user", {"id": 123})
        # May warn but shouldn't block basic call
        assert result.final_verdict in (GuardVerdict.ALLOW, GuardVerdict.WARN)
