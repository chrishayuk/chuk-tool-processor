# tests/tool_processor/plugins/parsers/test_xml_tool.py
"""
Tests for the plugin-discovery & registry helpers.
They cover:

* basic registry round-trip
* @plugin decorator helper
* automatic discovery/registration of
  - parser-plugins (async)
  - execution strategies
  - classes marked with @plugin
* the public convenience wrappers
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from chuk_tool_processor.plugins.discovery import (
    PluginDiscovery,
    PluginRegistry,
    discover_default_plugins,
    discover_plugins,
    plugin,
    plugin_registry,
)

# --------------------------------------------------------------------------- #
# Optional base interface (depends on “parsers” sub-package being present)
# --------------------------------------------------------------------------- #
try:
    # NEW canonical location
    from chuk_tool_processor.plugins.parsers.base import ParserPlugin
except ModuleNotFoundError:  # pragma: no cover - optional feature genuinely absent
    ParserPlugin = None  # ­type: ignore[assignment]

from chuk_tool_processor.models.execution_strategy import ExecutionStrategy


# --------------------------------------------------------------------------- #
# Registry basics
# --------------------------------------------------------------------------- #
class TestPluginRegistry:
    """Round-trip sanity check for the plain in-memory registry."""

    def test_round_trip(self) -> None:
        reg = PluginRegistry()
        sentinel: Any = object()

        reg.register_plugin("cat", "name", sentinel)

        assert reg.get_plugin("cat", "name") is sentinel
        assert "cat" in reg.list_plugins()
        assert "name" in reg.list_plugins("cat")["cat"]


# --------------------------------------------------------------------------- #
# @plugin decorator helper
# --------------------------------------------------------------------------- #
class TestPluginDecorator:
    def test_custom_and_default_name(self) -> None:
        @plugin("cat", "custom")
        class C1:
            pass

        @plugin("cat")
        class C2:
            pass

        # meta attributes are injected by the decorator
        assert C1._plugin_meta == {"category": "cat", "name": "custom"}  # type: ignore[attr-defined]
        assert C2._plugin_meta["name"] == "C2"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Dummy classes fed into discovery
# --------------------------------------------------------------------------- #
if ParserPlugin:

    class DummyParser(ParserPlugin):  # async implementation!
        async def try_parse(self, raw: str | object):  # noqa: D401
            return []

else:

    class DummyParser:  # pragma: no cover - fallback if parsers are really disabled
        async def try_parse(self, raw):  # type: ignore[override]
            return []


class DummyExec(ExecutionStrategy):
    async def run(self, calls, timeout=None):  # pragma: no cover - never executed
        return []


@plugin("custom", "custom_plugin")
class DummyCustom:
    pass


# --------------------------------------------------------------------------- #
# Discovery - unit tests (use *public* API where possible)
# --------------------------------------------------------------------------- #
class TestPluginDiscovery:
    """Directly exercise the internal `_maybe_register` helper."""

    @staticmethod
    def _single_discovery(cls):  # helper
        reg = PluginRegistry()
        PluginDiscovery(reg)._maybe_register(cls)
        return reg

    def test_register_parser(self) -> None:
        reg = self._single_discovery(DummyParser)
        assert isinstance(reg.get_plugin("parser", "DummyParser"), DummyParser)

    def test_register_exec_strategy(self) -> None:
        reg = self._single_discovery(DummyExec)
        assert reg.get_plugin("execution_strategy", "DummyExec") is DummyExec

    def test_register_plugin_meta(self) -> None:
        reg = self._single_discovery(DummyCustom)
        assert isinstance(reg.get_plugin("custom", "custom_plugin"), DummyCustom)

    def test_ignore_non_plugin(self) -> None:
        class Bogus:
            pass

        reg = self._single_discovery(Bogus)
        assert not reg.list_plugins()  # nothing registered


# --------------------------------------------------------------------------- #
# Integration - mock import machinery to simulate real package walking
# --------------------------------------------------------------------------- #
class TestDiscoveryIntegration:
    """End-to-end discovery using the public `discover_plugins` helpers."""

    @mock.patch("importlib.import_module")
    @mock.patch("pkgutil.iter_modules")
    def test_discover_single_module(self, itermods, impmod) -> None:
        # --- stub package -----------------------------------------------------------------
        fake_pkg = mock.MagicMock()
        fake_pkg.__path__ = ["/fake"]
        fake_pkg.__name__ = "package"
        impmod.return_value = fake_pkg

        itermods.return_value = [
            (None, "package.mod", False),
        ]

        # module that houses one parser plugin
        class Plug(DummyParser):  # inherits async try_parse from DummyParser
            pass

        fake_mod = mock.MagicMock()
        fake_mod.__name__ = "package.mod"
        fake_mod.Plug = Plug
        impmod.side_effect = lambda n: fake_mod if n == "package.mod" else fake_pkg

        registry = PluginRegistry()
        PluginDiscovery(registry).discover_plugins(["package"])

        assert isinstance(registry.get_plugin("parser", "Plug"), Plug)

    # ------------------------------------------------------------------ #
    @mock.patch("importlib.import_module")
    def test_default_discovery_wrapper(self, impmod) -> None:
        impmod.return_value = mock.MagicMock()
        with mock.patch.object(PluginDiscovery, "discover_plugins") as spy:
            discover_default_plugins()
            spy.assert_called_once_with(["chuk_tool_processor.plugins"])

    @mock.patch("importlib.import_module")
    def test_custom_package_wrapper(self, impmod) -> None:
        impmod.return_value = mock.MagicMock()
        with mock.patch.object(PluginDiscovery, "discover_plugins") as spy:
            discover_plugins(["pkg1", "pkg2"])
            spy.assert_called_once_with(["pkg1", "pkg2"])


# --------------------------------------------------------------------------- #
# Global registry singleton smoke-test
# --------------------------------------------------------------------------- #
def test_global_registry_singleton() -> None:
    assert isinstance(plugin_registry, PluginRegistry)
