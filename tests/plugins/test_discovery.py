# tests/tool_processor/plugins/test_discover.py
"""
Tests for the generic plugin-discovery utility.

These tests exercise:
* the in-memory `PluginRegistry`
* the public `@plugin` decorator
* direct `_maybe_register()` calls
* the full recursive discovery path with mocked import machinery
"""

from __future__ import annotations

from unittest import mock

from chuk_tool_processor.plugins.discovery import (
    PluginDiscovery,
    PluginRegistry,
    discover_default_plugins,
    discover_plugins,
    plugin,
    plugin_registry,
)

# ---------------------------------------------------------------------------
# Maybe-present bases from runtime package
# ---------------------------------------------------------------------------
try:
    from chuk_tool_processor.plugins.parsers.base import ParserPlugin
except ModuleNotFoundError:
    ParserPlugin = None  # pragma: no cover - optional feature

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy

# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_round_trip(self):
        reg = PluginRegistry()
        sentinel = object()
        reg.register_plugin("cat", "name", sentinel)
        assert reg.get_plugin("cat", "name") is sentinel
        assert "cat" in reg.list_plugins()
        assert "name" in reg.list_plugins("cat")["cat"]


# ---------------------------------------------------------------------------
# @plugin decorator
# ---------------------------------------------------------------------------


class TestPluginDecorator:
    def test_custom_and_default_name(self):
        @plugin("cat", "custom")
        class C1:
            pass

        @plugin("cat")
        class C2:
            pass

        assert C1._plugin_meta == {"category": "cat", "name": "custom"}  # type: ignore[attr-defined]
        assert C2._plugin_meta["name"] == "C2"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Dummy classes to feed discovery
# ---------------------------------------------------------------------------

if ParserPlugin:

    class DummyParser(ParserPlugin):
        """A minimal *async* implementation that satisfies the ABC."""

        async def try_parse(self, raw: str | object):  # type: ignore[override]
            return []

else:
    # Fallback when the parser subsystem isn't available (very unlikely in tests)
    class DummyParser:  # pragma: no cover
        async def try_parse(self, raw: str | object):  # noqa: D401
            return []


class DummyExec(ExecutionStrategy):
    async def run(self, calls, timeout=None):  # pragma: no cover - not executed
        return []


@plugin("custom", "custom_plugin")
class DummyCustom:
    pass


# ---------------------------------------------------------------------------
# Discovery unit tests (use public API only)
# ---------------------------------------------------------------------------


class TestPluginDiscovery:
    def _single_discovery(self, cls):
        reg = PluginRegistry()
        disc = PluginDiscovery(reg)
        disc._maybe_register(cls)  # internal helper, still public
        return reg

    def test_register_parser(self):
        reg = self._single_discovery(DummyParser)
        assert isinstance(reg.get_plugin("parser", "DummyParser"), DummyParser)

    def test_register_exec_strategy(self):
        reg = self._single_discovery(DummyExec)
        assert reg.get_plugin("execution_strategy", "DummyExec") is DummyExec

    def test_register_plugin_meta(self):
        reg = self._single_discovery(DummyCustom)
        assert isinstance(reg.get_plugin("custom", "custom_plugin"), DummyCustom)

    def test_ignore_non_plugin(self):
        class Bogus:
            pass

        reg = self._single_discovery(Bogus)
        assert not reg.list_plugins()  # nothing registered


# ---------------------------------------------------------------------------
# Integration tests - mock import machinery
# ---------------------------------------------------------------------------


class TestDiscoveryIntegration:
    @mock.patch("importlib.import_module")
    @mock.patch("pkgutil.iter_modules")
    def test_discover_single_module(self, itermods, impmod):
        # --- stub package ---
        fake_pkg = mock.MagicMock()
        fake_pkg.__path__ = ["/fake"]
        fake_pkg.__name__ = "package"
        impmod.return_value = fake_pkg

        itermods.return_value = [(None, "package.mod", False)]

        # --- stub module with a parser plugin ---
        class Plug(DummyParser):
            pass

        fake_mod = mock.MagicMock()
        fake_mod.__name__ = "package.mod"
        fake_mod.Plug = Plug
        impmod.side_effect = lambda n: fake_mod if n == "package.mod" else fake_pkg

        reg = PluginRegistry()
        PluginDiscovery(reg).discover_plugins(["package"])
        assert isinstance(reg.get_plugin("parser", "Plug"), Plug)

    # -----------------------------------------------------------

    @mock.patch("importlib.import_module")
    def test_default_discovery_wrapper(self, impmod):
        impmod.return_value = mock.MagicMock()
        with mock.patch.object(PluginDiscovery, "discover_plugins") as spy:
            discover_default_plugins()
            spy.assert_called_once_with(["chuk_tool_processor.plugins"])

    @mock.patch("importlib.import_module")
    def test_custom_package_wrapper(self, impmod):
        impmod.return_value = mock.MagicMock()
        with mock.patch.object(PluginDiscovery, "discover_plugins") as spy:
            discover_plugins(["pkg1", "pkg2"])
            spy.assert_called_once_with(["pkg1", "pkg2"])


# ---------------------------------------------------------------------------
# Global registry smoke test
# ---------------------------------------------------------------------------


def test_global_registry_singleton():
    assert isinstance(plugin_registry, PluginRegistry)
