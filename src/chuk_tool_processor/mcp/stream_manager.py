# chuk_tool_processor/mcp/stream_manager.py
"""
StreamManager for CHUK Tool Processor.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
#  CHUK imports                                                               #
# --------------------------------------------------------------------------- #
from chuk_mcp.config import load_config
from chuk_tool_processor.mcp.transport import (
    MCPBaseTransport,
    StdioTransport,
    SSETransport,
)
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.mcp.stream_manager")


class StreamManager:
    """
    Manager for MCP server streams with support for multiple transport types.
    """

    # ------------------------------------------------------------------ #
    #  construction                                                      #
    # ------------------------------------------------------------------ #
    def __init__(self) -> None:
        self.transports: Dict[str, MCPBaseTransport] = {}
        self.server_info: List[Dict[str, Any]] = []
        self.tool_to_server_map: Dict[str, str] = {}
        self.server_names: Dict[int, str] = {}
        self.all_tools: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    #  factory helpers                                                   #
    # ------------------------------------------------------------------ #
    @classmethod
    async def create(
        cls,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio",
    ) -> "StreamManager":
        inst = cls()
        await inst.initialize(config_file, servers, server_names, transport_type)
        return inst

    @classmethod
    async def create_with_sse(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
    ) -> "StreamManager":
        inst = cls()
        await inst.initialize_with_sse(servers, server_names)
        return inst

    # ------------------------------------------------------------------ #
    #  initialisation – stdio / sse                                      #
    # ------------------------------------------------------------------ #
    async def initialize(
        self,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio",
    ) -> None:
        async with self._lock:
            self.server_names = server_names or {}

            for idx, server_name in enumerate(servers):
                try:
                    if transport_type == "stdio":
                        params = await load_config(config_file, server_name)
                        transport: MCPBaseTransport = StdioTransport(params)
                    elif transport_type == "sse":
                        transport = SSETransport("http://localhost:8000")
                    else:
                        logger.error("Unsupported transport type: %s", transport_type)
                        continue

                    if not await transport.initialize():
                        logger.error("Failed to init %s", server_name)
                        continue

                    #  store transport
                    self.transports[server_name] = transport

                    #  ping + gather tools
                    status = "Up" if await transport.send_ping() else "Down"
                    tools = await transport.get_tools()

                    for t in tools:
                        name = t.get("name")
                        if name:
                            self.tool_to_server_map[name] = server_name
                    self.all_tools.extend(tools)

                    self.server_info.append(
                        {
                            "id": idx,
                            "name": server_name,
                            "tools": len(tools),
                            "status": status,
                        }
                    )
                    logger.info("Initialised %s – %d tool(s)", server_name, len(tools))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error initialising %s: %s", server_name, exc)

            logger.info(
                "StreamManager ready – %d server(s), %d tool(s)",
                len(self.transports),
                len(self.all_tools),
            )

    async def initialize_with_sse(
        self,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
    ) -> None:
        async with self._lock:
            self.server_names = server_names or {}

            for idx, cfg in enumerate(servers):
                name, url = cfg.get("name"), cfg.get("url")
                if not (name and url):
                    logger.error("Bad server config: %s", cfg)
                    continue
                try:
                    transport = SSETransport(url, cfg.get("api_key"))
                    if not await transport.initialize():
                        logger.error("Failed to init SSE %s", name)
                        continue

                    self.transports[name] = transport
                    status = "Up" if await transport.send_ping() else "Down"
                    tools = await transport.get_tools()

                    for t in tools:
                        tname = t.get("name")
                        if tname:
                            self.tool_to_server_map[tname] = name
                    self.all_tools.extend(tools)

                    self.server_info.append(
                        {"id": idx, "name": name, "tools": len(tools), "status": status}
                    )
                    logger.info("Initialised SSE %s – %d tool(s)", name, len(tools))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error initialising SSE %s: %s", name, exc)

            logger.info(
                "StreamManager ready – %d SSE server(s), %d tool(s)",
                len(self.transports),
                len(self.all_tools),
            )

    # ------------------------------------------------------------------ #
    #  queries                                                           #
    # ------------------------------------------------------------------ #
    def get_all_tools(self) -> List[Dict[str, Any]]:
        return self.all_tools

    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        return self.tool_to_server_map.get(tool_name)

    def get_server_info(self) -> List[Dict[str, Any]]:
        return self.server_info
    
    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """
        List all tools available from a specific server.
        
        This method is required by ProxyServerManager for proper tool discovery.
        
        Args:
            server_name: Name of the server to query
            
        Returns:
            List of tool definitions from the server
        """
        if server_name not in self.transports:
            logger.error(f"Server '{server_name}' not found in transports")
            return []
        
        # Get the transport for this server
        transport = self.transports[server_name]
        
        try:
            # Call the get_tools method on the transport
            tools = await transport.get_tools()
            logger.debug(f"Found {len(tools)} tools for server {server_name}")
            return tools
        except Exception as e:
            logger.error(f"Error listing tools for server {server_name}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  EXTRA HELPERS – ping / resources / prompts                        #
    # ------------------------------------------------------------------ #
    async def ping_servers(self) -> List[Dict[str, Any]]:
        async def _ping_one(name: str, tr: MCPBaseTransport):
            try:
                ok = await tr.send_ping()
            except Exception:  # pragma: no cover
                ok = False
            return {"server": name, "ok": ok}

        return await asyncio.gather(*(_ping_one(n, t) for n, t in self.transports.items()))

    async def list_resources(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        async def _one(name: str, tr: MCPBaseTransport):
            if not hasattr(tr, "list_resources"):
                return
            try:
                res = await tr.list_resources()  # type: ignore[attr-defined]
                # accept either {"resources": [...]} **or** a plain list
                resources = (
                    res.get("resources", []) if isinstance(res, dict) else res
                )
                for item in resources:
                    item = dict(item)
                    item["server"] = name
                    out.append(item)
            except Exception as exc:
                logger.debug("resources/list failed for %s: %s", name, exc)

        await asyncio.gather(*(_one(n, t) for n, t in self.transports.items()))
        return out

    async def list_prompts(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        async def _one(name: str, tr: MCPBaseTransport):
            if not hasattr(tr, "list_prompts"):
                return
            try:
                res = await tr.list_prompts()  # type: ignore[attr-defined]
                prompts = res.get("prompts", []) if isinstance(res, dict) else res
                for item in prompts:
                    item = dict(item)
                    item["server"] = name
                    out.append(item)
            except Exception as exc:
                logger.debug("prompts/list failed for %s: %s", name, exc)

        await asyncio.gather(*(_one(n, t) for n, t in self.transports.items()))
        return out

    # ------------------------------------------------------------------ #
    #  tool execution                                                    #
    # ------------------------------------------------------------------ #
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        server_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        server_name = server_name or self.get_server_for_tool(tool_name)
        if not server_name or server_name not in self.transports:
            # wording kept exactly for unit-test expectation
            return {
                "isError": True,
                "error": f"No server found for tool: {tool_name}",
            }
        return await self.transports[server_name].call_tool(tool_name, arguments)

    # ------------------------------------------------------------------ #
    #  shutdown                                                          #
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        tasks = [tr.close() for tr in self.transports.values()]
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:  # pragma: no cover
                pass
            except Exception as exc:  # noqa: BLE001
                logger.error("Error during close: %s", exc)

        self.transports.clear()
        self.server_info.clear()
        self.tool_to_server_map.clear()
        self.all_tools.clear()

    # ------------------------------------------------------------------ #
    #  backwards-compat: streams helper                                  #
    # ------------------------------------------------------------------ #
    def get_streams(self) -> List[Tuple[Any, Any]]:
        """
        Return a list of ``(read_stream, write_stream)`` tuples for **all**
        transports.  Older CLI commands rely on this helper.
        """
        pairs: List[Tuple[Any, Any]] = []

        for tr in self.transports.values():
            if hasattr(tr, "get_streams") and callable(tr.get_streams):
                pairs.extend(tr.get_streams())  # type: ignore[arg-type]
                continue

            rd = getattr(tr, "read_stream", None)
            wr = getattr(tr, "write_stream", None)
            if rd and wr:
                pairs.append((rd, wr))

        return pairs

    # convenience alias
    @property
    def streams(self) -> List[Tuple[Any, Any]]:  # pragma: no cover
        return self.get_streams()
