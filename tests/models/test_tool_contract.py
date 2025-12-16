# tests/models/test_tool_contract.py
"""
Tests for ToolContract and related functionality.
"""

import pytest

from chuk_tool_processor.models.tool_contract import (
    ContractViolation,
    Determinism,
    LatencyHint,
    ResourceRequirement,
    SideEffectClass,
    ToolContract,
    contract,
    get_contract,
)


# --------------------------------------------------------------------------- #
# ContractViolation Tests
# --------------------------------------------------------------------------- #
class TestContractViolation:
    """Tests for ContractViolation model."""

    def test_basic_violation(self):
        """Test creating basic violation."""
        violation = ContractViolation(
            condition="n > 0",
            phase="precondition",
            message="Precondition failed: n > 0",
        )
        assert violation.condition == "n > 0"
        assert violation.phase == "precondition"
        assert violation.message == "Precondition failed: n > 0"

    def test_violation_with_actual_value(self):
        """Test violation with actual value."""
        violation = ContractViolation(
            condition="n > 0",
            phase="precondition",
            message="Failed",
            actual_value=-5,
        )
        assert violation.actual_value == -5


# --------------------------------------------------------------------------- #
# ToolContract Tests
# --------------------------------------------------------------------------- #
class TestToolContract:
    """Tests for ToolContract model."""

    def test_basic_contract(self):
        """Test creating basic contract."""
        contract = ToolContract()
        assert contract.requires == []
        assert contract.ensures == []
        assert contract.determinism == Determinism.IMPURE

    def test_contract_with_conditions(self):
        """Test contract with pre/post conditions."""
        tc = ToolContract(
            requires=["n > 0", "n < 100"],
            ensures=["result >= 0"],
        )
        assert len(tc.requires) == 2
        assert len(tc.ensures) == 1

    def test_validate_conditions_valid(self):
        """Test condition validation with valid expressions."""
        tc = ToolContract(
            requires=["x > 0", "isinstance(y, str)", "len(items) <= 10"],
        )
        assert len(tc.requires) == 3

    def test_validate_conditions_invalid(self):
        """Test condition validation with invalid syntax."""
        with pytest.raises(ValueError, match="Invalid condition syntax"):
            ToolContract(requires=["x >"])

    def test_is_pure(self):
        """Test is_pure property."""
        pure_contract = ToolContract(
            determinism=Determinism.PURE,
            side_effects=SideEffectClass.NONE,
        )
        assert pure_contract.is_pure is True

        impure_contract = ToolContract(
            determinism=Determinism.IMPURE,
            side_effects=SideEffectClass.NONE,
        )
        assert impure_contract.is_pure is False

        side_effect_contract = ToolContract(
            determinism=Determinism.PURE,
            side_effects=SideEffectClass.LOCAL,
        )
        assert side_effect_contract.is_pure is False

    def test_is_safe_to_cache(self):
        """Test is_safe_to_cache property."""
        pure = ToolContract(determinism=Determinism.PURE)
        assert pure.is_safe_to_cache is True

        impure = ToolContract(determinism=Determinism.IMPURE)
        assert impure.is_safe_to_cache is False

    def test_is_safe_to_retry(self):
        """Test is_safe_to_retry property."""
        idempotent = ToolContract(idempotent=True)
        assert idempotent.is_safe_to_retry is True

        no_effects = ToolContract(side_effects=SideEffectClass.NONE)
        assert no_effects.is_safe_to_retry is True

        not_safe = ToolContract(
            idempotent=False,
            side_effects=SideEffectClass.REMOTE,
        )
        assert not_safe.is_safe_to_retry is False

    def test_resource_requirements(self):
        """Test resource_requirements property."""
        tc = ToolContract(
            requires_network=True,
            requires_filesystem=True,
            requires_subprocess=True,
            requires_gpu=True,
            max_memory_mb=2048,  # > 1024
        )
        reqs = tc.resource_requirements

        assert ResourceRequirement.NETWORK in reqs
        assert ResourceRequirement.FILESYSTEM in reqs
        assert ResourceRequirement.SUBPROCESS in reqs
        assert ResourceRequirement.GPU in reqs
        assert ResourceRequirement.HIGH_MEMORY in reqs

    def test_resource_requirements_low_memory(self):
        """Test resource_requirements with low memory."""
        tc = ToolContract(max_memory_mb=512)
        reqs = tc.resource_requirements
        assert ResourceRequirement.HIGH_MEMORY not in reqs

    def test_check_preconditions_satisfied(self):
        """Test check_preconditions when satisfied."""
        tc = ToolContract(requires=["n > 0", "n < 100"])
        violations = tc.check_preconditions({"n": 50})
        assert len(violations) == 0

    def test_check_preconditions_violated(self):
        """Test check_preconditions when violated."""
        tc = ToolContract(requires=["n > 0"])
        violations = tc.check_preconditions({"n": -5})

        assert len(violations) == 1
        assert violations[0].phase == "precondition"
        assert violations[0].actual_value == -5

    def test_check_preconditions_eval_error(self):
        """Test check_preconditions with evaluation error."""
        tc = ToolContract(requires=["n > 0"])
        # Missing variable
        violations = tc.check_preconditions({"x": 5})

        assert len(violations) == 1
        assert "evaluation error" in violations[0].message.lower()

    def test_check_postconditions_satisfied(self):
        """Test check_postconditions when satisfied."""
        tc = ToolContract(ensures=["result >= 0"])
        violations = tc.check_postconditions({"n": 5}, 120)
        assert len(violations) == 0

    def test_check_postconditions_violated(self):
        """Test check_postconditions when violated."""
        tc = ToolContract(ensures=["result >= 0"])
        violations = tc.check_postconditions({"n": 5}, -1)

        assert len(violations) == 1
        assert violations[0].phase == "postcondition"
        assert violations[0].actual_value == -1

    def test_check_postconditions_eval_error(self):
        """Test check_postconditions with evaluation error."""
        tc = ToolContract(ensures=["result.value > 0"])
        # result doesn't have .value attribute
        violations = tc.check_postconditions({}, 42)

        assert len(violations) == 1
        assert "evaluation error" in violations[0].message.lower()

    def test_check_postconditions_uses_arguments(self):
        """Test check_postconditions has access to arguments."""
        tc = ToolContract(ensures=["result <= max_val"])
        violations = tc.check_postconditions({"max_val": 100}, 50)
        assert len(violations) == 0

    def test_validate_contract(self):
        """Test validate_contract method."""
        tc = ToolContract(
            requires=["n > 0"],
            ensures=["result >= 0"],
        )
        violations = tc.validate_contract({"n": -5}, result=50)

        # Should have precondition violation
        assert len(violations) == 1
        assert violations[0].phase == "precondition"

    def test_validate_contract_without_result(self):
        """Test validate_contract without result."""
        tc = ToolContract(requires=["n > 0"])
        violations = tc.validate_contract({"n": -5})
        assert len(violations) == 1

    def test_to_llm_description_pure(self):
        """Test to_llm_description for pure tool."""
        tc = ToolContract(
            determinism=Determinism.PURE,
            cost_hint=1,
            latency_hint=LatencyHint.INSTANT,
            side_effects=SideEffectClass.NONE,
            requires=["n > 0"],
        )
        desc = tc.to_llm_description()

        assert "deterministic" in desc
        assert "instant" in desc.lower()
        assert "safe to retry" in desc.lower()
        assert "n > 0" in desc

    def test_to_llm_description_external(self):
        """Test to_llm_description for external tool."""
        tc = ToolContract(
            determinism=Determinism.EXTERNAL,
        )
        desc = tc.to_llm_description()
        assert "external state" in desc.lower()

    def test_to_llm_description_destructive(self):
        """Test to_llm_description for destructive tool."""
        tc = ToolContract(
            side_effects=SideEffectClass.DESTRUCTIVE,
        )
        desc = tc.to_llm_description()
        assert "destructive" in desc.lower()

    def test_to_llm_description_remote(self):
        """Test to_llm_description for remote tool."""
        tc = ToolContract(
            side_effects=SideEffectClass.REMOTE,
        )
        desc = tc.to_llm_description()
        assert "remote" in desc.lower()

    def test_to_llm_description_cost_levels(self):
        """Test to_llm_description with various cost levels."""
        for cost in [0, 1, 2, 5, 10, 25, 50, 100]:
            tc = ToolContract(cost_hint=cost)
            desc = tc.to_llm_description()
            assert "Cost:" in desc

    def test_to_llm_description_latency_levels(self):
        """Test to_llm_description with various latency levels."""
        for hint in LatencyHint:
            tc = ToolContract(latency_hint=hint)
            desc = tc.to_llm_description()
            assert "Latency:" in desc

    def test_to_dict(self):
        """Test to_dict export."""
        tc = ToolContract(requires=["n > 0"])
        d = tc.to_dict()
        assert "requires" in d
        assert d["requires"] == ["n > 0"]


# --------------------------------------------------------------------------- #
# Decorator Tests
# --------------------------------------------------------------------------- #
class TestContractDecorator:
    """Tests for @contract decorator."""

    def test_basic_decorator(self):
        """Test basic decorator usage."""

        @contract(requires=["x > 0"])
        class TestTool:
            pass

        assert hasattr(TestTool, "_tool_contract")
        assert TestTool._tool_contract.requires == ["x > 0"]

    def test_decorator_with_all_options(self):
        """Test decorator with all options."""

        @contract(
            requires=["n > 0"],
            ensures=["result >= 0"],
            determinism=Determinism.PURE,
            cost_hint=5,
            latency_hint=LatencyHint.FAST,
            side_effects=SideEffectClass.NONE,
            idempotent=True,
            requires_network=True,
            requires_filesystem=True,
        )
        class TestTool:
            pass

        tc = TestTool._tool_contract
        assert tc.requires == ["n > 0"]
        assert tc.ensures == ["result >= 0"]
        assert tc.determinism == Determinism.PURE
        assert tc.cost_hint == 5
        assert tc.idempotent is True
        assert tc.requires_network is True

    def test_decorator_on_function(self):
        """Test decorator on function."""

        @contract(requires=["a > 0"])
        def add(a, b):
            return a + b

        assert hasattr(add, "_tool_contract")


class TestGetContract:
    """Tests for get_contract function."""

    def test_get_contract_from_class(self):
        """Test getting contract from decorated class."""

        @contract(requires=["x > 0"])
        class TestTool:
            pass

        tc = get_contract(TestTool)
        assert tc is not None
        assert tc.requires == ["x > 0"]

    def test_get_contract_from_instance(self):
        """Test getting contract from instance."""

        @contract(requires=["x > 0"])
        class TestTool:
            pass

        instance = TestTool()
        tc = get_contract(instance)
        assert tc is not None
        assert tc.requires == ["x > 0"]

    def test_get_contract_none(self):
        """Test getting contract from undecorated class."""

        class TestTool:
            pass

        tc = get_contract(TestTool)
        assert tc is None

    def test_get_contract_invalid_attribute(self):
        """Test getting contract when _tool_contract is not a ToolContract."""

        class TestTool:
            _tool_contract = "not a contract"

        tc = get_contract(TestTool)
        assert tc is None


# --------------------------------------------------------------------------- #
# Enum Tests
# --------------------------------------------------------------------------- #
class TestEnums:
    """Tests for enum values."""

    def test_determinism_values(self):
        """Test Determinism enum values."""
        assert Determinism.PURE.value == "pure"
        assert Determinism.IMPURE.value == "impure"
        assert Determinism.EXTERNAL.value == "external"

    def test_latency_hint_values(self):
        """Test LatencyHint enum values."""
        assert LatencyHint.INSTANT.value == "instant"
        assert LatencyHint.FAST.value == "fast"
        assert LatencyHint.MODERATE.value == "moderate"
        assert LatencyHint.SLOW.value == "slow"
        assert LatencyHint.VERY_SLOW.value == "very_slow"

    def test_side_effect_class_values(self):
        """Test SideEffectClass enum values."""
        assert SideEffectClass.NONE.value == "none"
        assert SideEffectClass.LOCAL.value == "local"
        assert SideEffectClass.REMOTE.value == "remote"
        assert SideEffectClass.DESTRUCTIVE.value == "destructive"

    def test_resource_requirement_values(self):
        """Test ResourceRequirement enum values."""
        assert ResourceRequirement.NETWORK.value == "network"
        assert ResourceRequirement.FILESYSTEM.value == "filesystem"
        assert ResourceRequirement.GPU.value == "gpu"
        assert ResourceRequirement.HIGH_MEMORY.value == "high_memory"
        assert ResourceRequirement.SUBPROCESS.value == "subprocess"
