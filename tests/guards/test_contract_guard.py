# tests/guards/test_contract_guard.py
"""
Tests for the ContractGuard and ContractAwareGuardChain.
"""

from chuk_tool_processor.guards.base import BaseGuard, GuardResult, GuardVerdict
from chuk_tool_processor.guards.contract_guard import (
    ContractAwareGuardChain,
    ContractGuard,
)
from chuk_tool_processor.models.tool_contract import (
    ToolContract,
)


# --------------------------------------------------------------------------- #
# Mock Guards for Testing
# --------------------------------------------------------------------------- #
class AllowGuard(BaseGuard):
    """Guard that always allows."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return GuardResult(verdict=GuardVerdict.ALLOW, reason="Always allow")


class BlockGuard(BaseGuard):
    """Guard that always blocks."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return GuardResult(verdict=GuardVerdict.BLOCK, reason="Always block")


class OutputBlockGuard(BaseGuard):
    """Guard that blocks on output check."""

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return GuardResult(verdict=GuardVerdict.ALLOW)

    def check_output(self, tool_name: str, arguments: dict, result) -> GuardResult:
        return GuardResult(verdict=GuardVerdict.BLOCK, reason="Output blocked")


class NamedGuard(BaseGuard):
    """Guard with explicit name."""

    name = "named_guard"

    def check(self, tool_name: str, arguments: dict) -> GuardResult:
        return GuardResult(verdict=GuardVerdict.ALLOW)


# --------------------------------------------------------------------------- #
# ContractGuard Tests
# --------------------------------------------------------------------------- #
class TestContractGuardInit:
    """Tests for ContractGuard initialization."""

    def test_basic_init(self):
        """Test basic initialization."""
        guard = ContractGuard()
        assert guard._registry is None
        assert guard._contracts == {}
        assert guard._strict is False

    def test_init_with_contracts(self):
        """Test initialization with contracts."""
        contract = ToolContract(requires=["n > 0"])
        contracts = {"factorial": contract}

        guard = ContractGuard(contracts=contracts)
        assert "factorial" in guard._contracts
        assert guard._contracts["factorial"] is contract

    def test_init_with_strict(self):
        """Test initialization with strict mode."""
        guard = ContractGuard(strict=True)
        assert guard._strict is True


class TestContractGuardRegisterContract:
    """Tests for register_contract method."""

    def test_register_contract(self):
        """Test registering a contract."""
        guard = ContractGuard()
        contract = ToolContract(requires=["x > 0"])

        guard.register_contract("my_tool", contract)

        assert "my_tool" in guard._contracts
        assert guard._contracts["my_tool"] is contract

    def test_register_multiple_contracts(self):
        """Test registering multiple contracts."""
        guard = ContractGuard()

        guard.register_contract("tool_a", ToolContract(requires=["a > 0"]))
        guard.register_contract("tool_b", ToolContract(requires=["b > 0"]))

        assert "tool_a" in guard._contracts
        assert "tool_b" in guard._contracts


class TestContractGuardGetContract:
    """Tests for get_contract method."""

    def test_get_contract_by_name(self):
        """Test getting contract by tool name."""
        contract = ToolContract(requires=["n > 0"])
        guard = ContractGuard(contracts={"factorial": contract})

        result = guard.get_contract("factorial")
        assert result is contract

    def test_get_contract_by_full_name(self):
        """Test getting contract by full namespaced name."""
        contract = ToolContract(requires=["n > 0"])
        guard = ContractGuard(contracts={"math.factorial": contract})

        result = guard.get_contract("factorial", "math")
        assert result is contract

    def test_get_contract_not_found(self):
        """Test getting contract when not found."""
        guard = ContractGuard()

        result = guard.get_contract("nonexistent")
        assert result is None

    def test_get_contract_prefers_full_name(self):
        """Test that full name takes precedence over short name."""
        short_contract = ToolContract(requires=["short"])
        full_contract = ToolContract(requires=["full"])

        guard = ContractGuard(
            contracts={
                "factorial": short_contract,
                "math.factorial": full_contract,
            }
        )

        result = guard.get_contract("factorial", "math")
        assert result is full_contract


class TestContractGuardCheck:
    """Tests for check method (precondition validation)."""

    def test_check_no_contract(self):
        """Test check when no contract exists."""
        guard = ContractGuard()

        result = guard.check("unknown_tool", {"x": 1})

        assert result.verdict == GuardVerdict.ALLOW
        assert "No contract defined" in result.reason

    def test_check_no_preconditions(self):
        """Test check when contract has no preconditions."""
        contract = ToolContract()  # No requires
        guard = ContractGuard(contracts={"my_tool": contract})

        result = guard.check("my_tool", {"x": 1})

        assert result.verdict == GuardVerdict.ALLOW
        assert "No preconditions" in result.reason

    def test_check_preconditions_satisfied(self):
        """Test check when all preconditions are satisfied."""
        contract = ToolContract(requires=["n > 0", "n < 100"])
        guard = ContractGuard(contracts={"factorial": contract})

        result = guard.check("factorial", {"n": 50})

        assert result.verdict == GuardVerdict.ALLOW
        assert "satisfied" in result.reason

    def test_check_preconditions_violated_non_strict(self):
        """Test check when preconditions violated in non-strict mode."""
        contract = ToolContract(requires=["n > 0"])
        guard = ContractGuard(contracts={"factorial": contract}, strict=False)

        result = guard.check("factorial", {"n": -5})

        assert result.verdict == GuardVerdict.WARN
        assert "warning" in result.reason.lower()

    def test_check_preconditions_violated_strict(self):
        """Test check when preconditions violated in strict mode."""
        contract = ToolContract(requires=["n > 0"])
        guard = ContractGuard(contracts={"factorial": contract}, strict=True)

        result = guard.check("factorial", {"n": -5})

        assert result.verdict == GuardVerdict.BLOCK
        assert "failed" in result.reason.lower()

    def test_check_with_namespace(self):
        """Test check with namespace."""
        contract = ToolContract(requires=["x > 0"])
        guard = ContractGuard(contracts={"math.add": contract})

        result = guard.check("add", {"x": 10}, namespace="math")

        assert result.verdict == GuardVerdict.ALLOW

    def test_check_multiple_violations(self):
        """Test check with multiple precondition violations."""
        contract = ToolContract(requires=["x > 0", "y > 0"])
        guard = ContractGuard(contracts={"my_tool": contract}, strict=True)

        result = guard.check("my_tool", {"x": -1, "y": -2})

        assert result.verdict == GuardVerdict.BLOCK
        # Both violations should be reported
        assert "violations" in result.details


class TestContractGuardCheckOutput:
    """Tests for check_output method (postcondition validation)."""

    def test_check_output_no_contract(self):
        """Test check_output when no contract exists."""
        guard = ContractGuard()

        result = guard.check_output("unknown_tool", {}, 42)

        assert result.verdict == GuardVerdict.ALLOW
        assert "No contract defined" in result.reason

    def test_check_output_no_postconditions(self):
        """Test check_output when contract has no postconditions."""
        contract = ToolContract(requires=["n > 0"])  # No ensures
        guard = ContractGuard(contracts={"my_tool": contract})

        result = guard.check_output("my_tool", {"n": 1}, 42)

        assert result.verdict == GuardVerdict.ALLOW
        assert "No postconditions" in result.reason

    def test_check_output_postconditions_satisfied(self):
        """Test check_output when all postconditions are satisfied."""
        contract = ToolContract(ensures=["result >= 0"])
        guard = ContractGuard(contracts={"factorial": contract})

        result = guard.check_output("factorial", {"n": 5}, 120)

        assert result.verdict == GuardVerdict.ALLOW
        assert "satisfied" in result.reason

    def test_check_output_postconditions_violated_non_strict(self):
        """Test check_output when postconditions violated in non-strict mode."""
        contract = ToolContract(ensures=["result >= 0"])
        guard = ContractGuard(contracts={"factorial": contract}, strict=False)

        result = guard.check_output("factorial", {"n": 5}, -1)

        assert result.verdict == GuardVerdict.WARN
        assert "warning" in result.reason.lower()

    def test_check_output_postconditions_violated_strict(self):
        """Test check_output when postconditions violated in strict mode."""
        contract = ToolContract(ensures=["result >= 0"])
        guard = ContractGuard(contracts={"factorial": contract}, strict=True)

        result = guard.check_output("factorial", {"n": 5}, -1)

        assert result.verdict == GuardVerdict.BLOCK
        assert "failed" in result.reason.lower()
        assert "result_type" in result.details


# --------------------------------------------------------------------------- #
# ContractAwareGuardChain Tests
# --------------------------------------------------------------------------- #
class TestContractAwareGuardChainInit:
    """Tests for ContractAwareGuardChain initialization."""

    def test_basic_init(self):
        """Test basic initialization."""
        chain = ContractAwareGuardChain()

        assert chain._guards == []
        assert chain._contract_guard is not None

    def test_init_with_guards(self):
        """Test initialization with guards."""
        guards = [AllowGuard(), AllowGuard()]
        chain = ContractAwareGuardChain(guards=guards)

        assert len(chain._guards) == 2

    def test_init_with_contracts(self):
        """Test initialization with contracts."""
        contracts = {"my_tool": ToolContract(requires=["x > 0"])}
        chain = ContractAwareGuardChain(contracts=contracts)

        # Contract should be registered
        assert chain._contract_guard.get_contract("my_tool") is not None

    def test_init_with_strict_contracts(self):
        """Test initialization with strict contracts."""
        chain = ContractAwareGuardChain(strict_contracts=True)

        assert chain._contract_guard._strict is True

    def test_init_with_named_guard(self):
        """Test initialization with guard that has name attribute."""
        guard = NamedGuard()
        chain = ContractAwareGuardChain(guards=[guard])

        # Guard should be added with its name
        assert len(chain._guards) == 1


class TestContractAwareGuardChainRegisterContract:
    """Tests for register_contract method."""

    def test_register_contract(self):
        """Test registering a contract."""
        chain = ContractAwareGuardChain()
        contract = ToolContract(requires=["x > 0"])

        chain.register_contract("my_tool", contract)

        assert chain._contract_guard.get_contract("my_tool") is contract


class TestContractAwareGuardChainCheck:
    """Tests for check method."""

    def test_check_passes_all_guards(self):
        """Test check when all guards pass."""
        guards = [AllowGuard(), AllowGuard()]
        chain = ContractAwareGuardChain(guards=guards)

        result = chain.check("my_tool", {"x": 1})

        assert result.verdict == GuardVerdict.ALLOW

    def test_check_fails_on_contract_violation(self):
        """Test check fails on contract violation."""
        contracts = {"my_tool": ToolContract(requires=["x > 0"])}
        chain = ContractAwareGuardChain(contracts=contracts, strict_contracts=True)

        result = chain.check("my_tool", {"x": -1})

        assert result.verdict == GuardVerdict.BLOCK

    def test_check_fails_on_guard_block(self):
        """Test check fails when a guard blocks."""
        guards = [AllowGuard(), BlockGuard()]
        chain = ContractAwareGuardChain(guards=guards)

        result = chain.check("my_tool", {"x": 1})

        assert result.verdict == GuardVerdict.BLOCK


class TestContractAwareGuardChainCheckOutput:
    """Tests for check_output method."""

    def test_check_output_passes(self):
        """Test check_output when all checks pass."""
        chain = ContractAwareGuardChain()

        result = chain.check_output("my_tool", {}, 42)

        assert result.verdict == GuardVerdict.ALLOW

    def test_check_output_fails_on_contract(self):
        """Test check_output fails on contract postcondition violation."""
        contracts = {"my_tool": ToolContract(ensures=["result >= 0"])}
        chain = ContractAwareGuardChain(contracts=contracts, strict_contracts=True)

        result = chain.check_output("my_tool", {}, -1)

        assert result.verdict == GuardVerdict.BLOCK

    def test_check_output_fails_on_guard(self):
        """Test check_output fails when guard blocks output."""
        guards = [OutputBlockGuard()]
        chain = ContractAwareGuardChain(guards=guards)

        result = chain.check_output("my_tool", {}, 42)

        assert result.verdict == GuardVerdict.BLOCK

    def test_check_output_contract_checked_first(self):
        """Test that contract is checked before other guards."""
        contracts = {"my_tool": ToolContract(ensures=["result >= 0"])}
        guards = [OutputBlockGuard()]
        chain = ContractAwareGuardChain(guards=guards, contracts=contracts, strict_contracts=True)

        result = chain.check_output("my_tool", {}, -1)

        # Contract failure should be returned, not output guard failure
        assert result.verdict == GuardVerdict.BLOCK
        assert "postcondition" in result.reason.lower()
