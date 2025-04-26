# tests/plugins/test_discovery.py
import pytest
import importlib
import sys
from unittest import mock
from typing import List, Dict, Any

from chuk_tool_processor.plugins.discovery import (
    PluginRegistry,
    PluginDiscovery,
    plugin,
    plugin_registry,
    discover_default_plugins,
    discover_plugins
)


class TestPluginRegistry:
    """Tests for the PluginRegistry class."""

    def test_init_creates_empty_registry(self):
        """Test that initializing creates an empty registry."""
        registry = PluginRegistry()
        assert registry._plugins == {}

    def test_register_plugin(self):
        """Test registering a plugin."""
        registry = PluginRegistry()
        registry.register_plugin("test_category", "test_plugin", object())
        
        assert "test_category" in registry._plugins
        assert "test_plugin" in registry._plugins["test_category"]
        assert isinstance(registry._plugins["test_category"]["test_plugin"], object)

    def test_register_plugin_twice(self):
        """Test registering a plugin twice overwrites the first one."""
        registry = PluginRegistry()
        plugin1 = object()
        plugin2 = object()
        
        registry.register_plugin("test_category", "test_plugin", plugin1)
        registry.register_plugin("test_category", "test_plugin", plugin2)
        
        assert registry._plugins["test_category"]["test_plugin"] is plugin2

    def test_get_plugin(self):
        """Test getting a registered plugin."""
        registry = PluginRegistry()
        plugin_obj = object()
        registry.register_plugin("test_category", "test_plugin", plugin_obj)
        
        result = registry.get_plugin("test_category", "test_plugin")
        assert result is plugin_obj

    def test_get_nonexistent_plugin(self):
        """Test getting a non-existent plugin returns None."""
        registry = PluginRegistry()
        result = registry.get_plugin("nonexistent", "nonexistent")
        assert result is None

    def test_list_plugins_all(self):
        """Test listing all plugins."""
        registry = PluginRegistry()
        registry.register_plugin("category1", "plugin1", object())
        registry.register_plugin("category1", "plugin2", object())
        registry.register_plugin("category2", "plugin3", object())
        
        result = registry.list_plugins()
        
        assert "category1" in result
        assert "category2" in result
        assert set(result["category1"]) == {"plugin1", "plugin2"}
        assert set(result["category2"]) == {"plugin3"}

    def test_list_plugins_by_category(self):
        """Test listing plugins by category."""
        registry = PluginRegistry()
        registry.register_plugin("category1", "plugin1", object())
        registry.register_plugin("category1", "plugin2", object())
        registry.register_plugin("category2", "plugin3", object())
        
        result = registry.list_plugins("category1")
        
        assert list(result.keys()) == ["category1"]
        assert set(result["category1"]) == {"plugin1", "plugin2"}


class TestPluginDecorator:
    """Tests for the @plugin decorator."""

    def test_plugin_decorator(self):
        """Test that the plugin decorator sets _plugin_meta correctly."""
        @plugin(category="test_category", name="test_name")
        class TestPlugin:
            pass
        
        assert hasattr(TestPlugin, "_plugin_meta")
        assert TestPlugin._plugin_meta["category"] == "test_category"
        assert TestPlugin._plugin_meta["name"] == "test_name"

    def test_plugin_decorator_default_name(self):
        """Test that the plugin decorator uses class name when name not provided."""
        @plugin(category="test_category")
        class TestPlugin:
            pass
        
        assert TestPlugin._plugin_meta["name"] == "TestPlugin"


# Mock classes for testing plugin discovery
class MockParserPlugin:
    def try_parse(self, raw: str) -> List[Dict[str, Any]]:
        return []

class MockExecutionStrategy:
    pass

class MockGenericPlugin:
    pass


@plugin(category="custom", name="custom_plugin")
class MockCustomPlugin:
    pass


class TestPluginDiscovery:
    """Tests for the PluginDiscovery class."""

    def test_register_if_plugin_parser(self):
        """Test registering a parser plugin."""
        registry = PluginRegistry()
        discovery = PluginDiscovery(registry)
        
        discovery._register_if_plugin(MockParserPlugin)
        
        assert registry.get_plugin("parser", "MockParserPlugin") is not None
        assert isinstance(registry.get_plugin("parser", "MockParserPlugin"), MockParserPlugin)

    def test_register_if_plugin_execution_strategy(self):
        """Test registering an execution strategy."""
        registry = PluginRegistry()
        discovery = PluginDiscovery(registry)
        
        # Create a class that 'looks like' it inherits from ExecutionStrategy
        # without actually modifying __mro__ which is not writable
        class ExecutionStrategy:
            pass
            
        class MockStrategy(ExecutionStrategy):
            pass
        
        discovery._register_if_plugin(MockStrategy)
        
        assert registry.get_plugin("execution_strategy", "MockStrategy") is not None
        assert registry.get_plugin("execution_strategy", "MockStrategy") == MockStrategy

    def test_register_if_plugin_meta(self):
        """Test registering a plugin with _plugin_meta."""
        registry = PluginRegistry()
        discovery = PluginDiscovery(registry)
        
        discovery._register_if_plugin(MockCustomPlugin)
        
        assert registry.get_plugin("custom", "custom_plugin") is not None
        assert isinstance(registry.get_plugin("custom", "custom_plugin"), MockCustomPlugin)

    def test_register_if_not_plugin(self):
        """Test that non-plugins aren't registered."""
        registry = PluginRegistry()
        discovery = PluginDiscovery(registry)
        
        discovery._register_if_plugin(MockGenericPlugin)
        
        plugins = registry.list_plugins()
        assert not plugins  # Should be empty


class TestPluginDiscoveryIntegration:
    """Integration tests for plugin discovery."""

    @mock.patch("importlib.import_module")
    @mock.patch("pkgutil.iter_modules")
    def test_discover_in_package_single_module(self, mock_iter_modules, mock_import_module):
        """Test discovering plugins in a single package."""
        # Set up mocks
        mock_package = mock.MagicMock()
        # Important: Set __path__ and __name__ attributes on the mock package
        mock_package.__path__ = ["/fake/path"]
        mock_package.__name__ = "package"
        mock_import_module.return_value = mock_package
        mock_iter_modules.return_value = [
            (None, "package.module", False),
        ]
        
        # Mock the imported module
        mock_module = mock.MagicMock()
        mock_module.__name__ = "package.module"
        
        # Add a plugin class to the module
        class TestPlugin:
            def try_parse(self, raw: str):
                return []
        
        mock_module.TestPlugin = TestPlugin
        
        # Set up module's dir function properly
        mock_dir_result = ["TestPlugin"]
        mock_module.__dir__ = mock.MagicMock(return_value=mock_dir_result)
        
        # Make importlib.import_module return our mock module
        mock_import_module.side_effect = lambda name: mock_module if name == "package.module" else mock_package
        
        # Run discovery
        registry = PluginRegistry()
        discovery = PluginDiscovery(registry)
        discovery.discover_plugins(["package"])
        
        # Verify plugin was discovered
        assert registry.get_plugin("parser", "TestPlugin") is not None

    @mock.patch("importlib.import_module")
    def test_discover_default_plugins(self, mock_import_module):
        """Test discover_default_plugins function."""
        # Mock the importlib.import_module to avoid actually importing
        mock_import_module.return_value = mock.MagicMock()
        
        # Mock the PluginDiscovery.discover_plugins method
        with mock.patch.object(PluginDiscovery, "discover_plugins") as mock_discover:
            discover_default_plugins()
            mock_discover.assert_called_once_with(["chuk_tool_processor.plugins"])

    @mock.patch("importlib.import_module")
    def test_discover_plugins_custom_packages(self, mock_import_module):
        """Test discover_plugins function with custom packages."""
        # Mock the importlib.import_module to avoid actually importing
        mock_import_module.return_value = mock.MagicMock()
        
        # Mock the PluginDiscovery.discover_plugins method
        with mock.patch.object(PluginDiscovery, "discover_plugins") as mock_discover:
            discover_plugins(["custom.package1", "custom.package2"])
            mock_discover.assert_called_once_with(["custom.package1", "custom.package2"])


def test_global_plugin_registry_exists():
    """Test that the global plugin registry exists and is initialized."""
    assert isinstance(plugin_registry, PluginRegistry)