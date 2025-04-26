# chuk_tool_processor/plugins/discovery.py
"""Plugin discovery & registry utilities for chuk_tool_processor"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Any, Dict, List, Optional, Set, Type

logger = logging.getLogger(__name__)


class PluginRegistry:
    """In‑memory registry keyed by *category → name*."""

    def __init__(self) -> None:  # no side‑effects in import time
        self._plugins: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    def register_plugin(self, category: str, name: str, plugin: Any) -> None:
        self._plugins.setdefault(category, {})[name] = plugin
        logger.debug("Registered plugin %s.%s", category, name)

    def get_plugin(self, category: str, name: str) -> Optional[Any]:
        return self._plugins.get(category, {}).get(name)

    def list_plugins(self, category: str | None = None) -> Dict[str, List[str]]:
        if category:
            return {category: list(self._plugins.get(category, {}))}
        return {cat: list(names) for cat, names in self._plugins.items()}


class PluginDiscovery:
    """Recursively scans packages for plugin classes and registers them."""

    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry
        self._seen: Set[str] = set()

        # optional parser subsystem
        try:
            from chuk_tool_processor.parsers.base import ParserPlugin as _PP  # noqa: WPS433
        except ModuleNotFoundError:
            _PP = None
        self.ParserPlugin = _PP

        # ExecutionStrategy always present inside core models
        from chuk_tool_processor.models.execution_strategy import ExecutionStrategy  # noqa: WPS433

        self.ExecutionStrategy = ExecutionStrategy

    # ------------------------------------------------------------------
    def discover_plugins(self, package_paths: List[str]) -> None:
        for pkg in package_paths:
            self._walk(pkg)

    # ------------------------------------------------------------------
    def _walk(self, pkg_path: str) -> None:
        try:
            pkg = importlib.import_module(pkg_path)
        except ImportError as exc:  # pragma: no cover
            logger.warning("Cannot import package %s: %s", pkg_path, exc)
            return

        for _, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
            if mod_name in self._seen:
                continue
            self._seen.add(mod_name)
            self._inspect_module(mod_name)
            if is_pkg:
                self._walk(mod_name)

    # ------------------------------------------------------------------
    def _inspect_module(self, mod_name: str) -> None:
        try:
            module = importlib.import_module(mod_name)
        except ImportError as exc:  # pragma: no cover
            logger.warning("Cannot import module %s: %s", mod_name, exc)
            return

        for attr in module.__dict__.values():
            if inspect.isclass(attr):
                self._maybe_register(attr)

    # ------------------------------------------------------------------
    def _maybe_register(self, cls: Type) -> None:
        """Register *cls* in all relevant plugin categories."""

        # ---------------- parser plugins ------------------------------
        looks_like_parser = callable(getattr(cls, "try_parse", None))
        if looks_like_parser and not inspect.isabstract(cls):
            # skip ABC base itself if available
            if self.ParserPlugin and cls is self.ParserPlugin:
                pass
            else:
                self.registry.register_plugin("parser", cls.__name__, cls())

        # --------------- execution strategies -------------------------
        if (
            issubclass(cls, self.ExecutionStrategy)
            and cls is not self.ExecutionStrategy
            and not inspect.isabstract(cls)
        ):
            self.registry.register_plugin("execution_strategy", cls.__name__, cls)

        # --------------- explicit @plugin decorator -------------------
        meta = getattr(cls, "_plugin_meta", None)
        if meta and not inspect.isabstract(cls):
            self.registry.register_plugin(meta.get("category", "unknown"), meta.get("name", cls.__name__), cls())


# ----------------------------------------------------------------------
# public decorator helper
# ----------------------------------------------------------------------

def plugin(category: str, name: str | None = None):
    """Decorator to mark a class as a plugin for explicit registration."""

    def decorator(cls):
        cls._plugin_meta = {"category": category, "name": name or cls.__name__}
        return cls

    return decorator


# ----------------------------------------------------------------------
# Singletons & convenience wrappers
# ----------------------------------------------------------------------
plugin_registry = PluginRegistry()


def discover_default_plugins() -> None:
    PluginDiscovery(plugin_registry).discover_plugins(["chuk_tool_processor.plugins"])


def discover_plugins(package_paths: List[str]) -> None:
    PluginDiscovery(plugin_registry).discover_plugins(package_paths)
