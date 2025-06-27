#!/usr/bin/env python
# chuk_tool_processor/mcp/mcp_tool.py
"""
MCP tool shim that delegates execution to a StreamManager,
handling its own lazy bootstrap when needed.

FIXED: Added subprocess serialization support by implementing __getstate__ and __setstate__
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.mcp.stream_manager import StreamManager

logger = get_logger("chuk_tool_processor.mcp.mcp_tool")


class MCPTool:
    """
    Wrap a remote MCP tool so it can be called like a local tool.

    You may pass an existing ``StreamManager`` *positionally* (for legacy
    code) or via the named parameter.

    If no ``StreamManager`` is supplied the class will start one on first
    use via ``setup_mcp_stdio``.
    
    FIXED: Added serialization support for subprocess execution.
    """

    # ------------------------------------------------------------------ #
    def __init__(
        self,
        tool_name: str = "",
        stream_manager: Optional[StreamManager] = None,
        *,
        cfg_file: str = "",
        servers: Optional[List[str]] = None,
        server_names: Optional[Dict[int, str]] = None,
        namespace: str = "stdio",
        default_timeout: Optional[float] = None
    ) -> None:
        if not tool_name:
            raise ValueError(
                "MCPTool requires a tool_name. "
                "This error usually occurs during subprocess serialization. "
                "Make sure the tool is properly registered with a name."
            )
        
        self.tool_name = tool_name
        self._sm: Optional[StreamManager] = stream_manager
        self.default_timeout = default_timeout

        # Boot-strap parameters (only needed if _sm is None)
        self._cfg_file = cfg_file
        self._servers = servers or []
        self._server_names = server_names or {}
        self._namespace = namespace

        # Create lock only when needed (not during deserialization)
        self._sm_lock: Optional[asyncio.Lock] = None

    def _ensure_lock(self) -> asyncio.Lock:
        """Ensure the lock exists, creating it if necessary."""
        if self._sm_lock is None:
            self._sm_lock = asyncio.Lock()
        return self._sm_lock

    # ------------------------------------------------------------------ #
    # Serialization support for subprocess execution
    # ------------------------------------------------------------------ #
    def __getstate__(self) -> Dict[str, Any]:
        """
        Custom serialization for pickle support.
        
        Excludes non-serializable async components and stream manager.
        The subprocess will recreate these as needed.
        """
        state = self.__dict__.copy()
        
        # Remove non-serializable items
        state['_sm'] = None  # StreamManager will be recreated in subprocess
        state['_sm_lock'] = None  # Lock will be recreated when needed
        
        # Ensure we have the necessary configuration for subprocess
        # If no servers specified, default to the tool name (common pattern)
        if not state.get('_servers'):
            # Extract server name from tool_name (e.g., "get_current_time" -> "time")
            # This is a heuristic - adjust based on your naming convention
            if 'time' in self.tool_name.lower():
                state['_servers'] = ['time']
                state['_server_names'] = {0: 'time'}
            else:
                # Default fallback - use the tool name itself
                state['_servers'] = [self.tool_name]
                state['_server_names'] = {0: self.tool_name}
        
        # Ensure we have a config file path
        if not state.get('_cfg_file'):
            state['_cfg_file'] = 'server_config.json'
        
        logger.debug(f"Serializing MCPTool '{self.tool_name}' for subprocess with servers: {state['_servers']}")
        return state
    
    def __setstate__(self, state: Dict[str, Any]) -> None:
        """
        Custom deserialization for pickle support.
        
        Restores the object state and ensures required fields are set.
        """
        self.__dict__.update(state)
        
        # Ensure critical fields exist
        if not hasattr(self, 'tool_name') or not self.tool_name:
            raise ValueError("Invalid MCPTool state: missing tool_name")
        
        # Initialize transient fields
        self._sm = None
        self._sm_lock = None
        
        logger.debug(f"Deserialized MCPTool '{self.tool_name}' in subprocess")

    # ------------------------------------------------------------------ #
    async def _ensure_stream_manager(self) -> StreamManager:
        """
        Lazily create / attach a StreamManager.

        Importing ``setup_mcp_stdio`` *inside* this function prevents the
        circular-import seen earlier.  ★
        """
        if self._sm is not None:
            return self._sm

        # Use the lock, creating it if needed
        async with self._ensure_lock():
            if self._sm is None:  # re-check inside lock
                logger.info(
                    "Boot-strapping MCP stdio transport for '%s'", self.tool_name
                )

                # ★  local import avoids circular dependency
                from chuk_tool_processor.mcp.setup_mcp_stdio import setup_mcp_stdio

                _, self._sm = await setup_mcp_stdio(
                    config_file=self._cfg_file,
                    servers=self._servers,
                    server_names=self._server_names,
                    namespace=self._namespace,
                )

        return self._sm  # type: ignore[return-value]

    async def execute(self, timeout: Optional[float] = None, **kwargs: Any) -> Any:
        """
        Invoke the remote MCP tool, guaranteeing that *one* timeout is enforced.

        Parameters
        ----------
        timeout : float | None
            If provided, forward this to StreamManager.  Otherwise fall back
            to ``self.default_timeout``.
        **kwargs
            Arguments forwarded to the tool.

        Returns
        -------
        Any
            The ``content`` of the remote tool response.

        Raises
        ------
        RuntimeError
            The remote tool returned an error payload.
        asyncio.TimeoutError
            The call exceeded the chosen timeout.
        """
        sm = await self._ensure_stream_manager()

        # Pick the timeout we will enforce (may be None = no limit).
        effective_timeout: Optional[float] = (
            timeout if timeout is not None else self.default_timeout
        )

        call_kwargs: dict[str, Any] = {
            "tool_name": self.tool_name,
            "arguments": kwargs,
        }
        if effective_timeout is not None:
            call_kwargs["timeout"] = effective_timeout
            logger.debug(
                "Forwarding timeout=%ss to StreamManager for tool '%s'",
                effective_timeout,
                self.tool_name,
            )

        try:
            result = await sm.call_tool(**call_kwargs)
        except asyncio.TimeoutError:
            logger.warning(
                "MCP tool '%s' timed out after %ss",
                self.tool_name,
                effective_timeout,
            )
            raise

        if result.get("isError"):
            err = result.get("error", "Unknown error")
            logger.error("Remote MCP error from '%s': %s", self.tool_name, err)
            raise RuntimeError(err)

        return result.get("content")

    # ------------------------------------------------------------------ #
    # Legacy method name support
    async def _aexecute(self, timeout: Optional[float] = None, **kwargs: Any) -> Any:
        """Legacy alias for execute() method."""
        return await self.execute(timeout=timeout, **kwargs)

    # ------------------------------------------------------------------ #
    # Utility methods for debugging
    # ------------------------------------------------------------------ #
    def is_serializable(self) -> bool:
        """Check if this tool can be serialized (for debugging)."""
        try:
            import pickle
            pickle.dumps(self)
            return True
        except Exception:
            return False
    
    def get_serialization_info(self) -> Dict[str, Any]:
        """Get information about what would be serialized."""
        state = self.__getstate__()
        return {
            "tool_name": state.get("tool_name"),
            "namespace": state.get("_namespace"),
            "servers": state.get("_servers"),
            "cfg_file": state.get("_cfg_file"),
            "has_stream_manager": state.get("_sm") is not None,
            "serializable_size": len(str(state))
        }