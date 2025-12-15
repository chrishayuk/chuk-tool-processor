# chuk_tool_processor/guards/models.py
"""Pydantic models for tool guards.

Defines tool classifications and enforcement levels used by guards.
"""

from __future__ import annotations

from enum import Enum


class EnforcementLevel(str, Enum):
    """Enforcement level for guards and constraints."""

    OFF = "off"  # No enforcement
    WARN = "warn"  # Proceed but log warning
    BLOCK = "block"  # Do not execute, return error


class ToolClassification:
    """Central definitions for tool classification.

    Guards and managers should use these definitions rather than
    maintaining their own hardcoded sets.
    """

    # Discovery tools - search/list/get schemas (count against discovery budget)
    DISCOVERY_TOOLS: frozenset[str] = frozenset(
        {
            "list_tools",
            "search_tools",
            "get_tool_schema",
            "get_tool_schemas",
        }
    )

    # Idempotent math tools - safe to call multiple times, exempt from per-tool limits
    IDEMPOTENT_MATH_TOOLS: frozenset[str] = frozenset(
        {
            "add",
            "subtract",
            "multiply",
            "divide",
            "sqrt",
            "pow",
            "power",
            "log",
            "exp",
            "sin",
            "cos",
            "tan",
            "abs",
            "floor",
            "ceil",
            "round",
        }
    )

    # Parameterized tools - require computed input values (precondition guard)
    # These tools should have prior bindings before being called with numeric args
    PARAMETERIZED_TOOLS: frozenset[str] = frozenset(
        {
            "normal_cdf",
            "normal_pdf",
            "normal_sf",
            "t_cdf",
            "t_sf",
            "t_test",
            "chi_cdf",
            "chi_sf",
            "chi_square",
        }
    )

    @classmethod
    def is_discovery_tool(cls, tool_name: str) -> bool:
        """Check if tool is a discovery tool."""
        base = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()
        return base in cls.DISCOVERY_TOOLS

    @classmethod
    def is_idempotent_math_tool(cls, tool_name: str) -> bool:
        """Check if tool is an idempotent math tool."""
        base = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()
        return base in cls.IDEMPOTENT_MATH_TOOLS

    @classmethod
    def is_parameterized_tool(cls, tool_name: str) -> bool:
        """Check if tool requires computed values."""
        base = tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()
        return base in cls.PARAMETERIZED_TOOLS

    # Side effect classifications for SideEffectGuard
    READ_ONLY_PATTERNS: frozenset[str] = frozenset(
        {
            "get",
            "list",
            "search",
            "read",
            "fetch",
            "query",
            "describe",
            "show",
            "find",
            "lookup",
            "check",
            "validate",
            "verify",
            "count",
            "exists",
        }
    )

    WRITE_PATTERNS: frozenset[str] = frozenset(
        {
            "create",
            "update",
            "put",
            "post",
            "write",
            "save",
            "set",
            "add",
            "insert",
            "modify",
            "patch",
            "upload",
            "send",
            "submit",
        }
    )

    DESTRUCTIVE_PATTERNS: frozenset[str] = frozenset(
        {
            "delete",
            "remove",
            "drop",
            "truncate",
            "destroy",
            "purge",
            "clear",
            "reset",
            "wipe",
            "revoke",
            "terminate",
            "kill",
        }
    )

    # Network-related tools for NetworkPolicyGuard
    NETWORK_PATTERNS: frozenset[str] = frozenset(
        {
            "http",
            "fetch",
            "request",
            "api",
            "webhook",
            "curl",
            "download",
            "upload",
            "socket",
            "connect",
        }
    )

    @classmethod
    def _get_base_name(cls, tool_name: str) -> str:
        """Extract base name from potentially namespaced tool name."""
        return tool_name.split(".")[-1].lower() if "." in tool_name else tool_name.lower()

    @classmethod
    def classify_side_effect(cls, tool_name: str) -> str:
        """Classify tool by side effect type.

        Returns:
            "read_only", "write", or "destructive"
        """
        base = cls._get_base_name(tool_name)

        # Check destructive first (most restrictive)
        for pattern in cls.DESTRUCTIVE_PATTERNS:
            if pattern in base:
                return "destructive"

        # Check write patterns
        for pattern in cls.WRITE_PATTERNS:
            if pattern in base:
                return "write"

        # Check read-only patterns
        for pattern in cls.READ_ONLY_PATTERNS:
            if pattern in base:
                return "read_only"

        # Default to write (conservative)
        return "write"

    @classmethod
    def is_network_tool(cls, tool_name: str) -> bool:
        """Check if tool likely performs network operations."""
        base = cls._get_base_name(tool_name)
        return any(pattern in base for pattern in cls.NETWORK_PATTERNS)
