#!/usr/bin/env python
# chuk_tool_processor/mcp/mcp_tool.py
"""
MCP tool shim that delegates execution to a StreamManager,
handling its own lazy bootstrap when needed.
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
    """

    # ------------------------------------------------------------------ #
    def __init__(
        self,
        tool_name: str,
        stream_manager: Optional[StreamManager] = None,
        *,
        cfg_file: str = "",
        servers: Optional[List[str]] = None,
        server_names: Optional[Dict[int, str]] = None,
        namespace: str = "stdio",
        default_timeout: Optional[float] = None
    ) -> None:
        self.tool_name = tool_name
        self._sm: Optional[StreamManager] = stream_manager
        self.default_timeout = default_timeout

        # Boot-strap parameters (only needed if _sm is None)
        self._cfg_file = cfg_file
        self._servers = servers or []
        self._server_names = server_names or {}
        self._namespace = namespace

        self._sm_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    async def _ensure_stream_manager(self) -> StreamManager:
        """
        Lazily create / attach a StreamManager.

        Importing ``setup_mcp_stdio`` *inside* this function prevents the
        circular-import seen earlier.  ★
        """
        if self._sm is not None:
            return self._sm

        async with self._sm_lock:
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