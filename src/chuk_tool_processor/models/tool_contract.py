# chuk_tool_processor/models/tool_contract.py
"""
ToolContract: Pre/post conditions and execution hints for tool reasoning.

This module provides a way to express tool semantics that both:
- Guards can validate at runtime
- Planners/agents can reason about before calling

Contracts turn tools from opaque functions into typed APIs that LLMs
can understand and reason about.

Example:
    >>> contract = ToolContract(
    ...     requires=["n > 0", "n <= 1000"],
    ...     ensures=["result >= 0"],
    ...     determinism=Determinism.PURE,
    ...     cost_hint=1,
    ...     side_effects=SideEffectClass.NONE,
    ... )
    >>> # Planner knows: this is cheap, pure, safe to cache/retry
    >>> # Guard knows: validate n > 0 before calling
"""

from __future__ import annotations

import re
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

_T = TypeVar("_T")


class Determinism(str, Enum):
    """Determinism classification for tools."""

    PURE = "pure"  # Same inputs always produce same outputs
    IMPURE = "impure"  # May vary (time, random, etc.)
    EXTERNAL = "external"  # Depends on external state (APIs, DBs)


class LatencyHint(str, Enum):
    """Expected latency classification."""

    INSTANT = "instant"  # < 10ms (math, local lookups)
    FAST = "fast"  # 10-100ms (cached API, simple DB)
    MODERATE = "moderate"  # 100ms-1s (API calls, moderate processing)
    SLOW = "slow"  # 1-10s (complex processing, multiple APIs)
    VERY_SLOW = "very_slow"  # > 10s (ML inference, large data)


class SideEffectClass(str, Enum):
    """Classification of tool side effects."""

    NONE = "none"  # Pure computation, no side effects
    LOCAL = "local"  # Affects local state (memory, files)
    REMOTE = "remote"  # Affects remote state (APIs, DBs)
    DESTRUCTIVE = "destructive"  # Potentially irreversible (delete, overwrite)


class ResourceRequirement(str, Enum):
    """Resource requirements for execution."""

    NETWORK = "network"  # Requires network access
    FILESYSTEM = "filesystem"  # Requires filesystem access
    GPU = "gpu"  # Requires GPU
    HIGH_MEMORY = "high_memory"  # Requires significant memory
    SUBPROCESS = "subprocess"  # Spawns subprocesses


class ContractViolation(BaseModel):
    """Details of a contract violation."""

    model_config = ConfigDict(frozen=True)

    condition: str = Field(..., description="The condition that was violated")
    phase: str = Field(..., description="'precondition' or 'postcondition'")
    message: str = Field(..., description="Human-readable violation message")
    actual_value: Any | None = Field(default=None, description="The actual value that violated the condition")


class ToolContract(BaseModel):
    """
    Pre/post conditions and execution hints for tool reasoning.

    Contracts express tool semantics in a way that:
    - Guards can validate at runtime
    - Planners can reason about before calling
    - Caching can use to determine invalidation
    - Retry logic can use to determine safety

    The condition syntax supports simple expressions:
        - Comparisons: "n > 0", "len(items) <= 100"
        - Type checks: "isinstance(x, str)"
        - Membership: "status in ['active', 'pending']"
        - Boolean: "enabled", "not disabled"

    Example:
        >>> contract = ToolContract(
        ...     requires=["n > 0", "n <= 1000"],
        ...     ensures=["result >= 0", "result <= n"],
        ...     determinism=Determinism.PURE,
        ...     cost_hint=1,
        ...     latency_hint=LatencyHint.INSTANT,
        ...     side_effects=SideEffectClass.NONE,
        ... )

    For complex conditions, use guard classes directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ------------------------------------------------------------------ #
    # Preconditions (evaluated before execution)
    # ------------------------------------------------------------------ #
    requires: list[str] = Field(
        default_factory=list,
        description="Preconditions that must hold before execution. "
        "Simple Python expressions over argument names. "
        "Example: ['n > 0', 'units in [\"m\", \"ft\"]']",
    )

    # ------------------------------------------------------------------ #
    # Postconditions (evaluated after execution)
    # ------------------------------------------------------------------ #
    ensures: list[str] = Field(
        default_factory=list,
        description="Postconditions that must hold after execution. "
        "Simple Python expressions over 'result' and argument names. "
        "Example: ['result >= 0', 'len(result) <= max_length']",
    )

    # ------------------------------------------------------------------ #
    # Execution characteristics
    # ------------------------------------------------------------------ #
    determinism: Determinism = Field(
        default=Determinism.IMPURE,
        description="Whether the tool produces deterministic outputs",
    )

    cost_hint: int = Field(
        default=1,
        ge=0,
        le=100,
        description="Abstract cost units (0=free, 1=cheap, 10=moderate, 50=expensive, 100=very expensive). "
        "Used for planning and budget enforcement.",
    )

    latency_hint: LatencyHint = Field(
        default=LatencyHint.MODERATE,
        description="Expected latency classification",
    )

    # ------------------------------------------------------------------ #
    # Side effects
    # ------------------------------------------------------------------ #
    side_effects: SideEffectClass = Field(
        default=SideEffectClass.NONE,
        description="Classification of side effects",
    )

    idempotent: bool = Field(
        default=False,
        description="Whether multiple calls with same args have same effect as one call. Important for retry safety.",
    )

    # ------------------------------------------------------------------ #
    # Resource requirements
    # ------------------------------------------------------------------ #
    requires_network: bool = Field(default=False, description="Whether the tool needs network access")
    requires_filesystem: bool = Field(default=False, description="Whether the tool needs filesystem access")
    requires_subprocess: bool = Field(default=False, description="Whether the tool spawns subprocesses")
    requires_gpu: bool = Field(default=False, description="Whether the tool needs GPU")

    max_memory_mb: int | None = Field(
        default=None,
        ge=0,
        description="Maximum memory usage in megabytes (for resource planning)",
    )

    max_duration_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Maximum expected duration in seconds (for timeout planning)",
    )

    # ------------------------------------------------------------------ #
    # Concurrency
    # ------------------------------------------------------------------ #
    max_concurrent: int | None = Field(
        default=None,
        ge=1,
        description="Maximum concurrent executions allowed (None=unlimited)",
    )

    thread_safe: bool = Field(
        default=True,
        description="Whether the tool is safe to call from multiple threads",
    )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    @field_validator("requires", "ensures")
    @classmethod
    def validate_conditions(cls, v: list[str]) -> list[str]:
        """Validate that conditions are syntactically valid."""
        for condition in v:
            try:
                # Try to compile as Python expression
                compile(condition, "<condition>", "eval")
            except SyntaxError as e:
                raise ValueError(f"Invalid condition syntax '{condition}': {e}") from e
        return v

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #
    @property
    def is_pure(self) -> bool:
        """Check if tool is pure (deterministic with no side effects)."""
        return self.determinism == Determinism.PURE and self.side_effects == SideEffectClass.NONE

    @property
    def is_safe_to_cache(self) -> bool:
        """Check if results can be safely cached."""
        return self.determinism == Determinism.PURE

    @property
    def is_safe_to_retry(self) -> bool:
        """Check if tool is safe to retry on failure."""
        return self.idempotent or self.side_effects == SideEffectClass.NONE

    @property
    def resource_requirements(self) -> set[ResourceRequirement]:
        """Get set of resource requirements."""
        reqs: set[ResourceRequirement] = set()
        if self.requires_network:
            reqs.add(ResourceRequirement.NETWORK)
        if self.requires_filesystem:
            reqs.add(ResourceRequirement.FILESYSTEM)
        if self.requires_subprocess:
            reqs.add(ResourceRequirement.SUBPROCESS)
        if self.requires_gpu:
            reqs.add(ResourceRequirement.GPU)
        if self.max_memory_mb and self.max_memory_mb > 1024:
            reqs.add(ResourceRequirement.HIGH_MEMORY)
        return reqs

    # ------------------------------------------------------------------ #
    # Condition evaluation
    # ------------------------------------------------------------------ #
    def check_preconditions(self, arguments: dict[str, Any]) -> list[ContractViolation]:
        """
        Evaluate preconditions against arguments.

        Args:
            arguments: Tool arguments to validate

        Returns:
            List of violations (empty if all preconditions pass)
        """
        violations: list[ContractViolation] = []

        for condition in self.requires:
            try:
                # Evaluate condition with arguments as locals (intentional, uses restricted builtins)
                result = eval(condition, {"__builtins__": _SAFE_BUILTINS}, arguments)  # noqa: S307 # nosec B307
                if not result:
                    violations.append(
                        ContractViolation(
                            condition=condition,
                            phase="precondition",
                            message=f"Precondition failed: {condition}",
                            actual_value=_extract_relevant_value(condition, arguments),
                        )
                    )
            except Exception as e:
                # Condition evaluation failed (missing var, type error, etc.)
                violations.append(
                    ContractViolation(
                        condition=condition,
                        phase="precondition",
                        message=f"Precondition evaluation error: {e}",
                    )
                )

        return violations

    def check_postconditions(
        self,
        arguments: dict[str, Any],
        result: Any,
    ) -> list[ContractViolation]:
        """
        Evaluate postconditions against result.

        Args:
            arguments: Tool arguments (for context)
            result: Tool execution result

        Returns:
            List of violations (empty if all postconditions pass)
        """
        violations: list[ContractViolation] = []

        # Build evaluation context with both arguments and result
        context = {**arguments, "result": result}

        for condition in self.ensures:
            try:
                # Intentional eval with restricted builtins for postcondition checking
                check_result = eval(condition, {"__builtins__": _SAFE_BUILTINS}, context)  # noqa: S307 # nosec B307
                if not check_result:
                    violations.append(
                        ContractViolation(
                            condition=condition,
                            phase="postcondition",
                            message=f"Postcondition failed: {condition}",
                            actual_value=result if "result" in condition else None,
                        )
                    )
            except Exception as e:
                violations.append(
                    ContractViolation(
                        condition=condition,
                        phase="postcondition",
                        message=f"Postcondition evaluation error: {e}",
                    )
                )

        return violations

    def validate_contract(self, arguments: dict[str, Any], result: Any | None = None) -> list[ContractViolation]:
        """
        Validate both pre and postconditions.

        Args:
            arguments: Tool arguments
            result: Tool result (if checking postconditions)

        Returns:
            All violations found
        """
        violations = self.check_preconditions(arguments)
        if result is not None:
            violations.extend(self.check_postconditions(arguments, result))
        return violations

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def to_llm_description(self) -> str:
        """
        Generate a description suitable for LLM context.

        Returns a string that helps the LLM understand:
        - What constraints apply
        - What to expect from this tool
        - When it's safe to use
        """
        parts: list[str] = []

        # Determinism
        if self.determinism == Determinism.PURE:
            parts.append("This tool is deterministic (same inputs always give same outputs).")
        elif self.determinism == Determinism.EXTERNAL:
            parts.append("This tool depends on external state (results may vary).")

        # Cost
        cost_desc = {
            0: "free",
            1: "very cheap",
            2: "cheap",
            5: "moderate cost",
            10: "moderately expensive",
            25: "expensive",
            50: "very expensive",
            100: "extremely expensive",
        }
        closest_cost = min(cost_desc.keys(), key=lambda x: abs(x - self.cost_hint))
        parts.append(f"Cost: {cost_desc[closest_cost]}.")

        # Latency
        latency_desc = {
            LatencyHint.INSTANT: "instant (< 10ms)",
            LatencyHint.FAST: "fast (10-100ms)",
            LatencyHint.MODERATE: "moderate (100ms-1s)",
            LatencyHint.SLOW: "slow (1-10s)",
            LatencyHint.VERY_SLOW: "very slow (> 10s)",
        }
        parts.append(f"Latency: {latency_desc[self.latency_hint]}.")

        # Side effects
        if self.side_effects == SideEffectClass.NONE:
            parts.append("No side effects.")
        elif self.side_effects == SideEffectClass.DESTRUCTIVE:
            parts.append("WARNING: May have destructive side effects.")
        elif self.side_effects == SideEffectClass.REMOTE:
            parts.append("Modifies remote state.")

        # Preconditions
        if self.requires:
            parts.append(f"Requires: {', '.join(self.requires)}")

        # Retry safety
        if self.is_safe_to_retry:
            parts.append("Safe to retry on failure.")

        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Export contract as dictionary."""
        return self.model_dump(exclude_none=True)


# ------------------------------------------------------------------ #
# Safe builtins for condition evaluation
# ------------------------------------------------------------------ #
_SAFE_BUILTINS: dict[str, Any] = {
    # Type checking
    "isinstance": isinstance,
    "type": type,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    # Collection operations
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "all": all,
    "any": any,
    "sorted": sorted,
    "reversed": reversed,
    # Math
    "abs": abs,
    "round": round,
    "pow": pow,
    # String operations
    "ord": ord,
    "chr": chr,
    # Boolean
    "True": True,
    "False": False,
    "None": None,
}


def _extract_relevant_value(condition: str, arguments: dict[str, Any]) -> Any | None:
    """Try to extract the relevant value from a condition for error reporting."""
    # Simple heuristic: find variable names in condition
    var_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
    for match in var_pattern.finditer(condition):
        var_name = match.group(1)
        if var_name in arguments:
            return arguments[var_name]
    return None


# ------------------------------------------------------------------ #
# Contract decorator
# ------------------------------------------------------------------ #
def contract(
    *,
    requires: list[str] | None = None,
    ensures: list[str] | None = None,
    determinism: Determinism = Determinism.IMPURE,
    cost_hint: int = 1,
    latency_hint: LatencyHint = LatencyHint.MODERATE,
    side_effects: SideEffectClass = SideEffectClass.NONE,
    idempotent: bool = False,
    requires_network: bool = False,
    requires_filesystem: bool = False,
) -> Callable[[_T], _T]:
    """
    Decorator to attach a contract to a tool class or function.

    Example:
        @contract(
            requires=["n > 0"],
            ensures=["result >= 0"],
            determinism=Determinism.PURE,
            cost_hint=1,
        )
        class FactorialTool(ValidatedTool):
            ...

    Args:
        requires: Preconditions
        ensures: Postconditions
        determinism: Determinism classification
        cost_hint: Cost units (0-100)
        latency_hint: Expected latency
        side_effects: Side effect classification
        idempotent: Whether tool is idempotent
        requires_network: Network requirement
        requires_filesystem: Filesystem requirement

    Returns:
        Decorated class with _tool_contract attribute
    """

    def decorator(cls_or_func: _T) -> _T:
        tool_contract = ToolContract(
            requires=requires or [],
            ensures=ensures or [],
            determinism=determinism,
            cost_hint=cost_hint,
            latency_hint=latency_hint,
            side_effects=side_effects,
            idempotent=idempotent,
            requires_network=requires_network,
            requires_filesystem=requires_filesystem,
        )
        cls_or_func._tool_contract = tool_contract  # type: ignore[attr-defined]
        return cls_or_func

    return decorator


def get_contract(tool: Any) -> ToolContract | None:
    """
    Get the contract attached to a tool, if any.

    Args:
        tool: Tool class or instance

    Returns:
        ToolContract or None
    """
    # Check instance
    if hasattr(tool, "_tool_contract"):
        contract_attr = tool._tool_contract
        if isinstance(contract_attr, ToolContract):
            return contract_attr

    # Check class
    tool_class = tool if isinstance(tool, type) else type(tool)
    if hasattr(tool_class, "_tool_contract"):
        contract_attr = tool_class._tool_contract
        if isinstance(contract_attr, ToolContract):
            return contract_attr

    return None
