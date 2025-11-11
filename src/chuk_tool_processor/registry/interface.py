# chuk_tool_processor/registry/interface.py
"""
Defines the interface for asynchronous tool registries.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

# imports
from chuk_tool_processor.registry.metadata import ToolInfo, ToolMetadata

T = TypeVar("T")


@runtime_checkable
class ToolRegistryInterface(Protocol):
    """
    Protocol for an async tool registry. Implementations should allow registering tools
    and retrieving them by name and namespace.
    """

    async def register_tool(
        self,
        tool: Any,
        name: str | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a tool implementation asynchronously.

        Args:
            tool: The tool class or instance with an `execute` method.
            name: Optional explicit name; if omitted, uses tool.__name__.
            namespace: Namespace for the tool (default: "default").
            metadata: Optional additional metadata for the tool.
        """
        ...  # pragma: no cover

    async def get_tool(self, name: str, namespace: str = "default") -> Any | None:
        """
        Retrieve a registered tool by name and namespace asynchronously.

        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").

        Returns:
            The tool implementation or None if not found.
        """
        ...  # pragma: no cover

    async def get_tool_strict(self, name: str, namespace: str = "default") -> Any:
        """
        Retrieve a registered tool by name and namespace, raising if not found.

        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").

        Returns:
            The tool implementation.

        Raises:
            ToolNotFoundError: If the tool is not found in the registry.
        """
        ...  # pragma: no cover

    async def get_metadata(self, name: str, namespace: str = "default") -> ToolMetadata | None:
        """
        Retrieve metadata for a registered tool asynchronously.

        Args:
            name: The name of the tool.
            namespace: The namespace of the tool (default: "default").

        Returns:
            ToolMetadata if found, None otherwise.
        """
        ...  # pragma: no cover

    async def list_tools(self, namespace: str | None = None) -> list[ToolInfo]:
        """
        List all registered tool names asynchronously, optionally filtered by namespace.

        Args:
            namespace: Optional namespace filter.

        Returns:
            List of ToolInfo objects containing namespace and name.

        Example:
            >>> tools = await registry.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool.namespace}:{tool.name}")
        """
        ...  # pragma: no cover

    async def list_namespaces(self) -> list[str]:
        """
        List all registered namespaces asynchronously.

        Returns:
            List of namespace names.
        """
        ...  # pragma: no cover

    async def list_metadata(self, namespace: str | None = None) -> list[ToolMetadata]:
        """
        Return all ToolMetadata objects asynchronously.

        Args:
            namespace: Optional filter by namespace.
                • None (default) - metadata from all namespaces
                • "some_ns" - only that namespace

        Returns:
            List of ToolMetadata objects.
        """
        ...  # pragma: no cover
