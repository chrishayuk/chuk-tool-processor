# chuk_tool_processor/registry/interface.py
"""
Defines the interface for tool registries.
"""
from typing import Protocol, Any, Dict, List, Optional, Tuple

# imports
from chuk_tool_processor.registry.metadata import ToolMetadata


class ToolRegistryInterface(Protocol):
    """
    Protocol for a tool registry. Implementations should allow registering tools
    and retrieving them by name and namespace.
    """
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
        ...

    def get_tool(self, name: str, namespace: str = "default") -> Optional[Any]:
        """
        Retrieve a registered tool by name and namespace.
        
        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").
            
        Returns:
            The tool implementation or None if not found.
        """
        ...

    def get_metadata(self, name: str, namespace: str = "default") -> Optional[ToolMetadata]:
        """
        Retrieve metadata for a registered tool.
        
        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").
            
        Returns:
            ToolMetadata if found, None otherwise.
        """
        ...

    def list_tools(self, namespace: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        List all registered tool names, optionally filtered by namespace.
        
        Args:
            namespace: Optional namespace filter.
            
        Returns:
            List of (namespace, name) tuples.
        """
        ...

    def list_namespaces(self) -> List[str]:
        """
        List all registered namespaces.
        
        Returns:
            List of namespace names.
        """
        ...