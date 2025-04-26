"""
Global access to *the* tool registry instance.

There are two public faces:

1.  **Module helpers**  
    • `get_registry()` lazily instantiates a default `InMemoryToolRegistry`
      and memoises it in the module-level variable ``_REGISTRY``.  
    • `set_registry()` lets callers replace or reset that singleton.

2.  **`ToolRegistryProvider` shim**  
    Earlier versions exposed a static wrapper.  Tests rely on being able to
    monkey-patch the *module-level* factory and to clear the cached instance
    by setting `ToolRegistryProvider._registry = None`.  We therefore keep a
    **separate class-level cache** (`_registry`) and call the *current*
    module-level `get_registry()` **only when the cache is empty**.

The contract verified by the test-suite is:

* The module-level factory is invoked **exactly once** per fresh cache.
* `ToolRegistryProvider.set_registry(obj)` overrides subsequent retrievals.
* `ToolRegistryProvider.set_registry(None)` resets the cache so the next
  `get_registry()` call invokes (and honours any monkey-patched) factory.
"""
from __future__ import annotations

from typing import Optional

from .interface import ToolRegistryInterface
from .providers.memory import InMemoryToolRegistry

# --------------------------------------------------------------------------- #
# Module-level singleton used by the helper functions
# --------------------------------------------------------------------------- #
_REGISTRY: Optional[ToolRegistryInterface] = None
# --------------------------------------------------------------------------- #


def _default_registry() -> ToolRegistryInterface:
    """Create the default in-memory registry."""
    return InMemoryToolRegistry()


def get_registry() -> ToolRegistryInterface:
    """
    Return the process-wide registry, creating it on first use.

    This function *may* be monkey-patched in tests; call it via
    ``globals()["get_registry"]()`` if you need the latest binding.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _default_registry()
    return _REGISTRY


def set_registry(registry: ToolRegistryInterface | None) -> None:
    """
    Replace or clear the global registry.

    Passing ``None`` resets the singleton so that the next `get_registry()`
    call recreates it (useful in tests).
    """
    global _REGISTRY
    _REGISTRY = registry


# --------------------------------------------------------------------------- #
# Back-compat shim used by legacy import paths and the test-suite
# --------------------------------------------------------------------------- #
class ToolRegistryProvider:                       # noqa: D401
    """Legacy static wrapper retaining historical semantics."""

    # The test-suite directly mutates this attribute, so we keep it.
    _registry: Optional[ToolRegistryInterface] = None

    # ------------------------ public API ------------------------ #
    @staticmethod
    def get_registry() -> ToolRegistryInterface:
        """
        Return the cached instance or, if absent, call the *current*
        module-level `get_registry()` exactly once to populate it.
        """
        if ToolRegistryProvider._registry is None:
            # Honour any runtime monkey-patching of the factory.
            ToolRegistryProvider._registry = globals()["get_registry"]()
        return ToolRegistryProvider._registry

    @staticmethod
    def set_registry(registry: ToolRegistryInterface | None) -> None:
        """
        Override the cached registry.

        *   If ``registry`` is an object, all subsequent `get_registry()`
            calls return it without touching the factory.
        *   If ``registry`` is ``None``, the cache is cleared so the next
            `get_registry()` call invokes the (possibly patched) factory.
        """
        ToolRegistryProvider._registry = registry
