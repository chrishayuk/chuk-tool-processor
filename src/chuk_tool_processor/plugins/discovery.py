# chuk_tool_processor/plugins/discovery.py
import importlib
import inspect
import pkgutil
import sys
from typing import Dict, List, Optional, Set, Type, Any
import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Registry for discovered plugins.
    """
    def __init__(self):
        self._plugins: Dict[str, Dict[str, Any]] = {}
    
    def register_plugin(self, category: str, name: str, plugin: Any) -> None:
        """
        Register a plugin in the registry.
        
        Args:
            category: Plugin category (e.g., "parser", "executor").
            name: Plugin name.
            plugin: Plugin implementation.
        """
        # Ensure category exists
        if category not in self._plugins:
            self._plugins[category] = {}
            
        # Register plugin
        self._plugins[category][name] = plugin
        logger.debug(f"Registered plugin: {category}.{name}")
    
    def get_plugin(self, category: str, name: str) -> Optional[Any]:
        """
        Get a plugin from the registry.
        
        Args:
            category: Plugin category.
            name: Plugin name.
            
        Returns:
            Plugin implementation or None if not found.
        """
        return self._plugins.get(category, {}).get(name)
    
    def list_plugins(self, category: Optional[str] = None) -> Dict[str, List[str]]:
        """
        List registered plugins.
        
        Args:
            category: Optional category filter.
            
        Returns:
            Dict mapping categories to lists of plugin names.
        """
        if category:
            return {category: list(self._plugins.get(category, {}).keys())}
        else:
            return {cat: list(plugins.keys()) for cat, plugins in self._plugins.items()}


class PluginDiscovery:
    """
    Discovers and loads plugins from specified packages.
    """
    def __init__(self, registry: PluginRegistry):
        """
        Initialize the plugin discovery.
        
        Args:
            registry: Plugin registry to register discovered plugins.
        """
        self.registry = registry
        self._discovered_modules: Set[str] = set()
    
    def discover_plugins(self, package_paths: List[str]) -> None:
        """
        Discover plugins in the specified packages.
        
        Args:
            package_paths: List of package paths to search for plugins.
        """
        for package_path in package_paths:
            self._discover_in_package(package_path)
    
    def _discover_in_package(self, package_path: str) -> None:
        """
        Discover plugins in a single package.
        
        Args:
            package_path: Package path to search.
        """
        try:
            # Import the package
            package = importlib.import_module(package_path)
            
            # Walk through package modules
            for _, name, is_pkg in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
                # Skip if already processed
                if name in self._discovered_modules:
                    continue
                    
                self._discovered_modules.add(name)
                
                # Process module
                self._process_module(name)
                
                # Recurse into subpackages
                if is_pkg:
                    self._discover_in_package(name)
                    
        except ImportError as e:
            logger.warning(f"Failed to import package {package_path}: {e}")
    
    def _process_module(self, module_name: str) -> None:
        """
        Process a module for plugins.
        
        Args:
            module_name: Module name to process.
        """
        try:
            # Import the module
            module = importlib.import_module(module_name)
            
            # Find all classes in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                
                # Skip non-classes
                if not inspect.isclass(attr):
                    continue
                
                # Check if it's a plugin
                self._register_if_plugin(attr)
                
        except ImportError as e:
            logger.warning(f"Failed to import module {module_name}: {e}")
    
    def _register_if_plugin(self, cls: Type) -> None:
        """
        Register a class if it's a plugin.
        
        Args:
            cls: Class to check.
        """
        # Check if it's a parser plugin
        if hasattr(cls, "try_parse") and callable(getattr(cls, "try_parse")):
            self.registry.register_plugin("parser", cls.__name__, cls())
        
        # Check if it's an execution strategy
        if "ExecutionStrategy" in [base.__name__ for base in cls.__mro__]:
            self.registry.register_plugin("execution_strategy", cls.__name__, cls)
        
        # Check if it has plugin metadata
        if hasattr(cls, "_plugin_meta"):
            meta = getattr(cls, "_plugin_meta")
            self.registry.register_plugin(meta.get("category", "unknown"), meta.get("name", cls.__name__), cls())


def plugin(category: str, name: Optional[str] = None):
    """
    Decorator to mark a class as a plugin.
    
    Example:
        @plugin(category="parser", name="custom_format")
        class CustomFormatParser:
            def try_parse(self, raw: str):
                ...
    """
    def decorator(cls):
        cls._plugin_meta = {
            "category": category,
            "name": name or cls.__name__
        }
        return cls
    return decorator


# Initialize the global plugin registry
plugin_registry = PluginRegistry()


# Function to discover plugins in the default package
def discover_default_plugins():
    """
    Discover plugins in the default package.
    """
    discovery = PluginDiscovery(plugin_registry)
    discovery.discover_plugins(["chuk_tool_processor.plugins"])


# Function to discover plugins in custom packages
def discover_plugins(package_paths: List[str]):
    """
    Discover plugins in custom packages.
    
    Args:
        package_paths: List of package paths to search for plugins.
    """
    discovery = PluginDiscovery(plugin_registry)
    discovery.discover_plugins(package_paths)