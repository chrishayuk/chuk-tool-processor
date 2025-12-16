# chuk_tool_processor/models/sandbox_policy.py
"""
SandboxPolicy: Declarative sandbox requirements for tool execution.

This module provides a policy-as-code approach to tool isolation,
allowing:
- MCP servers to declare tool requirements
- Tool Processor to enforce isolation
- Agents to reason about tool safety

The policy matrix approach maps tool patterns to isolation requirements,
making sandbox decisions explicit and auditable.

Example:
    >>> policy = SandboxPolicy(
    ...     isolation=IsolationLevel.PROCESS,
    ...     network=NetworkPolicy.DENY,
    ...     filesystem=FilesystemPolicy.READ_ONLY,
    ...     tool_patterns=["solver.*", "compute.*"],
    ... )
    >>> # All solver.* and compute.* tools run in process isolation
    >>> # with no network and read-only filesystem
"""

from __future__ import annotations

import fnmatch
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IsolationLevel(str, Enum):
    """Level of process isolation for tool execution."""

    NONE = "none"  # Direct in-process (fastest, least safe)
    THREAD = "thread"  # Thread-level isolation only
    PROCESS = "process"  # Subprocess isolation (safe default)
    CONTAINER = "container"  # Container isolation (most secure)
    WASM = "wasm"  # WebAssembly sandbox (future)


class NetworkPolicy(str, Enum):
    """Network access policy for sandboxed execution."""

    DENY = "deny"  # No network access
    LOCALHOST = "localhost"  # Only localhost connections
    PRIVATE = "private"  # Only private network (10.x, 192.168.x, etc.)
    ALLOW = "allow"  # Full network access


class FilesystemPolicy(str, Enum):
    """Filesystem access policy for sandboxed execution."""

    DENY = "deny"  # No filesystem access
    READ_ONLY = "read_only"  # Read-only access to allowed paths
    TEMP_ONLY = "temp_only"  # Read/write only to temp directories
    READ_WRITE = "read_write"  # Full read/write access to allowed paths


class CapabilityGrant(str, Enum):
    """Specific capabilities that can be granted to sandboxed tools."""

    # Process capabilities
    SPAWN_SUBPROCESS = "spawn_subprocess"  # Can spawn child processes
    SPAWN_THREADS = "spawn_threads"  # Can spawn threads

    # I/O capabilities
    STDIN = "stdin"  # Can read from stdin
    STDOUT = "stdout"  # Can write to stdout
    STDERR = "stderr"  # Can write to stderr

    # Resource capabilities
    GPU = "gpu"  # Can access GPU
    HIGH_MEMORY = "high_memory"  # Can use > 1GB memory
    LONG_RUNNING = "long_running"  # Can run > 60 seconds

    # System capabilities
    ENVIRONMENT = "environment"  # Can read environment variables
    SIGNALS = "signals"  # Can handle signals


class ResourceLimit(BaseModel):
    """Resource limits for sandboxed execution."""

    model_config = ConfigDict(frozen=True)

    # CPU limits
    cpu_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Maximum CPU seconds allowed",
    )
    cpu_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Maximum CPU percentage (0-100)",
    )

    # Memory limits
    memory_mb: int | None = Field(
        default=None,
        ge=0,
        description="Maximum memory in megabytes",
    )
    memory_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Maximum memory as percentage of system",
    )

    # I/O limits
    output_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Maximum output size in bytes",
    )
    open_files: int | None = Field(
        default=None,
        ge=0,
        description="Maximum number of open file descriptors",
    )

    # Time limits
    wall_time_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Maximum wall-clock time in seconds",
    )

    # Process limits
    max_processes: int | None = Field(
        default=None,
        ge=0,
        description="Maximum number of child processes",
    )

    def merge_with(self, other: ResourceLimit) -> ResourceLimit:
        """Merge with another limit, taking the more restrictive values."""
        return ResourceLimit(
            cpu_seconds=_min_none_float(self.cpu_seconds, other.cpu_seconds),
            cpu_percent=_min_none_int(self.cpu_percent, other.cpu_percent),
            memory_mb=_min_none_int(self.memory_mb, other.memory_mb),
            memory_percent=_min_none_int(self.memory_percent, other.memory_percent),
            output_bytes=_min_none_int(self.output_bytes, other.output_bytes),
            open_files=_min_none_int(self.open_files, other.open_files),
            wall_time_seconds=_min_none_float(self.wall_time_seconds, other.wall_time_seconds),
            max_processes=_min_none_int(self.max_processes, other.max_processes),
        )


def _min_none_int(a: int | None, b: int | None) -> int | None:
    """Return minimum of two int values, treating None as infinity."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _min_none_float(a: float | None, b: float | None) -> float | None:
    """Return minimum of two float values, treating None as infinity."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


class PathRule(BaseModel):
    """Rule for filesystem path access."""

    model_config = ConfigDict(frozen=True)

    pattern: str = Field(..., description="Glob pattern for matching paths")
    access: str = Field(
        default="read",
        description="Access level: 'read', 'write', or 'deny'",
    )


class SandboxPolicy(BaseModel):
    """
    Declarative sandbox requirements for a tool or tool category.

    SandboxPolicy expresses what isolation and resource constraints
    should be applied when executing tools matching certain patterns.

    The Tool Processor uses these policies to:
    - Select appropriate execution strategy
    - Configure sandbox parameters
    - Enforce resource limits
    - Audit execution decisions

    Example:
        >>> # Policy for untrusted code execution
        >>> untrusted_policy = SandboxPolicy(
        ...     name="untrusted-code",
        ...     isolation=IsolationLevel.CONTAINER,
        ...     network=NetworkPolicy.DENY,
        ...     filesystem=FilesystemPolicy.TEMP_ONLY,
        ...     limits=ResourceLimit(
        ...         cpu_seconds=30,
        ...         memory_mb=512,
        ...         wall_time_seconds=60,
        ...     ),
        ...     tool_patterns=["code.*", "eval.*"],
        ... )

        >>> # Policy for trusted internal tools
        >>> trusted_policy = SandboxPolicy(
        ...     name="trusted-internal",
        ...     isolation=IsolationLevel.NONE,
        ...     network=NetworkPolicy.ALLOW,
        ...     filesystem=FilesystemPolicy.READ_WRITE,
        ...     tool_patterns=["internal.*"],
        ... )
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    name: str = Field(
        default="default",
        description="Name of this policy for logging/debugging",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the policy",
    )
    priority: int = Field(
        default=0,
        description="Priority when multiple policies match (higher = checked first)",
    )

    # ------------------------------------------------------------------ #
    # Isolation level
    # ------------------------------------------------------------------ #
    isolation: IsolationLevel = Field(
        default=IsolationLevel.PROCESS,
        description="Level of process isolation required",
    )

    # ------------------------------------------------------------------ #
    # Network policy
    # ------------------------------------------------------------------ #
    network: NetworkPolicy = Field(
        default=NetworkPolicy.DENY,
        description="Network access policy",
    )
    allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Specific hosts allowed (when network=PRIVATE or ALLOW)",
    )
    blocked_hosts: list[str] = Field(
        default_factory=list,
        description="Specific hosts blocked (blacklist)",
    )

    # ------------------------------------------------------------------ #
    # Filesystem policy
    # ------------------------------------------------------------------ #
    filesystem: FilesystemPolicy = Field(
        default=FilesystemPolicy.READ_ONLY,
        description="Filesystem access policy",
    )
    allowed_paths: list[PathRule] = Field(
        default_factory=list,
        description="Specific paths allowed with access levels",
    )
    blocked_paths: list[str] = Field(
        default_factory=list,
        description="Paths explicitly blocked (glob patterns)",
    )

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    capabilities: set[CapabilityGrant] = Field(
        default_factory=set,
        description="Specific capabilities granted to the sandbox",
    )

    # ------------------------------------------------------------------ #
    # Resource limits
    # ------------------------------------------------------------------ #
    limits: ResourceLimit = Field(
        default_factory=ResourceLimit,
        description="Resource limits for execution",
    )

    # ------------------------------------------------------------------ #
    # Matching rules
    # ------------------------------------------------------------------ #
    tool_patterns: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Glob patterns for matching tool names (e.g., 'solver.*')",
    )
    namespace_patterns: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Glob patterns for matching namespaces",
    )
    exclude_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns to exclude from this policy",
    )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    @field_validator("tool_patterns", "namespace_patterns", "exclude_patterns")
    @classmethod
    def validate_patterns(cls, v: list[str]) -> list[str]:
        """Validate that patterns are valid glob patterns."""
        for pattern in v:
            # Basic validation - fnmatch will handle the actual matching
            if not pattern:
                raise ValueError("Empty pattern not allowed")
        return v

    # ------------------------------------------------------------------ #
    # Matching
    # ------------------------------------------------------------------ #
    def matches(self, tool_name: str, namespace: str = "default") -> bool:
        """
        Check if this policy applies to a tool.

        Args:
            tool_name: Name of the tool
            namespace: Namespace of the tool

        Returns:
            True if this policy should apply to the tool
        """
        # Check exclusions first
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(tool_name, pattern):
                return False
            if fnmatch.fnmatch(f"{namespace}.{tool_name}", pattern):
                return False

        # Check tool patterns
        tool_matches = any(fnmatch.fnmatch(tool_name, p) for p in self.tool_patterns) or any(
            fnmatch.fnmatch(f"{namespace}.{tool_name}", p) for p in self.tool_patterns
        )

        # Check namespace patterns
        namespace_matches = any(fnmatch.fnmatch(namespace, p) for p in self.namespace_patterns)

        return tool_matches and namespace_matches

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #
    @property
    def is_restrictive(self) -> bool:
        """Check if this is a restrictive policy (blocks network/filesystem)."""
        return self.network == NetworkPolicy.DENY or self.filesystem == FilesystemPolicy.DENY

    @property
    def allows_network(self) -> bool:
        """Check if network access is allowed."""
        return self.network != NetworkPolicy.DENY

    @property
    def allows_write(self) -> bool:
        """Check if write access is allowed."""
        return self.filesystem in (FilesystemPolicy.TEMP_ONLY, FilesystemPolicy.READ_WRITE)

    @property
    def is_isolated(self) -> bool:
        """Check if this policy requires process isolation."""
        return self.isolation in (IsolationLevel.PROCESS, IsolationLevel.CONTAINER, IsolationLevel.WASM)

    def has_capability(self, cap: CapabilityGrant) -> bool:
        """Check if a specific capability is granted."""
        return cap in self.capabilities

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        """Export policy as dictionary."""
        return self.model_dump(exclude_none=True)

    def to_matrix_row(self) -> dict[str, str]:
        """
        Export as a row for the policy matrix table.

        Returns a simplified dict suitable for tabular display.
        """
        return {
            "name": self.name,
            "isolation": self.isolation.value,
            "network": self.network.value,
            "filesystem": self.filesystem.value,
            "cpu_limit": f"{self.limits.cpu_seconds}s" if self.limits.cpu_seconds else "∞",
            "mem_limit": f"{self.limits.memory_mb}MB" if self.limits.memory_mb else "∞",
            "patterns": ", ".join(self.tool_patterns[:3]),
        }


class PolicyRegistry(BaseModel):
    """
    Registry of sandbox policies with pattern-based matching.

    The registry maintains a collection of policies and provides
    lookup functionality to find the appropriate policy for a tool.

    Example:
        >>> registry = PolicyRegistry(policies=[
        ...     SandboxPolicy(name="strict", isolation=IsolationLevel.CONTAINER, ...),
        ...     SandboxPolicy(name="moderate", isolation=IsolationLevel.PROCESS, ...),
        ...     SandboxPolicy(name="permissive", isolation=IsolationLevel.NONE, ...),
        ... ])
        >>> policy = registry.get_policy("solver.run", namespace="compute")
    """

    model_config = ConfigDict(frozen=False)

    policies: list[SandboxPolicy] = Field(
        default_factory=list,
        description="List of policies in priority order",
    )
    default_policy: SandboxPolicy = Field(
        default_factory=lambda: SandboxPolicy(
            name="default",
            description="Default policy when no other matches",
            isolation=IsolationLevel.PROCESS,
            network=NetworkPolicy.DENY,
            filesystem=FilesystemPolicy.READ_ONLY,
        ),
        description="Policy to use when no other policy matches",
    )

    def add_policy(self, policy: SandboxPolicy) -> None:
        """Add a policy to the registry."""
        self.policies.append(policy)
        # Keep sorted by priority (descending)
        self.policies.sort(key=lambda p: p.priority, reverse=True)

    def remove_policy(self, name: str) -> bool:
        """Remove a policy by name. Returns True if found and removed."""
        for i, policy in enumerate(self.policies):
            if policy.name == name:
                self.policies.pop(i)
                return True
        return False

    def get_policy(self, tool_name: str, namespace: str = "default") -> SandboxPolicy:
        """
        Get the policy that applies to a tool.

        Args:
            tool_name: Name of the tool
            namespace: Namespace of the tool

        Returns:
            The highest-priority matching policy, or default_policy
        """
        for policy in self.policies:
            if policy.matches(tool_name, namespace):
                return policy
        return self.default_policy

    def get_all_matching(self, tool_name: str, namespace: str = "default") -> list[SandboxPolicy]:
        """Get all policies that match a tool (for debugging)."""
        return [p for p in self.policies if p.matches(tool_name, namespace)]

    def to_matrix(self) -> list[dict[str, str]]:
        """Export all policies as a matrix for display."""
        rows = [p.to_matrix_row() for p in self.policies]
        rows.append(self.default_policy.to_matrix_row())
        return rows


# ------------------------------------------------------------------ #
# Preset policies
# ------------------------------------------------------------------ #

# Strict policy for untrusted code
STRICT_POLICY = SandboxPolicy(
    name="strict",
    description="Maximum isolation for untrusted code",
    priority=100,
    isolation=IsolationLevel.CONTAINER,
    network=NetworkPolicy.DENY,
    filesystem=FilesystemPolicy.DENY,
    limits=ResourceLimit(
        cpu_seconds=30,
        memory_mb=256,
        wall_time_seconds=60,
        output_bytes=1024 * 1024,  # 1MB
    ),
    tool_patterns=["eval.*", "exec.*", "code.*", "untrusted.*"],
)

# Standard policy for computation
STANDARD_POLICY = SandboxPolicy(
    name="standard",
    description="Process isolation for general computation",
    priority=50,
    isolation=IsolationLevel.PROCESS,
    network=NetworkPolicy.DENY,
    filesystem=FilesystemPolicy.TEMP_ONLY,
    limits=ResourceLimit(
        cpu_seconds=300,
        memory_mb=1024,
        wall_time_seconds=600,
    ),
    tool_patterns=["compute.*", "process.*", "transform.*"],
)

# Permissive policy for trusted internal tools
PERMISSIVE_POLICY = SandboxPolicy(
    name="permissive",
    description="Minimal isolation for trusted tools",
    priority=10,
    isolation=IsolationLevel.NONE,
    network=NetworkPolicy.ALLOW,
    filesystem=FilesystemPolicy.READ_WRITE,
    capabilities={CapabilityGrant.SPAWN_SUBPROCESS, CapabilityGrant.ENVIRONMENT},
    tool_patterns=["internal.*", "trusted.*"],
)

# MCP remote policy - trust the MCP server's own isolation
MCP_POLICY = SandboxPolicy(
    name="mcp",
    description="Policy for MCP remote tools (delegation)",
    priority=75,
    isolation=IsolationLevel.NONE,  # MCP server handles isolation
    network=NetworkPolicy.ALLOW,  # Need network to reach MCP
    filesystem=FilesystemPolicy.DENY,  # No local filesystem access
    tool_patterns=["mcp.*", "remote.*"],
)


def create_default_registry() -> PolicyRegistry:
    """Create a registry with sensible default policies."""
    return PolicyRegistry(
        policies=[
            STRICT_POLICY,
            MCP_POLICY,
            STANDARD_POLICY,
            PERMISSIVE_POLICY,
        ]
    )
