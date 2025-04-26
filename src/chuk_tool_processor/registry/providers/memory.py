# chuk_tool_processor/registry/providers/memory.py
# chuk_tool_processor/registry/providers/memory.py
"""
In-memory implementation of the tool registry.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Tuple

from chuk_tool_processor.core.exceptions import ToolNotFoundError
from chuk_tool_processor.registry.interface import ToolRegistryInterface
from chuk_tool_processor.registry.metadata import ToolMetadata


class InMemoryToolRegistry(ToolRegistryInterface):
    """
    In-memory implementation of ToolRegistryInterface with namespace support.

    Suitable for single-process apps or tests; not persisted across processes.
    """

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #

    def __init__(self) -> None:
        # {namespace: {tool_name: tool_obj}}
        self._tools: Dict[str, Dict[str, Any]] = {}
        # {namespace: {tool_name: ToolMetadata}}
        self._metadata: Dict[str, Dict[str, ToolMetadata]] = {}

    # ------------------------------------------------------------------ #
    # registration
    # ------------------------------------------------------------------ #

    def register_tool(
        self,
        tool: Any,
        name: Optional[str] = None,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        # ensure namespace buckets
        self._tools.setdefault(namespace, {})
        self._metadata.setdefault(namespace, {})

        key = name or getattr(tool, "__name__", None) or repr(tool)
        self._tools[namespace][key] = tool

        # build metadata -------------------------------------------------
        is_async = inspect.iscoroutinefunction(getattr(tool, "execute", None))

        # default description -> docstring
        description = (
            (inspect.getdoc(tool) or "").strip()
            if not (metadata and "description" in metadata)
            else None
        )

        meta_dict: Dict[str, Any] = {
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

    def get_tool(self, name: str, namespace: str = "default") -> Optional[Any]:
        return self._tools.get(namespace, {}).get(name)

    def get_tool_strict(self, name: str, namespace: str = "default") -> Any:
        tool = self.get_tool(name, namespace)
        if tool is None:
            raise ToolNotFoundError(f"{namespace}.{name}")
        return tool

    def get_metadata(
        self, name: str, namespace: str = "default"
    ) -> Optional[ToolMetadata]:
        return self._metadata.get(namespace, {}).get(name)

    # ------------------------------------------------------------------ #
    # listing helpers
    # ------------------------------------------------------------------ #

    def list_tools(self, namespace: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Return a list of ``(namespace, name)`` tuples.
        """
        if namespace:
            return [
                (namespace, n) for n in self._tools.get(namespace, {}).keys()
            ]

        result: List[Tuple[str, str]] = []
        for ns, tools in self._tools.items():
            result.extend((ns, n) for n in tools.keys())
        return result

    def list_namespaces(self) -> List[str]:
        return list(self._tools.keys())

    def list_metadata(self, namespace: str | None = None) -> List[ToolMetadata]:
        """
        Return *all* :class:`ToolMetadata` objects.

        Parameters
        ----------
        namespace
            • ``None`` *(default)* – metadata from **all** namespaces  
            • ``"some_ns"``        – only that namespace
        """
        if namespace is not None:
            return list(self._metadata.get(namespace, {}).values())

        # flatten
        result: List[ToolMetadata] = []
        for ns_meta in self._metadata.values():
            result.extend(ns_meta.values())
        return result
