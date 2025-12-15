# chuk_tool_processor/guards/side_effect.py
"""Side effect guard for controlling tool capabilities.

Labels tools as read_only/write/destructive and enforces policies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel, ToolClassification


class SideEffectClass(str, Enum):
    """Classification of tool side effects."""

    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ExecutionMode(str, Enum):
    """Allowed execution modes."""

    READ_ONLY = "read_only"  # Only read operations allowed
    WRITE_ALLOWED = "write_allowed"  # Writes allowed, destructive blocked
    DESTRUCTIVE_ALLOWED = "destructive_allowed"  # All operations allowed


class Environment(str, Enum):
    """Deployment environment."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class SideEffectConfig(BaseModel):
    """Configuration for SideEffectGuard."""

    mode: ExecutionMode = Field(
        default=ExecutionMode.WRITE_ALLOWED,
        description="Allowed execution mode",
    )
    environment: Environment = Field(
        default=Environment.DEV,
        description="Current deployment environment",
    )
    require_capability_token: bool = Field(
        default=False,
        description="Require capability token for write/destructive",
    )
    capability_token_arg: str = Field(
        default="_capability_token",
        description="Argument name for capability token",
    )
    prod_blocked_classes: set[SideEffectClass] = Field(
        default_factory=lambda: {SideEffectClass.DESTRUCTIVE},
        description="Side effect classes blocked in production",
    )
    explicit_classifications: dict[str, SideEffectClass] = Field(
        default_factory=dict,
        description="Explicit tool classifications (overrides heuristics)",
    )
    enforcement_level: EnforcementLevel = Field(
        default=EnforcementLevel.BLOCK,
        description="Enforcement level for violations",
    )


# Type alias for classification getter callback
ClassificationGetter = Callable[[str], Awaitable[SideEffectClass] | SideEffectClass]


class SideEffectGuard(BaseGuard):
    """Guard that enforces side effect policies.

    Features:
    - Read-only mode for evals/demos
    - Capability token requirement for writes
    - Environment gating (block destructive in prod)
    - Automatic classification via heuristics or explicit config
    """

    def __init__(
        self,
        config: SideEffectConfig | None = None,
        get_classification: ClassificationGetter | None = None,
    ) -> None:
        """Initialize the guard.

        Args:
            config: Guard configuration
            get_classification: Optional callback to get tool classification.
                              Falls back to heuristic classification if not provided.
        """
        self.config = config or SideEffectConfig()
        self._get_classification = get_classification

    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if tool execution is allowed based on side effect policy."""
        classification = self._classify_tool(tool_name)

        # Check environment restrictions
        env_violation = self._check_environment(tool_name, classification)
        if env_violation:
            return env_violation

        # Check mode restrictions
        mode_violation = self._check_mode(tool_name, classification)
        if mode_violation:
            return mode_violation

        # Check capability token if required
        token_violation = self._check_capability_token(tool_name, classification, arguments)
        if token_violation:
            return token_violation

        return self.allow()

    async def check_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Async check with async classification lookup."""
        classification = await self._classify_tool_async(tool_name)

        env_violation = self._check_environment(tool_name, classification)
        if env_violation:
            return env_violation

        mode_violation = self._check_mode(tool_name, classification)
        if mode_violation:
            return mode_violation

        token_violation = self._check_capability_token(tool_name, classification, arguments)
        if token_violation:
            return token_violation

        return self.allow()

    def _classify_tool(self, tool_name: str) -> SideEffectClass:
        """Get synchronous classification for a tool."""
        # Check explicit classifications first
        if tool_name in self.config.explicit_classifications:
            return self.config.explicit_classifications[tool_name]

        # Use callback if provided and it's synchronous
        if self._get_classification is not None:
            result = self._get_classification(tool_name)
            if not isinstance(result, Awaitable):
                return result

        # Fall back to heuristic
        return self._heuristic_classification(tool_name)

    async def _classify_tool_async(self, tool_name: str) -> SideEffectClass:
        """Get async classification for a tool."""
        if tool_name in self.config.explicit_classifications:
            return self.config.explicit_classifications[tool_name]

        if self._get_classification is not None:
            result = self._get_classification(tool_name)
            if isinstance(result, Awaitable):
                return await result
            return result

        return self._heuristic_classification(tool_name)

    def _heuristic_classification(self, tool_name: str) -> SideEffectClass:
        """Classify tool using heuristics from ToolClassification."""
        classification = ToolClassification.classify_side_effect(tool_name)

        return {
            "read_only": SideEffectClass.READ_ONLY,
            "write": SideEffectClass.WRITE,
            "destructive": SideEffectClass.DESTRUCTIVE,
        }.get(classification, SideEffectClass.WRITE)

    def _check_environment(
        self,
        tool_name: str,
        classification: SideEffectClass,
    ) -> GuardResult | None:
        """Check if classification is allowed in current environment."""
        if self.config.environment != Environment.PROD:
            return None

        if classification in self.config.prod_blocked_classes:
            message = f"Tool '{tool_name}' classified as {classification.value} is blocked in production environment"
            return self._enforcement_result(message, tool_name, classification)

        return None

    def _check_mode(
        self,
        tool_name: str,
        classification: SideEffectClass,
    ) -> GuardResult | None:
        """Check if classification is allowed in current mode."""
        mode = self.config.mode

        if mode == ExecutionMode.READ_ONLY:
            if classification != SideEffectClass.READ_ONLY:
                message = f"Tool '{tool_name}' classified as {classification.value} is blocked in read-only mode"
                return self._enforcement_result(message, tool_name, classification)

        elif mode == ExecutionMode.WRITE_ALLOWED and classification == SideEffectClass.DESTRUCTIVE:
            message = (
                f"Tool '{tool_name}' classified as {classification.value} "
                f"is blocked (destructive operations not allowed)"
            )
            return self._enforcement_result(message, tool_name, classification)

        return None

    def _check_capability_token(
        self,
        tool_name: str,
        classification: SideEffectClass,
        arguments: dict[str, Any],
    ) -> GuardResult | None:
        """Check if capability token is present when required."""
        if not self.config.require_capability_token:
            return None

        if classification == SideEffectClass.READ_ONLY:
            return None

        token = arguments.get(self.config.capability_token_arg)
        if not token:
            message = f"Tool '{tool_name}' requires capability token for {classification.value} operations"
            return self._enforcement_result(message, tool_name, classification)

        return None

    def _enforcement_result(
        self,
        message: str,
        tool_name: str,
        classification: SideEffectClass,
    ) -> GuardResult:
        """Create enforcement result based on config."""
        if self.config.enforcement_level == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                tool=tool_name,
                classification=classification.value,
            )

        return self.block(
            reason=message,
            tool=tool_name,
            classification=classification.value,
        )

    def set_mode(self, mode: ExecutionMode) -> None:
        """Change execution mode at runtime."""
        self.config.mode = mode

    def set_environment(self, environment: Environment) -> None:
        """Change environment at runtime."""
        self.config.environment = environment
