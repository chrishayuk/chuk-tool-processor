# chuk_tool_processor/guards/contract_guard.py
"""
ContractGuard: Guard that enforces tool contracts.

This guard validates preconditions before execution and postconditions
after execution, based on the ToolContract attached to tools.

Example:
    >>> guard = ContractGuard(registry)
    >>> result = guard.check("factorial", {"n": -5})
    >>> # Returns BLOCK because n > 0 precondition fails
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chuk_tool_processor.guards.base import BaseGuard, GuardResult, GuardVerdict
from chuk_tool_processor.models.tool_contract import ToolContract

if TYPE_CHECKING:
    from chuk_tool_processor.registry.interface import ToolRegistryInterface


class ContractGuard(BaseGuard):
    """
    Guard that enforces tool contracts (pre/post conditions).

    ContractGuard looks up the contract attached to a tool and validates:
    - Preconditions before execution (in check())
    - Postconditions after execution (in check_output())

    If a tool has no contract, the guard allows execution.

    Example:
        >>> guard = ContractGuard(registry, strict=True)
        >>> result = guard.check("calculator.divide", {"a": 10, "b": 0})
        >>> # If contract has requires=["b != 0"], returns BLOCK
    """

    def __init__(
        self,
        registry: ToolRegistryInterface | None = None,
        contracts: dict[str, ToolContract] | None = None,
        strict: bool = False,
    ):
        """
        Initialize contract guard.

        Args:
            registry: Tool registry to look up tool classes/instances
            contracts: Optional dict mapping tool names to contracts
            strict: If True, BLOCK on any violation. If False, WARN only.
        """
        self._registry = registry
        self._contracts = contracts or {}
        self._strict = strict

    def register_contract(self, tool_name: str, contract: ToolContract) -> None:
        """Register a contract for a tool."""
        self._contracts[tool_name] = contract

    def get_contract(self, tool_name: str, namespace: str = "default") -> ToolContract | None:
        """
        Get the contract for a tool.

        Looks up in order:
        1. Explicit contracts dict
        2. Contract attached to tool class via decorator
        """
        # Check explicit contracts
        full_name = f"{namespace}.{tool_name}" if namespace != "default" else tool_name
        if full_name in self._contracts:
            return self._contracts[full_name]
        if tool_name in self._contracts:
            return self._contracts[tool_name]

        # Note: checking tool class for attached contract would need to be async
        # in real use since registry.get_tool is async. For guard checks,
        # contracts should be pre-registered via register_contract().

        return None

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        namespace: str = "default",
    ) -> GuardResult:
        """
        Check preconditions before execution.

        Args:
            tool_name: Name of the tool
            arguments: Arguments passed to the tool
            namespace: Tool namespace

        Returns:
            GuardResult with verdict
        """
        contract = self.get_contract(tool_name, namespace)

        if contract is None:
            return self.allow("No contract defined")

        if not contract.requires:
            return self.allow("No preconditions")

        violations = contract.check_preconditions(arguments)

        if not violations:
            return self.allow("All preconditions satisfied")

        # Format violation messages
        messages = [v.message for v in violations]
        details = {
            "violations": [v.model_dump() for v in violations],
            "contract": tool_name,
        }

        if self._strict:
            return self.block(
                f"Contract precondition failed: {'; '.join(messages)}",
                **details,
            )
        else:
            return self.warn(
                f"Contract precondition warning: {'; '.join(messages)}",
                **details,
            )

    def check_output(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        namespace: str = "default",
    ) -> GuardResult:
        """
        Check postconditions after execution.

        Args:
            tool_name: Name of the tool
            arguments: Arguments that were passed
            result: The result returned by the tool
            namespace: Tool namespace

        Returns:
            GuardResult with verdict
        """
        contract = self.get_contract(tool_name, namespace)

        if contract is None:
            return self.allow("No contract defined")

        if not contract.ensures:
            return self.allow("No postconditions")

        violations = contract.check_postconditions(arguments, result)

        if not violations:
            return self.allow("All postconditions satisfied")

        messages = [v.message for v in violations]
        details = {
            "violations": [v.model_dump() for v in violations],
            "contract": tool_name,
            "result_type": type(result).__name__,
        }

        if self._strict:
            return self.block(
                f"Contract postcondition failed: {'; '.join(messages)}",
                **details,
            )
        else:
            return self.warn(
                f"Contract postcondition warning: {'; '.join(messages)}",
                **details,
            )


class ContractAwareGuardChain:
    """
    Guard chain that includes contract validation.

    This is a convenience class that wraps a guard chain and adds
    contract validation at the appropriate points.

    Example:
        >>> chain = ContractAwareGuardChain(
        ...     guards=[SchemaGuard(), SensitiveDataGuard()],
        ...     contracts={"factorial": ToolContract(requires=["n > 0"])},
        ... )
        >>> result = chain.check("factorial", {"n": -1})
    """

    def __init__(
        self,
        guards: list[BaseGuard] | None = None,
        contracts: dict[str, ToolContract] | None = None,
        strict_contracts: bool = False,
    ):
        """
        Initialize contract-aware guard chain.

        Args:
            guards: List of guards to run
            contracts: Dict of tool name -> contract
            strict_contracts: Whether to BLOCK or WARN on contract violations
        """
        from chuk_tool_processor.guards.chain import GuardChain

        self._contract_guard = ContractGuard(contracts=contracts, strict=strict_contracts)
        self._guards = guards or []
        # Build list of named guard tuples for GuardChain
        guard_tuples: list[tuple[str, BaseGuard]] = [("contract", self._contract_guard)]
        for i, guard in enumerate(self._guards):
            guard_name = getattr(guard, "name", f"guard_{i}")
            guard_tuples.append((guard_name, guard))
        self._chain = GuardChain(guards=guard_tuples)

    def register_contract(self, tool_name: str, contract: ToolContract) -> None:
        """Register a contract for a tool."""
        self._contract_guard.register_contract(tool_name, contract)

    def check(self, tool_name: str, arguments: dict[str, Any]) -> GuardResult:
        """Run all guards including contract validation."""
        chain_result = self._chain.check_all(tool_name, arguments)
        return GuardResult(
            verdict=chain_result.final_verdict,
            reason=chain_result.final_reason,
            repaired_args=chain_result.repaired_args,
        )

    def check_output(self, tool_name: str, arguments: dict[str, Any], result: Any) -> GuardResult:
        """Run output guards including contract postconditions."""
        # First check contract postconditions
        contract_result = self._contract_guard.check_output(tool_name, arguments, result)
        if contract_result.blocked:
            return contract_result

        # Then check other guards
        for guard in self._guards:
            if hasattr(guard, "check_output"):
                guard_result = guard.check_output(tool_name, arguments, result)
                if guard_result.blocked:
                    return guard_result

        return GuardResult(verdict=GuardVerdict.ALLOW)
