# chuk_tool_processor/plugins/discovery.py
"""Async-friendly plugin discovery & registry utilities for chuk_tool_processor."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import Any

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy
from chuk_tool_processor.plugins.parsers.base import ParserPlugin

__all__ = [
    "plugin_registry",
    "PluginRegistry",
    "PluginDiscovery",
    "discover_default_plugins",
    "discover_plugins",
    "plugin",
]

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# In-memory registry
# -----------------------------------------------------------------------------
class PluginRegistry:
    """Thread-safe (GIL) in-memory registry keyed by *category → name*."""

    def __init__(self) -> None:
        # category → {name → object}
        self._plugins: dict[str, dict[str, Any]] = {}

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def register_plugin(self, category: str, name: str, plugin: Any) -> None:
        self._plugins.setdefault(category, {})[name] = plugin
        logger.debug("Registered plugin %s.%s", category, name)

    def get_plugin(self, category: str, name: str) -> Any | None:  # noqa: D401
        return self._plugins.get(category, {}).get(name)

    def list_plugins(self, category: str | None = None) -> dict[str, list[str]]:
        if category is not None:
            return {category: sorted(self._plugins.get(category, {}))}
        return {cat: sorted(names) for cat, names in self._plugins.items()}


# -----------------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------------
class PluginDiscovery:
    """
    Recursively scans *package_paths* for plugin classes and registers them.

    * Parser plugins - concrete subclasses of :class:`ParserPlugin`
      with an **async** ``try_parse`` coroutine.

    * Execution strategies - concrete subclasses of
      :class:`ExecutionStrategy`.

    * Explicitly-decorated plugins - classes tagged with ``@plugin(...)``.
    """

    # ------------------------------------------------------------------ #
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry
        self._seen_modules: set[str] = set()

    # ------------------------------------------------------------------ #
    def discover_plugins(self, package_paths: list[str]) -> None:
        """Import every package in *package_paths* and walk its subtree."""
        for pkg_path in package_paths:
            self._walk(pkg_path)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _walk(self, pkg_path: str) -> None:
        try:
            root_pkg = importlib.import_module(pkg_path)
        except ImportError as exc:  # pragma: no cover
            logger.warning("Cannot import package %s: %s", pkg_path, exc)
            return

        self._inspect_module(root_pkg)

        for _, mod_name, is_pkg in pkgutil.iter_modules(root_pkg.__path__, root_pkg.__name__ + "."):
            if mod_name in self._seen_modules:
                continue
            self._seen_modules.add(mod_name)

            try:
                mod = importlib.import_module(mod_name)
            except ImportError as exc:  # pragma: no cover
                logger.debug("Cannot import module %s: %s", mod_name, exc)
                continue

            self._inspect_module(mod)

            if is_pkg:
                self._walk(mod_name)

    # ------------------------------------------------------------------ #
    def _inspect_module(self, module: ModuleType) -> None:
        for attr in module.__dict__.values():
            if inspect.isclass(attr):
                self._maybe_register(attr)

    # ------------------------------------------------------------------ #
    def _maybe_register(self, cls: type) -> None:
        """Register *cls* in all matching plugin categories."""
        if inspect.isabstract(cls):
            return

        # ------------------- Parser plugins -------------------------
        if issubclass(cls, ParserPlugin) and cls is not ParserPlugin:
            if not inspect.iscoroutinefunction(getattr(cls, "try_parse", None)):
                logger.debug("Skipping parser plugin %s: try_parse is not async", cls.__qualname__)
            else:
                try:
                    self._registry.register_plugin("parser", cls.__name__, cls())
                except Exception as exc:  # pragma: no cover
                    logger.warning("Cannot instantiate parser plugin %s: %s", cls.__qualname__, exc)

        # ---------------- Execution strategies ---------------------
        if issubclass(cls, ExecutionStrategy) and cls is not ExecutionStrategy:
            self._registry.register_plugin("execution_strategy", cls.__name__, cls)

        # ------------- Explicit @plugin decorator ------------------
        meta: dict | None = getattr(cls, "_plugin_meta", None)
        if meta:
            category = meta.get("category", "unknown")
            name = meta.get("name", cls.__name__)
            try:
                plugin_obj: Any = cls() if callable(getattr(cls, "__init__", None)) else cls
                self._registry.register_plugin(category, name, plugin_obj)
            except Exception as exc:  # pragma: no cover
                logger.warning("Cannot instantiate decorated plugin %s: %s", cls.__qualname__, exc)


# -----------------------------------------------------------------------------
# Decorator helper
# -----------------------------------------------------------------------------
def plugin(category: str, name: str | None = None):
    """
    Decorator that marks a concrete class as a plugin for *category*.

    Example
    -------
    ```python
    @plugin("transport", name="sse")
    class MySSETransport:
        ...
    ```
    """

    def decorator(cls):
        cls._plugin_meta = {"category": category, "name": name or cls.__name__}
        return cls

    return decorator


# -----------------------------------------------------------------------------
# Singletons & convenience wrappers
# -----------------------------------------------------------------------------
plugin_registry = PluginRegistry()


def discover_default_plugins() -> None:
    """Discover plugins shipped inside *chuk_tool_processor.plugins*."""
    PluginDiscovery(plugin_registry).discover_plugins(["chuk_tool_processor.plugins"])


def discover_plugins(package_paths: list[str]) -> None:
    """Discover plugins from arbitrary external *package_paths*."""
    PluginDiscovery(plugin_registry).discover_plugins(package_paths)
