# chuk_tool_processor/mcp/transport/base_transport.py
"""
Abstract transport layer for MCP communication.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MCPBaseTransport(ABC):
    """
    Abstract base class for MCP transport mechanisms.
    """

    # ------------------------------------------------------------------ #
    #  connection lifecycle                                              #
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Establish the connection.

        Returns
        -------
        bool
            ``True`` if the connection was initialised successfully.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Tear down the connection and release all resources."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  diagnostics                                                       #
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def send_ping(self) -> bool:
        """
        Send a **ping** request.

        Returns
        -------
        bool
            ``True`` on success, ``False`` otherwise.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  tool handling                                                     #
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def get_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list with *all* tool definitions exposed by the server.
        """
        raise NotImplementedError

    @abstractmethod
    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute *tool_name* with *arguments* and return the normalised result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  new: resources & prompts                                          #
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def list_resources(self) -> Dict[str, Any]:
        """
        Retrieve the server’s resources catalogue.

        Expected shape::
            { "resources": [ {...}, ... ], "nextCursor": "…", … }
        """
        raise NotImplementedError

    @abstractmethod
    async def list_prompts(self) -> Dict[str, Any]:
        """
        Retrieve the server’s prompt catalogue.

        Expected shape::
            { "prompts": [ {...}, ... ], "nextCursor": "…", … }
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    #  optional helper (non-abstract)                                    #
    # ------------------------------------------------------------------ #
    def get_streams(self):
        """
        Return a list of ``(read_stream, write_stream)`` tuples.

        Transports that do not expose their low-level streams can simply leave
        the default implementation (which returns an empty list).
        """
        return []
