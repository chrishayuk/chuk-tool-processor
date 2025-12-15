# chuk_tool_processor/guards/chain.py
"""Guard chain for composing and ordering multiple guards.

Provides a unified interface for running multiple guards in sequence.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult, GuardVerdict


class GuardChainResult(BaseModel):
    """Result from running a guard chain."""

    final_verdict: GuardVerdict
    final_reason: str = ""
    guard_results: list[tuple[str, GuardResult]] = Field(default_factory=list)
    stopped_at: str | None = None
    repaired_args: dict[str, Any] | None = None

    @property
    def allowed(self) -> bool:
        """Check if execution should proceed."""
        return self.final_verdict in (GuardVerdict.ALLOW, GuardVerdict.WARN)

    @property
    def blocked(self) -> bool:
        """Check if execution is blocked."""
        return self.final_verdict == GuardVerdict.BLOCK


class GuardChain:
    """Chain of guards to run in sequence.

    Guards are run in order. If any guard blocks, execution stops.
    Warnings are collected but don't stop execution.
    Repair verdicts can modify arguments for subsequent guards.

    Usage:
        chain = GuardChain([
            ("schema", SchemaStrictnessGuard()),
            ("sensitive", SensitiveDataGuard()),
            ("network", NetworkPolicyGuard()),
        ])

        result = chain.check_all("my_tool", {"url": "http://example.com"})
        if result.blocked:
            raise ValueError(result.final_reason)
    """

    def __init__(
        self,
        guards: list[tuple[str, BaseGuard]] | None = None,
    ) -> None:
        """Initialize with named guards.

        Args:
            guards: List of (name, guard) tuples in execution order
        """
        self._guards: list[tuple[str, BaseGuard]] = guards or []

    def add(self, name: str, guard: BaseGuard) -> GuardChain:
        """Add a guard to the chain. Returns self for chaining."""
        self._guards.append((name, guard))
        return self

    def insert(self, index: int, name: str, guard: BaseGuard) -> GuardChain:
        """Insert a guard at specific position. Returns self for chaining."""
        self._guards.insert(index, (name, guard))
        return self

    def remove(self, name: str) -> GuardChain:
        """Remove a guard by name. Returns self for chaining."""
        self._guards = [(n, g) for n, g in self._guards if n != name]
        return self

    def get(self, name: str) -> BaseGuard | None:
        """Get a guard by name."""
        for n, g in self._guards:
            if n == name:
                return g
        return None

    def check_all(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardChainResult:
        """Run all guards in sequence.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments to check

        Returns:
            GuardChainResult with final verdict and all guard results
        """
        results: list[tuple[str, GuardResult]] = []
        current_args = dict(arguments)
        repaired_args: dict[str, Any] | None = None

        for name, guard in self._guards:
            result = guard.check(tool_name, current_args)
            results.append((name, result))

            if result.verdict == GuardVerdict.BLOCK:
                return GuardChainResult(
                    final_verdict=GuardVerdict.BLOCK,
                    final_reason=result.reason,
                    guard_results=results,
                    stopped_at=name,
                )

            if result.verdict == GuardVerdict.REPAIR and result.repaired_args:
                current_args = result.repaired_args
                repaired_args = result.repaired_args

        # Determine final verdict from collected results
        has_warnings = any(r.verdict == GuardVerdict.WARN for _, r in results)
        final_verdict = GuardVerdict.WARN if has_warnings else GuardVerdict.ALLOW

        # Collect warning reasons
        warning_reasons = [r.reason for _, r in results if r.verdict == GuardVerdict.WARN and r.reason]
        final_reason = "; ".join(warning_reasons) if warning_reasons else ""

        return GuardChainResult(
            final_verdict=final_verdict,
            final_reason=final_reason,
            guard_results=results,
            repaired_args=repaired_args,
        )

    async def check_all_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardChainResult:
        """Run all guards in sequence (async version).

        Uses check_async if available, falls back to check.
        """
        results: list[tuple[str, GuardResult]] = []
        current_args = dict(arguments)
        repaired_args: dict[str, Any] | None = None

        for name, guard in self._guards:
            # Try async check first
            if hasattr(guard, "check_async"):
                result = await guard.check_async(tool_name, current_args)
            else:
                result = guard.check(tool_name, current_args)

            results.append((name, result))

            if result.verdict == GuardVerdict.BLOCK:
                return GuardChainResult(
                    final_verdict=GuardVerdict.BLOCK,
                    final_reason=result.reason,
                    guard_results=results,
                    stopped_at=name,
                )

            if result.verdict == GuardVerdict.REPAIR and result.repaired_args:
                current_args = result.repaired_args
                repaired_args = result.repaired_args

        has_warnings = any(r.verdict == GuardVerdict.WARN for _, r in results)
        final_verdict = GuardVerdict.WARN if has_warnings else GuardVerdict.ALLOW

        warning_reasons = [r.reason for _, r in results if r.verdict == GuardVerdict.WARN and r.reason]
        final_reason = "; ".join(warning_reasons) if warning_reasons else ""

        return GuardChainResult(
            final_verdict=final_verdict,
            final_reason=final_reason,
            guard_results=results,
            repaired_args=repaired_args,
        )

    def check_output_all(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> GuardChainResult:
        """Run all guards' post-execution checks.

        Args:
            tool_name: Name of the tool that was called
            arguments: Arguments that were passed
            result: The result from tool execution

        Returns:
            GuardChainResult with final verdict
        """
        results: list[tuple[str, GuardResult]] = []
        current_result = result

        for name, guard in self._guards:
            check_result = guard.check_output(tool_name, arguments, current_result)
            results.append((name, check_result))

            if check_result.verdict == GuardVerdict.BLOCK:
                return GuardChainResult(
                    final_verdict=GuardVerdict.BLOCK,
                    final_reason=check_result.reason,
                    guard_results=results,
                    stopped_at=name,
                )

            # For output checks, repair verdict means modified output
            if check_result.verdict == GuardVerdict.REPAIR and check_result.fallback_response:
                # Could parse fallback_response back to result
                pass

        has_warnings = any(r.verdict == GuardVerdict.WARN for _, r in results)
        final_verdict = GuardVerdict.WARN if has_warnings else GuardVerdict.ALLOW

        warning_reasons = [r.reason for _, r in results if r.verdict == GuardVerdict.WARN and r.reason]
        final_reason = "; ".join(warning_reasons) if warning_reasons else ""

        return GuardChainResult(
            final_verdict=final_verdict,
            final_reason=final_reason,
            guard_results=results,
        )

    def reset_all(self) -> None:
        """Reset all guards that have reset methods."""
        for _, guard in self._guards:
            if hasattr(guard, "reset"):
                guard.reset()

    def __len__(self) -> int:
        """Return number of guards in chain."""
        return len(self._guards)

    def __iter__(self):
        """Iterate over (name, guard) tuples."""
        return iter(self._guards)

    @classmethod
    def create_default(cls) -> GuardChain:
        """Create a chain with recommended default guards.

        Returns a chain with guards in recommended order.
        Import guards lazily to avoid circular imports.
        """
        from chuk_tool_processor.guards.concurrency import ConcurrencyGuard
        from chuk_tool_processor.guards.network_policy import NetworkPolicyGuard
        from chuk_tool_processor.guards.output_size import OutputSizeGuard
        from chuk_tool_processor.guards.plan_shape import PlanShapeGuard
        from chuk_tool_processor.guards.retry_safety import RetrySafetyGuard
        from chuk_tool_processor.guards.schema_strictness import SchemaStrictnessGuard
        from chuk_tool_processor.guards.sensitive_data import SensitiveDataGuard
        from chuk_tool_processor.guards.side_effect import SideEffectGuard
        from chuk_tool_processor.guards.timeout_budget import TimeoutBudgetGuard

        return cls(
            [
                ("schema", SchemaStrictnessGuard()),
                ("sensitive_args", SensitiveDataGuard()),
                ("network", NetworkPolicyGuard()),
                ("side_effect", SideEffectGuard()),
                ("concurrency", ConcurrencyGuard()),
                ("timeout", TimeoutBudgetGuard()),
                ("plan_shape", PlanShapeGuard()),
                ("retry", RetrySafetyGuard()),
                ("output_size", OutputSizeGuard()),
            ]
        )
