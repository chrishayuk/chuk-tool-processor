# chuk_tool_processor/registry/provider.py
"""
Global access to *the* tool-registry instance.
"""
from __future__ import annotations

from typing import Optional

from .interface import ToolRegistryInterface
from .providers.memory import InMemoryToolRegistry   # default impl

# ───────────────────────────────────────────────────────────────────────────
_REGISTRY: Optional[ToolRegistryInterface] = None
# ───────────────────────────────────────────────────────────────────────────


def get_registry() -> ToolRegistryInterface:
    """Return the single, process-wide registry instance."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = InMemoryToolRegistry()
    return _REGISTRY


def set_registry(registry: ToolRegistryInterface) -> None:
    """Swap in another implementation (tests, multi-process, …)."""
    global _REGISTRY
    _REGISTRY = registry


# ------------------------------------------------------------------------- #
# 🔌 backward-compat shim – lets old `from … import ToolRegistryProvider`
#    statements keep working without changes.
# ------------------------------------------------------------------------- #
class ToolRegistryProvider:                          # noqa: D401
    """Compatibility wrapper around the new helpers."""

    @staticmethod
    def get_registry() -> ToolRegistryInterface:     # same signature
        return get_registry()

    @staticmethod
    def set_registry(registry: ToolRegistryInterface) -> None:
        set_registry(registry)
