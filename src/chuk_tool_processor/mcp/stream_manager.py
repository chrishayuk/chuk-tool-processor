# chuk_tool_processor/mcp/stream_manager.py
"""
StreamManager for CHUK Tool Processor - Updated with HTTP Streamable support
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
    HTTPStreamableTransport,
)
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_tool_processor.mcp.stream_manager")


class StreamManager:
    """
    Manager for MCP server streams with support for multiple transport types.
    
    Updated to support the latest transports:
    - STDIO (process-based)
    - SSE (Server-Sent Events) 
    - HTTP Streamable (modern replacement for SSE, spec 2025-03-26)
    """

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
        default_timeout: float = 30.0,
    ) -> "StreamManager":
        inst = cls()
        await inst.initialize(
            config_file, 
            servers, 
            server_names, 
            transport_type,
            default_timeout=default_timeout
        )
        return inst

    @classmethod
    async def create_with_sse(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 10.0,
        default_timeout: float = 30.0,
    ) -> "StreamManager":
        inst = cls()
        await inst.initialize_with_sse(
            servers, 
            server_names,
            connection_timeout=connection_timeout,
            default_timeout=default_timeout
        )
        return inst

    @classmethod
    async def create_with_http_streamable(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 30.0,
        default_timeout: float = 30.0,
    ) -> "StreamManager":
        """Create StreamManager with HTTP Streamable transport."""
        inst = cls()
        await inst.initialize_with_http_streamable(
            servers, 
            server_names,
            connection_timeout=connection_timeout,
            default_timeout=default_timeout
        )
        return inst

    # ------------------------------------------------------------------ #
    #  initialisation - stdio / sse / http_streamable                    #
    # ------------------------------------------------------------------ #
    async def initialize(
        self,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio",
        default_timeout: float = 30.0,
    ) -> None:
        async with self._lock:
            self.server_names = server_names or {}

            for idx, server_name in enumerate(servers):
                try:
                    if transport_type == "stdio":
                        params = await load_config(config_file, server_name)
                        transport: MCPBaseTransport = StdioTransport(params)
                    elif transport_type == "sse":
                        logger.warning("Using SSE transport in initialize() - consider using initialize_with_sse() instead")
                        params = await load_config(config_file, server_name)
                        
                        if isinstance(params, dict) and 'url' in params:
                            sse_url = params['url']
                            api_key = params.get('api_key')
                        else:
                            sse_url = "http://localhost:8000"
                            api_key = None
                            logger.warning(f"No URL configured for SSE transport, using default: {sse_url}")
                        
                        transport = SSETransport(
                            sse_url,
                            api_key,
                            default_timeout=default_timeout
                        )
                    elif transport_type == "http_streamable":
                        logger.warning("Using HTTP Streamable transport in initialize() - consider using initialize_with_http_streamable() instead")
                        params = await load_config(config_file, server_name)
                        
                        if isinstance(params, dict) and 'url' in params:
                            http_url = params['url']
                            api_key = params.get('api_key')
                            session_id = params.get('session_id')
                        else:
                            http_url = "http://localhost:8000"
                            api_key = None
                            session_id = None
                            logger.warning(f"No URL configured for HTTP Streamable transport, using default: {http_url}")
                        
                        transport = HTTPStreamableTransport(
                            http_url,
                            api_key,
                            default_timeout=default_timeout,
                            session_id=session_id
                        )
                    else:
                        logger.error("Unsupported transport type: %s", transport_type)
                        continue

                    if not await transport.initialize():
                        logger.error("Failed to init %s", server_name)
                        continue

                    self.transports[server_name] = transport

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
                    logger.info("Initialised %s - %d tool(s)", server_name, len(tools))
                except Exception as exc:
                    logger.error("Error initialising %s: %s", server_name, exc)

            logger.info(
                "StreamManager ready - %d server(s), %d tool(s)",
                len(self.transports),
                len(self.all_tools),
            )

    async def initialize_with_sse(
        self,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 10.0,
        default_timeout: float = 30.0,
    ) -> None:
        async with self._lock:
            self.server_names = server_names or {}

            for idx, cfg in enumerate(servers):
                name, url = cfg.get("name"), cfg.get("url")
                if not (name and url):
                    logger.error("Bad server config: %s", cfg)
                    continue
                try:
                    transport = SSETransport(
                        url, 
                        cfg.get("api_key"),
                        connection_timeout=connection_timeout,
                        default_timeout=default_timeout
                    )
                    
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
                    logger.info("Initialised SSE %s - %d tool(s)", name, len(tools))
                except Exception as exc:
                    logger.error("Error initialising SSE %s: %s", name, exc)

            logger.info(
                "StreamManager ready - %d SSE server(s), %d tool(s)",
                len(self.transports),
                len(self.all_tools),
            )

    async def initialize_with_http_streamable(
        self,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 30.0,
        default_timeout: float = 30.0,
    ) -> None:
        """Initialize with HTTP Streamable transport (modern MCP spec 2025-03-26)."""
        async with self._lock:
            self.server_names = server_names or {}

            for idx, cfg in enumerate(servers):
                name, url = cfg.get("name"), cfg.get("url")
                if not (name and url):
                    logger.error("Bad server config: %s", cfg)
                    continue
                try:
                    transport = HTTPStreamableTransport(
                        url, 
                        cfg.get("api_key"),
                        connection_timeout=connection_timeout,
                        default_timeout=default_timeout,
                        session_id=cfg.get("session_id")
                    )
                    
                    if not await transport.initialize():
                        logger.error("Failed to init HTTP Streamable %s", name)
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
                    logger.info("Initialised HTTP Streamable %s - %d tool(s)", name, len(tools))
                except Exception as exc:
                    logger.error("Error initialising HTTP Streamable %s: %s", name, exc)

            logger.info(
                "StreamManager ready - %d HTTP Streamable server(s), %d tool(s)",
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
        """List all tools available from a specific server."""
        if server_name not in self.transports:
            logger.error(f"Server '{server_name}' not found in transports")
            return []
        
        transport = self.transports[server_name]
        
        try:
            tools = await transport.get_tools()
            logger.debug(f"Found {len(tools)} tools for server {server_name}")
            return tools
        except Exception as e:
            logger.error(f"Error listing tools for server {server_name}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  EXTRA HELPERS - ping / resources / prompts                        #
    # ------------------------------------------------------------------ #
    async def ping_servers(self) -> List[Dict[str, Any]]:
        async def _ping_one(name: str, tr: MCPBaseTransport):
            try:
                ok = await tr.send_ping()
            except Exception:
                ok = False
            return {"server": name, "ok": ok}

        return await asyncio.gather(*(_ping_one(n, t) for n, t in self.transports.items()))

    async def list_resources(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []

        async def _one(name: str, tr: MCPBaseTransport):
            try:
                res = await tr.list_resources()
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
            try:
                res = await tr.list_prompts()
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
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Call a tool on the appropriate server with timeout support."""
        server_name = server_name or self.get_server_for_tool(tool_name)
        if not server_name or server_name not in self.transports:
            return {
                "isError": True,
                "error": f"No server found for tool: {tool_name}",
            }
        
        transport = self.transports[server_name]
        
        if timeout is not None:
            logger.debug("Calling tool '%s' with %ss timeout", tool_name, timeout)
            try:
                if hasattr(transport, 'call_tool'):
                    import inspect
                    sig = inspect.signature(transport.call_tool)
                    if 'timeout' in sig.parameters:
                        return await transport.call_tool(tool_name, arguments, timeout=timeout)
                    else:
                        return await asyncio.wait_for(
                            transport.call_tool(tool_name, arguments),
                            timeout=timeout
                        )
                else:
                    return await asyncio.wait_for(
                        transport.call_tool(tool_name, arguments),
                        timeout=timeout
                    )
            except asyncio.TimeoutError:
                logger.warning("Tool '%s' timed out after %ss", tool_name, timeout)
                return {
                    "isError": True,
                    "error": f"Tool call timed out after {timeout}s",
                }
        else:
            return await transport.call_tool(tool_name, arguments)
        
    # ------------------------------------------------------------------ #
    #  shutdown - FIXED VERSION to prevent cancel scope errors           #
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """Close all transports safely without cancel scope errors."""
        if not self.transports:
            logger.debug("No transports to close")
            return
        
        logger.debug(f"Closing {len(self.transports)} transports...")
        
        # Strategy: Close transports sequentially with short timeouts
        close_results = []
        transport_items = list(self.transports.items())
        
        for name, transport in transport_items:
            try:
                try:
                    await asyncio.wait_for(transport.close(), timeout=0.2)
                    logger.debug(f"Closed transport: {name}")
                    close_results.append((name, True, None))
                except asyncio.TimeoutError:
                    logger.debug(f"Transport {name} close timed out (normal during shutdown)")
                    close_results.append((name, False, "timeout"))
                except asyncio.CancelledError:
                    logger.debug(f"Transport {name} close cancelled during event loop shutdown")
                    close_results.append((name, False, "cancelled"))
                    
            except Exception as e:
                logger.debug(f"Error closing transport {name}: {e}")
                close_results.append((name, False, str(e)))
        
        # Clean up state
        self._cleanup_state()
        
        # Log summary
        successful_closes = sum(1 for _, success, _ in close_results if success)
        if close_results:
            logger.debug(f"Transport cleanup: {successful_closes}/{len(close_results)} closed successfully")

    def _cleanup_state(self) -> None:
        """Clean up internal state synchronously."""
        try:
            self.transports.clear()
            self.server_info.clear()
            self.tool_to_server_map.clear()
            self.all_tools.clear()
            self.server_names.clear()
        except Exception as e:
            logger.debug(f"Error during state cleanup: {e}")

    # ------------------------------------------------------------------ #
    #  backwards-compat: streams helper                                  #
    # ------------------------------------------------------------------ #
    def get_streams(self) -> List[Tuple[Any, Any]]:
        """Return a list of (read_stream, write_stream) tuples for all transports."""
        pairs: List[Tuple[Any, Any]] = []

        for tr in self.transports.values():
            if hasattr(tr, "get_streams") and callable(tr.get_streams):
                pairs.extend(tr.get_streams())
                continue

            rd = getattr(tr, "read_stream", None)
            wr = getattr(tr, "write_stream", None)
            if rd and wr:
                pairs.append((rd, wr))

        return pairs

    @property
    def streams(self) -> List[Tuple[Any, Any]]:
        """Convenience alias for get_streams()."""
        return self.get_streams()