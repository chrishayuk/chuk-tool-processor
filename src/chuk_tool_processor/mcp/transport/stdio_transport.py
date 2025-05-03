# chuk_tool_processor/mcp/transport/stdio_transport.py
from __future__ import annotations

from contextlib import AsyncExitStack
import json
from typing import Dict, Any, List, Optional

# ------------------------------------------------------------------ #
#  Local import                                                      #
# ------------------------------------------------------------------ #
from .base_transport import MCPBaseTransport

# ------------------------------------------------------------------ #
#  chuk-protocol imports                                             #
# ------------------------------------------------------------------ #
from chuk_mcp.mcp_client.transport.stdio.stdio_client import stdio_client
from chuk_mcp.mcp_client.messages.initialize.send_messages import send_initialize
from chuk_mcp.mcp_client.messages.ping.send_messages import send_ping

# tools
from chuk_mcp.mcp_client.messages.tools.send_messages import (
    send_tools_call,
    send_tools_list,
)

# NEW: resources & prompts
from chuk_mcp.mcp_client.messages.resources.send_messages import (
    send_resources_list,
)
from chuk_mcp.mcp_client.messages.prompts.send_messages import (
    send_prompts_list,
)


class StdioTransport(MCPBaseTransport):
    """
    Stdio transport for MCP communication.
    """

    def __init__(self, server_params):
        self.server_params = server_params
        self.read_stream = None
        self.write_stream = None
        self._context_stack: Optional[AsyncExitStack] = None

    # --------------------------------------------------------------------- #
    #  Connection management                                                #
    # --------------------------------------------------------------------- #
    async def initialize(self) -> bool:
        try:
            self._context_stack = AsyncExitStack()
            await self._context_stack.__aenter__()

            ctx = stdio_client(self.server_params)
            self.read_stream, self.write_stream = await self._context_stack.enter_async_context(
                ctx
            )

            init_result = await send_initialize(self.read_stream, self.write_stream)
            return bool(init_result)

        except Exception as e:  # pragma: no cover
            import logging

            logging.error(f"Error initializing stdio transport: {e}")
            if self._context_stack:
                try:
                    await self._context_stack.__aexit__(None, None, None)
                except Exception:
                    pass
            return False

    async def close(self) -> None:
        if self._context_stack:
            try:
                await self._context_stack.__aexit__(None, None, None)
            except Exception:
                pass
        self.read_stream = None
        self.write_stream = None
        self._context_stack = None

    # --------------------------------------------------------------------- #
    #  Utility                                                              #
    # --------------------------------------------------------------------- #
    async def send_ping(self) -> bool:
        if not self.read_stream or not self.write_stream:
            return False
        return await send_ping(self.read_stream, self.write_stream)

    async def get_tools(self) -> List[Dict[str, Any]]:
        if not self.read_stream or not self.write_stream:
            return []
        tools_response = await send_tools_list(self.read_stream, self.write_stream)
        return tools_response.get("tools", [])

    # NEW ------------------------------------------------------------------ #
    #  Resources / Prompts                                                   #
    # --------------------------------------------------------------------- #
    async def list_resources(self) -> Dict[str, Any]:
        """
        Return the result of *resources/list*.  If the connection is not yet
        initialised an empty dict is returned.
        """
        if not self.read_stream or not self.write_stream:
            return {}
        try:
            return await send_resources_list(self.read_stream, self.write_stream)
        except Exception as exc:  # pragma: no cover
            import logging

            logging.error(f"Error listing resources: {exc}")
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """
        Return the result of *prompts/list*.  If the connection is not yet
        initialised an empty dict is returned.
        """
        if not self.read_stream or not self.write_stream:
            return {}
        try:
            return await send_prompts_list(self.read_stream, self.write_stream)
        except Exception as exc:  # pragma: no cover
            import logging

            logging.error(f"Error listing prompts: {exc}")
            return {}

    # OPTIONAL helper ------------------------------------------------------ #
    def get_streams(self):
        """
        Expose the low-level streams so legacy callers can access them
        directly.  The base-class’ default returns an empty list; here we
        return a single-element list when the transport is active.
        """
        if self.read_stream and self.write_stream:
            return [(self.read_stream, self.write_stream)]
        return []

    # --------------------------------------------------------------------- #
    #  Main entry-point                                                     #
    # --------------------------------------------------------------------- #
    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute *tool_name* with *arguments* and normalise the server’s reply.

        The echo-server often returns:
        {
            "content": [{"type":"text","text":"{\"message\":\"…\"}"}],
            "isError": false
        }
        We unwrap that so callers just receive either a dict or a plain string.
        """
        if not self.read_stream or not self.write_stream:
            return {"isError": True, "error": "Transport not initialized"}

        try:
            raw = await send_tools_call(
                self.read_stream, self.write_stream, tool_name, arguments
            )

            # Handle explicit error wrapper
            if "error" in raw:
                return {
                    "isError": True,
                    "error": raw["error"].get("message", "Unknown error"),
                }

            # Preferred: servers that put the answer under "result"
            if "result" in raw:
                return {"isError": False, "content": raw["result"]}

            # Common echo-server shape: top-level "content" list
            if "content" in raw:
                clist = raw["content"]
                if isinstance(clist, list) and clist:
                    first = clist[0]
                    if isinstance(first, dict) and first.get("type") == "text":
                        text = first.get("text", "")
                        # Try to parse as JSON; fall back to plain string
                        try:
                            parsed = json.loads(text)
                            return {"isError": False, "content": parsed}
                        except json.JSONDecodeError:
                            return {"isError": False, "content": text}

            # Fallback: give caller whatever the server sent
            return {"isError": False, "content": raw}

        except Exception as e:  # pragma: no cover
            import logging

            logging.error(f"Error calling tool {tool_name}: {e}")
            return {"isError": True, "error": str(e)}
