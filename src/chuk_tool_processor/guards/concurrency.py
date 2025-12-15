# chuk_tool_processor/guards/concurrency.py
"""Concurrency guard to prevent tool stampedes.

Limits simultaneous in-flight tool calls globally, per-namespace, and per-tool.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult


class ConcurrencyState(BaseModel):
    """Current concurrency state."""

    global_in_flight: int = 0
    namespace_in_flight: dict[str, int] = Field(default_factory=dict)
    tool_in_flight: dict[str, int] = Field(default_factory=dict)
    session_in_flight: dict[str, int] = Field(default_factory=dict)


class ConcurrencyConfig(BaseModel):
    """Configuration for ConcurrencyGuard."""

    global_max: int = Field(
        default=50,
        description="Maximum total in-flight calls",
    )
    per_namespace_max: dict[str, int] = Field(
        default_factory=dict,
        description="Maximum in-flight calls per namespace",
    )
    per_tool_max: dict[str, int] = Field(
        default_factory=dict,
        description="Maximum in-flight calls per tool",
    )
    per_session_max: int | None = Field(
        default=None,
        description="Maximum in-flight calls per session",
    )
    default_namespace_max: int = Field(
        default=20,
        description="Default max for namespaces not explicitly configured",
    )
    default_tool_max: int = Field(
        default=10,
        description="Default max for tools not explicitly configured",
    )


class ConcurrencyGuard(BaseGuard):
    """Guard that limits simultaneous in-flight tool calls.

    Prevents "tool stampedes" by enforcing:
    - Global maximum concurrent calls
    - Per-namespace limits
    - Per-tool limits
    - Per-session limits

    Thread-safe with async lock.
    """

    def __init__(self, config: ConcurrencyConfig | None = None) -> None:
        self.config = config or ConcurrencyConfig()
        self._state = ConcurrencyState()
        self._lock = asyncio.Lock()

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> GuardResult:
        """Synchronous check - use acquire() for proper concurrency control."""
        # Synchronous check just validates current state without locking
        violations = self._check_limits(tool_name, session_id=None)
        if violations:
            return self.block(
                reason=f"Concurrency limit exceeded: {'; '.join(violations)}",
                current_state=self._state.model_dump(),
            )
        return self.allow()

    async def acquire(
        self,
        tool_name: str,
        session_id: str | None = None,
    ) -> GuardResult:
        """Acquire a slot for execution. Call before tool execution."""
        async with self._lock:
            violations = self._check_limits(tool_name, session_id)
            if violations:
                return self.block(
                    reason=f"Concurrency limit exceeded: {'; '.join(violations)}",
                    current_state=self._state.model_dump(),
                )

            # Increment counters
            self._state.global_in_flight += 1

            namespace = self._get_namespace(tool_name)
            self._state.namespace_in_flight[namespace] = self._state.namespace_in_flight.get(namespace, 0) + 1

            self._state.tool_in_flight[tool_name] = self._state.tool_in_flight.get(tool_name, 0) + 1

            if session_id:
                self._state.session_in_flight[session_id] = self._state.session_in_flight.get(session_id, 0) + 1

            return self.allow()

    async def release(
        self,
        tool_name: str,
        session_id: str | None = None,
    ) -> None:
        """Release a slot after execution. Call after tool execution."""
        async with self._lock:
            self._state.global_in_flight = max(0, self._state.global_in_flight - 1)

            namespace = self._get_namespace(tool_name)
            if namespace in self._state.namespace_in_flight:
                self._state.namespace_in_flight[namespace] = max(0, self._state.namespace_in_flight[namespace] - 1)

            if tool_name in self._state.tool_in_flight:
                self._state.tool_in_flight[tool_name] = max(0, self._state.tool_in_flight[tool_name] - 1)

            if session_id and session_id in self._state.session_in_flight:
                self._state.session_in_flight[session_id] = max(0, self._state.session_in_flight[session_id] - 1)

    @asynccontextmanager
    async def slot(
        self,
        tool_name: str,
        session_id: str | None = None,
    ) -> AsyncIterator[GuardResult]:
        """Context manager for acquiring and releasing slots.

        Usage:
            async with guard.slot("my_tool"):
                result = await execute_tool()
        """
        result = await self.acquire(tool_name, session_id)
        if result.blocked:
            raise ConcurrencyLimitExceeded(result.reason)
        try:
            yield result
        finally:
            await self.release(tool_name, session_id)

    def _check_limits(
        self,
        tool_name: str,
        session_id: str | None,
    ) -> list[str]:
        """Check if any limits would be exceeded."""
        violations: list[str] = []

        # Global limit
        if self._state.global_in_flight >= self.config.global_max:
            violations.append(f"global: {self._state.global_in_flight}/{self.config.global_max}")

        # Namespace limit
        namespace = self._get_namespace(tool_name)
        namespace_max = self.config.per_namespace_max.get(namespace, self.config.default_namespace_max)
        namespace_current = self._state.namespace_in_flight.get(namespace, 0)
        if namespace_current >= namespace_max:
            violations.append(f"namespace '{namespace}': {namespace_current}/{namespace_max}")

        # Tool limit
        tool_max = self.config.per_tool_max.get(tool_name, self.config.default_tool_max)
        tool_current = self._state.tool_in_flight.get(tool_name, 0)
        if tool_current >= tool_max:
            violations.append(f"tool '{tool_name}': {tool_current}/{tool_max}")

        # Session limit
        if session_id and self.config.per_session_max is not None:
            session_current = self._state.session_in_flight.get(session_id, 0)
            if session_current >= self.config.per_session_max:
                violations.append(f"session '{session_id}': {session_current}/{self.config.per_session_max}")

        return violations

    def _get_namespace(self, tool_name: str) -> str:
        """Extract namespace from tool name."""
        if "." in tool_name:
            return tool_name.rsplit(".", 1)[0]
        return "default"

    def get_state(self) -> ConcurrencyState:
        """Get current concurrency state."""
        return self._state.model_copy()

    def reset(self) -> None:
        """Reset all counters."""
        self._state = ConcurrencyState()


class ConcurrencyLimitExceeded(Exception):
    """Raised when concurrency limit is exceeded."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
