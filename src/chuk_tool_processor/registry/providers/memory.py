# chuk_tool_processor/registry/providers/memory.py
"""
In-memory implementation of the asynchronous tool registry.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata


class InMemoryToolRegistry(ToolRegistryInterface):
    """
    In-memory implementation of the async ToolRegistryInterface with namespace support.

    Suitable for single-process apps or tests; not persisted across processes.
    Thread-safe with asyncio locking.
    """

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #

    def __init__(self) -> None:
        # {namespace: {tool_name: tool_obj}}
        self._tools: dict[str, dict[str, Any]] = {}
        # {namespace: {tool_name: ToolMetadata}}
        self._metadata: dict[str, dict[str, ToolMetadata]] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # registration
    # ------------------------------------------------------------------ #

    async def register_tool(
        self,
        tool: Any,
        name: str | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool in the registry asynchronously."""
        async with self._lock:
            # ensure namespace buckets
            self._tools.setdefault(namespace, {})
            self._metadata.setdefault(namespace, {})

            key = name or getattr(tool, "__name__", None) or repr(tool)
            self._tools[namespace][key] = tool

            # build metadata -------------------------------------------------
            is_async = inspect.iscoroutinefunction(getattr(tool, "execute", None))

            # default description -> docstring
            description = (inspect.getdoc(tool) or "").strip() if not (metadata and "description" in metadata) else None

            meta_dict: dict[str, Any] = {
                "name": key,
                "namespace": namespace,
                "is_async": is_async,
            }
            if description:
                meta_dict["description"] = description
            if metadata:
                meta_dict.update(metadata)

            self._metadata[namespace][key] = ToolMetadata(**meta_dict)

    # ------------------------------------------------------------------ #
    # retrieval
    # ------------------------------------------------------------------ #

    async def get_tool(self, name: str, namespace: str = "default") -> Any | None:
        """Retrieve a tool by name and namespace asynchronously."""
        # Read operations don't need locking for better concurrency
        return self._tools.get(namespace, {}).get(name)

    async def get_tool_strict(self, name: str, namespace: str = "default") -> Any:
        """Get a tool with strict validation, raising if not found."""
        tool = await self.get_tool(name, namespace)
        if tool is None:
            raise ToolNotFoundError(f"{namespace}.{name}")
        return tool

    async def get_metadata(self, name: str, namespace: str = "default") -> ToolMetadata | None:
        """Get metadata for a tool asynchronously."""
        return self._metadata.get(namespace, {}).get(name)

    # ------------------------------------------------------------------ #
    # listing helpers
    # ------------------------------------------------------------------ #

    async def list_tools(self, namespace: str | None = None) -> list[tuple[str, str]]:
        """
        Return a list of ``(namespace, name)`` tuples asynchronously.
        """
        if namespace:
            return [(namespace, n) for n in self._tools.get(namespace, {})]

        result: list[tuple[str, str]] = []
        for ns, tools in self._tools.items():
            result.extend((ns, n) for n in tools)
        return result

    async def list_namespaces(self) -> list[str]:
        """List all namespaces asynchronously."""
        return list(self._tools.keys())

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
        if namespace is not None:
            return list(self._metadata.get(namespace, {}).values())

        # flatten
        result: list[ToolMetadata] = []
        for ns_meta in self._metadata.values():
            result.extend(ns_meta.values())
        return result
