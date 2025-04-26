# chuk_tool_processor/registry/providers/memory.py
"""
In-memory implementation of the tool registry.
"""

import inspect
from typing import Any, Dict, List, Optional, Tuple

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata


class InMemoryToolRegistry(ToolRegistryInterface):
    """
    In-memory implementation of ToolRegistryInterface with namespace support.
    
    This implementation stores tools and their metadata in memory,
    organized by namespace. It's suitable for single-process applications
    or for testing, but doesn't provide persistence or sharing across
    multiple processes.
    """
    def __init__(self):
        """Initialize the in-memory registry."""
        # Store tools as {namespace: {name: tool}}
        self._tools: Dict[str, Dict[str, Any]] = {}
        # Store metadata as {namespace: {name: metadata}}
        self._metadata: Dict[str, Dict[str, ToolMetadata]] = {}

    def register_tool(
        self, 
        tool: Any, 
        name: Optional[str] = None,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a tool implementation.

        Args:
            tool: The tool class or instance with an `execute` method.
            name: Optional explicit name; if omitted, uses tool.__name__.
            namespace: Namespace for the tool (default: "default").
            metadata: Optional additional metadata for the tool.
        """
        # Ensure the namespace exists
        if namespace not in self._tools:
            self._tools[namespace] = {}
            self._metadata[namespace] = {}
            
        # Determine tool name
        key = name or getattr(tool, "__name__", None) or repr(tool)
        
        # Register the tool
        self._tools[namespace][key] = tool
        
        # Create and store metadata
        is_async = inspect.iscoroutinefunction(getattr(tool, "execute", None))
        
        # Get description from docstring if available
        description = None
        if hasattr(tool, "__doc__") and tool.__doc__:
            description = inspect.getdoc(tool)
        
        # Create metadata object
        meta_dict = {
            "name": key,
            "namespace": namespace,
            "is_async": is_async
        }
        
        # Add description if available (but don't override metadata if provided)
        if description and not (metadata and "description" in metadata):
            meta_dict["description"] = description
            
        # Add any additional metadata
        if metadata:
            meta_dict.update(metadata)
            
        tool_metadata = ToolMetadata(**meta_dict)
        
        self._metadata[namespace][key] = tool_metadata

    def get_tool(self, name: str, namespace: str = "default") -> Optional[Any]:
        """
        Retrieve a registered tool by name and namespace.
        
        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").
            
        Returns:
            The tool implementation or None if not found.
        """
        if namespace not in self._tools:
            return None
        return self._tools[namespace].get(name)

    def get_tool_strict(self, name: str, namespace: str = "default") -> Any:
        """
        Retrieve a registered tool by name and namespace, raising an exception if not found.
        
        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").
            
        Returns:
            The tool implementation.
            
        Raises:
            ToolNotFoundError: If the tool is not found.
        """
        tool = self.get_tool(name, namespace)
        if tool is None:
            raise ToolNotFoundError(f"{namespace}.{name}")
        return tool

    def get_metadata(self, name: str, namespace: str = "default") -> Optional[ToolMetadata]:
        """
        Retrieve metadata for a registered tool.
        
        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").
            
        Returns:
            ToolMetadata if found, None otherwise.
        """
        if namespace not in self._metadata:
            return None
        return self._metadata[namespace].get(name)

    def list_tools(self, namespace: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        List all registered tool names, optionally filtered by namespace.
        
        Args:
            namespace: Optional namespace filter.
            
        Returns:
            List of (namespace, name) tuples.
        """
        result = []
        
        if namespace:
            # List tools in specific namespace
            if namespace in self._tools:
                for name in self._tools[namespace].keys():
                    result.append((namespace, name))
        else:
            # List all tools
            for ns, tools in self._tools.items():
                for name in tools.keys():
                    result.append((ns, name))
                    
        return result

    def list_namespaces(self) -> List[str]:
        """
        List all registered namespaces.
        
        Returns:
            List of namespace names.
        """
        return list(self._tools.keys())