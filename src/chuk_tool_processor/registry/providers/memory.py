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
from chuk_tool_processor.registry.metadata import ToolInfo, ToolMetadata


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
        # Track deferred tools separately (metadata only, not loaded yet)
        # {namespace: {tool_name: ToolMetadata}}
        self._deferred_metadata: dict[str, dict[str, ToolMetadata]] = {}
        # Store pre-instantiated deferred tools separately (not active yet)
        # {namespace: {tool_name: tool_obj}}
        self._deferred_tools: dict[str, dict[str, Any]] = {}
        # Track which deferred tools have been loaded
        self._loaded_deferred_tools: set[str] = set()  # Set of "namespace.name"
        # Store stream_manager references for MCP tools by namespace
        self._stream_managers: dict[str, Any] = {}  # {namespace: StreamManager}
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
        """
        Register a tool in the registry asynchronously.

        Supports dotted names for automatic namespace extraction:
        - name="web.fetch_user" -> namespace="web", name="fetch_user"
        - name="fetch_user", namespace="web" -> namespace="web", name="fetch_user"
        - name="fetch_user" -> namespace="default", name="fetch_user"

        The explicit namespace parameter takes precedence over a dotted name
        only if namespace is not "default".
        """
        async with self._lock:
            # Determine the actual name and namespace
            key = name or getattr(tool, "__name__", None) or repr(tool)

            # Auto-parse dotted names: "web.fetch_user" -> namespace="web", name="fetch_user"
            # Only parse if namespace is still the default and name contains a dot
            if "." in key and namespace == "default":
                parts = key.split(".", 1)
                namespace = parts[0]
                key = parts[1]

            # ensure namespace buckets
            self._tools.setdefault(namespace, {})
            self._metadata.setdefault(namespace, {})
            self._deferred_metadata.setdefault(namespace, {})

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

            tool_metadata = ToolMetadata(**meta_dict)

            # Check if this is a deferred tool
            if tool_metadata.defer_loading:
                # Store metadata only, don't load the tool yet
                self._deferred_metadata[namespace][key] = tool_metadata
                # If tool is already instantiated (not via import_path), store it for later loading
                if tool_metadata.import_path is None and tool_metadata.mcp_factory_params is None:
                    # Store the pre-instantiated tool for deferred loading (separate from active tools)
                    self._deferred_tools.setdefault(namespace, {})[key] = tool
            else:
                # Eager loading (default behavior)
                self._tools[namespace][key] = tool
                self._metadata[namespace][key] = tool_metadata

    # ------------------------------------------------------------------ #
    # retrieval
    # ------------------------------------------------------------------ #

    async def get_tool(self, name: str, namespace: str = "default") -> Any | None:
        """
        Retrieve a tool by name and namespace asynchronously.

        If the tool is deferred and not yet loaded, it will be loaded automatically.
        """
        # Check if already loaded
        tool = self._tools.get(namespace, {}).get(name)
        if tool is not None:
            return tool

        # Check if it's a deferred tool
        key = f"{namespace}.{name}"
        if key not in self._loaded_deferred_tools and name in self._deferred_metadata.get(namespace, {}):
            # Lazy load the tool
            return await self.load_deferred_tool(name, namespace)

        return None

    async def get_tool_strict(self, name: str, namespace: str = "default") -> Any:
        """Get a tool with strict validation, raising if not found."""
        tool = await self.get_tool(name, namespace)
        if tool is None:
            # Gather helpful context for the error message
            all_tools = await self.list_tools()
            available_tools = [(t.namespace, t.name) for t in all_tools]
            available_namespaces = await self.list_namespaces()

            raise ToolNotFoundError(
                tool_name=name,
                namespace=namespace,
                available_tools=available_tools,
                available_namespaces=available_namespaces,
            )
        return tool

    async def get_metadata(self, name: str, namespace: str = "default") -> ToolMetadata | None:
        """
        Get metadata for a tool asynchronously.

        This works for both active and deferred tools.
        """
        # Check active tools first
        metadata = self._metadata.get(namespace, {}).get(name)
        if metadata is not None:
            return metadata

        # Check deferred tools
        return self._deferred_metadata.get(namespace, {}).get(name)

    # ------------------------------------------------------------------ #
    # listing helpers
    # ------------------------------------------------------------------ #

    async def list_tools(self, namespace: str | None = None) -> list[ToolInfo]:
        """
        Return a list of ToolInfo objects asynchronously.

        Args:
            namespace: Optional namespace filter.

        Returns:
            List of ToolInfo objects with namespace and name.
        """
        if namespace:
            return [ToolInfo(namespace=namespace, name=n) for n in self._tools.get(namespace, {})]

        result: list[ToolInfo] = []
        for ns, tools in self._tools.items():
            result.extend(ToolInfo(namespace=ns, name=n) for n in tools)
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

    # ------------------------------------------------------------------ #
    # Deferred loading support
    # ------------------------------------------------------------------ #

    async def search_deferred_tools(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[ToolMetadata]:
        """
        Search deferred tools by query and tags.

        Args:
            query: Natural language query to match against description and keywords
            tags: Optional list of tags to filter by
            limit: Maximum number of results to return

        Returns:
            List of ToolMetadata for matching deferred tools, sorted by relevance
        """
        candidates: list[tuple[float, ToolMetadata]] = []
        query_lower = query.lower()

        for namespace, tools in self._deferred_metadata.items():
            for tool_name, metadata in tools.items():
                # Skip if already loaded
                key = f"{namespace}.{tool_name}"
                if key in self._loaded_deferred_tools:
                    continue

                # Tag filtering
                if tags and not any(tag in metadata.tags for tag in tags):
                    continue

                # Calculate relevance score
                score = self._compute_relevance_score(query_lower, metadata)
                if score > 0:
                    candidates.append((score, metadata))

        # Sort by relevance score (descending) and return top N
        candidates.sort(reverse=True, key=lambda x: x[0])
        return [metadata for _, metadata in candidates[:limit]]

    def _compute_relevance_score(self, query_lower: str, metadata: ToolMetadata) -> float:
        """Compute relevance score for a tool based on query."""
        score = 0.0

        # Exact name match (highest priority)
        if query_lower == metadata.name.lower():
            score += 100.0

        # Name contains query
        if query_lower in metadata.name.lower():
            score += 50.0

        # Description match
        if metadata.description:
            desc_lower = metadata.description.lower()
            # Exact phrase match in description
            if query_lower in desc_lower:
                score += 30.0
            # Individual word matches
            query_words = query_lower.split()
            for word in query_words:
                if word in desc_lower:
                    score += 5.0

        # Search keywords match
        for keyword in metadata.search_keywords:
            if query_lower in keyword.lower():
                score += 20.0
            # Individual word matches
            query_words = query_lower.split()
            for word in query_words:
                if word in keyword.lower():
                    score += 3.0

        # Tag matches (partial credit)
        for tag in metadata.tags:
            if query_lower in tag.lower():
                score += 10.0

        return score

    async def load_deferred_tool(self, name: str, namespace: str = "default") -> Any:
        """
        Lazy load a deferred tool on-demand.

        Args:
            name: Tool name
            namespace: Tool namespace

        Returns:
            The loaded tool object

        Raises:
            ToolNotFoundError: If tool not found in deferred registry
            ImportError: If tool cannot be imported
        """
        key = f"{namespace}.{name}"

        # Check if already loaded
        if key in self._loaded_deferred_tools:
            return await self.get_tool(name, namespace)

        # Get metadata
        metadata = self._deferred_metadata.get(namespace, {}).get(name)
        if not metadata:
            raise ToolNotFoundError(
                tool_name=name,
                namespace=namespace,
                available_tools=[],
                available_namespaces=await self.list_namespaces(),
            )

        async with self._lock:
            # Double-check after acquiring lock
            if key in self._loaded_deferred_tools:
                return await self.get_tool(name, namespace)

            # Check if this is an MCP tool (has factory params)
            if metadata.mcp_factory_params is not None:
                # MCP tool - create via factory with stream_manager
                tool = await self._create_mcp_tool(metadata)
            elif metadata.import_path:
                # Regular tool - import the class
                tool = await self._import_tool(metadata.import_path)
            elif name in self._deferred_tools.get(namespace, {}):
                # Pre-instantiated tool (for testing)
                tool = self._deferred_tools[namespace][name]
            else:
                raise ValueError(f"Tool {key} is deferred but has no import_path or pre-instantiated tool")

            # Move from deferred to active
            self._tools.setdefault(namespace, {})
            self._metadata.setdefault(namespace, {})
            self._tools[namespace][name] = tool
            self._metadata[namespace][name] = metadata
            self._loaded_deferred_tools.add(key)

            return tool

    async def _import_tool(self, import_path: str) -> Any:
        """
        Dynamically import a tool from an import path.

        Args:
            import_path: Import path like 'module.submodule.ClassName'

        Returns:
            The imported tool class or function
        """
        parts = import_path.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid import path: {import_path}")

        module_path, class_name = parts

        # Dynamic import
        import importlib

        module = importlib.import_module(module_path)
        tool_class = getattr(module, class_name)

        return tool_class

    async def _create_mcp_tool(self, metadata: ToolMetadata) -> Any:
        """
        Create an MCP tool instance from stored factory parameters.

        Args:
            metadata: Tool metadata containing mcp_factory_params

        Returns:
            MCPTool instance
        """
        from chuk_tool_processor.mcp.mcp_tool import MCPTool

        if not metadata.mcp_factory_params:
            raise ValueError(f"Tool {metadata.name} has no mcp_factory_params")

        # Get stream_manager from stored namespace
        stream_manager = self._stream_managers.get(metadata.mcp_factory_params.namespace)

        if not stream_manager:
            raise ValueError(
                f"No StreamManager found for namespace '{metadata.mcp_factory_params.namespace}'. "
                f"Call set_stream_manager() before loading deferred MCP tools."
            )

        # Create MCPTool with stored parameters
        return MCPTool(
            tool_name=metadata.mcp_factory_params.tool_name,
            stream_manager=stream_manager,
            default_timeout=metadata.mcp_factory_params.default_timeout,
            enable_resilience=metadata.mcp_factory_params.enable_resilience,
            recovery_config=metadata.mcp_factory_params.recovery_config,
        )

    def set_stream_manager(self, namespace: str, stream_manager: Any) -> None:
        """
        Set the StreamManager for a namespace (used for deferred MCP tools).

        Args:
            namespace: Namespace for MCP tools
            stream_manager: StreamManager instance
        """
        self._stream_managers[namespace] = stream_manager

    async def get_active_tools(self, namespace: str | None = None) -> list[ToolInfo]:
        """
        Get only currently loaded (active) tools, excluding deferred tools.

        This is useful for generating tool schemas to send to LLM APIs,
        as it only includes tools that are ready to execute.

        Args:
            namespace: Optional namespace filter

        Returns:
            List of ToolInfo for active tools only
        """
        # This is the same as list_tools since _tools only contains loaded tools
        return await self.list_tools(namespace)

    async def get_deferred_tools(self, namespace: str | None = None) -> list[ToolInfo]:
        """
        Get list of deferred tools that haven't been loaded yet.

        Args:
            namespace: Optional namespace filter

        Returns:
            List of ToolInfo for deferred (not yet loaded) tools
        """
        if namespace:
            tools_in_ns = self._deferred_metadata.get(namespace, {})
            return [
                ToolInfo(namespace=namespace, name=name)
                for name in tools_in_ns
                if f"{namespace}.{name}" not in self._loaded_deferred_tools
            ]

        result: list[ToolInfo] = []
        for ns, tools in self._deferred_metadata.items():
            for name in tools:
                key = f"{ns}.{name}"
                if key not in self._loaded_deferred_tools:
                    result.append(ToolInfo(namespace=ns, name=name))
        return result
