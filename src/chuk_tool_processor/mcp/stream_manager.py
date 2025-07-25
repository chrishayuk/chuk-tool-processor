# chuk_tool_processor/mcp/stream_manager.py
"""
StreamManager for CHUK Tool Processor - Enhanced with robust shutdown handling
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

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
    
    Enhanced with robust shutdown handling to prevent event loop closure issues.
    
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
        self._closed = False  # Track if we've been closed
        self._shutdown_timeout = 2.0  # Maximum time to spend on shutdown

    # ------------------------------------------------------------------ #
    #  factory helpers with enhanced error handling                      #
    # ------------------------------------------------------------------ #
    @classmethod
    async def create(
        cls,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio",
        default_timeout: float = 30.0,
        initialization_timeout: float = 60.0,  # NEW: Timeout for entire initialization
    ) -> "StreamManager":
        """Create StreamManager with timeout protection."""
        try:
            inst = cls()
            await asyncio.wait_for(
                inst.initialize(
                    config_file, 
                    servers, 
                    server_names, 
                    transport_type,
                    default_timeout=default_timeout
                ),
                timeout=initialization_timeout
            )
            return inst
        except asyncio.TimeoutError:
            logger.error(f"StreamManager initialization timed out after {initialization_timeout}s")
            raise RuntimeError(f"StreamManager initialization timed out after {initialization_timeout}s")

    @classmethod
    async def create_with_sse(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 10.0,
        default_timeout: float = 30.0,
        initialization_timeout: float = 60.0,  # NEW
    ) -> "StreamManager":
        """Create StreamManager with SSE transport and timeout protection."""
        try:
            inst = cls()
            await asyncio.wait_for(
                inst.initialize_with_sse(
                    servers, 
                    server_names,
                    connection_timeout=connection_timeout,
                    default_timeout=default_timeout
                ),
                timeout=initialization_timeout
            )
            return inst
        except asyncio.TimeoutError:
            logger.error(f"SSE StreamManager initialization timed out after {initialization_timeout}s")
            raise RuntimeError(f"SSE StreamManager initialization timed out after {initialization_timeout}s")

    @classmethod
    async def create_with_http_streamable(
        cls,
        servers: List[Dict[str, str]],
        server_names: Optional[Dict[int, str]] = None,
        connection_timeout: float = 30.0,
        default_timeout: float = 30.0,
        initialization_timeout: float = 60.0,  # NEW
    ) -> "StreamManager":
        """Create StreamManager with HTTP Streamable transport and timeout protection."""
        try:
            inst = cls()
            await asyncio.wait_for(
                inst.initialize_with_http_streamable(
                    servers, 
                    server_names,
                    connection_timeout=connection_timeout,
                    default_timeout=default_timeout
                ),
                timeout=initialization_timeout
            )
            return inst
        except asyncio.TimeoutError:
            logger.error(f"HTTP Streamable StreamManager initialization timed out after {initialization_timeout}s")
            raise RuntimeError(f"HTTP Streamable StreamManager initialization timed out after {initialization_timeout}s")

    # ------------------------------------------------------------------ #
    #  NEW: Context manager support for automatic cleanup               #
    # ------------------------------------------------------------------ #
    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        await self.close()

    @classmethod
    @asynccontextmanager
    async def create_managed(
        cls,
        config_file: str,
        servers: List[str],
        server_names: Optional[Dict[int, str]] = None,
        transport_type: str = "stdio",
        default_timeout: float = 30.0,
    ):
        """Context manager factory for automatic cleanup."""
        stream_manager = None
        try:
            stream_manager = await cls.create(
                config_file=config_file,
                servers=servers,
                server_names=server_names,
                transport_type=transport_type,
                default_timeout=default_timeout,
            )
            yield stream_manager
        finally:
            if stream_manager:
                await stream_manager.close()

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
        if self._closed:
            raise RuntimeError("Cannot initialize a closed StreamManager")
            
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

                    # Initialize with timeout protection
                    if not await asyncio.wait_for(transport.initialize(), timeout=default_timeout):
                        logger.error("Failed to init %s", server_name)
                        continue

                    self.transports[server_name] = transport

                    # Ping and get tools with timeout protection
                    status = "Up" if await asyncio.wait_for(transport.send_ping(), timeout=5.0) else "Down"
                    tools = await asyncio.wait_for(transport.get_tools(), timeout=10.0)

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
                except asyncio.TimeoutError:
                    logger.error("Timeout initialising %s", server_name)
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
        if self._closed:
            raise RuntimeError("Cannot initialize a closed StreamManager")
            
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
                    
                    if not await asyncio.wait_for(transport.initialize(), timeout=connection_timeout):
                        logger.error("Failed to init SSE %s", name)
                        continue

                    self.transports[name] = transport
                    status = "Up" if await asyncio.wait_for(transport.send_ping(), timeout=5.0) else "Down"
                    tools = await asyncio.wait_for(transport.get_tools(), timeout=10.0)

                    for t in tools:
                        tname = t.get("name")
                        if tname:
                            self.tool_to_server_map[tname] = name
                    self.all_tools.extend(tools)

                    self.server_info.append(
                        {"id": idx, "name": name, "tools": len(tools), "status": status}
                    )
                    logger.info("Initialised SSE %s - %d tool(s)", name, len(tools))
                except asyncio.TimeoutError:
                    logger.error("Timeout initialising SSE %s", name)
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
        if self._closed:
            raise RuntimeError("Cannot initialize a closed StreamManager")
            
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
                    
                    if not await asyncio.wait_for(transport.initialize(), timeout=connection_timeout):
                        logger.error("Failed to init HTTP Streamable %s", name)
                        continue

                    self.transports[name] = transport
                    status = "Up" if await asyncio.wait_for(transport.send_ping(), timeout=5.0) else "Down"
                    tools = await asyncio.wait_for(transport.get_tools(), timeout=10.0)

                    for t in tools:
                        tname = t.get("name")
                        if tname:
                            self.tool_to_server_map[tname] = name
                    self.all_tools.extend(tools)

                    self.server_info.append(
                        {"id": idx, "name": name, "tools": len(tools), "status": status}
                    )
                    logger.info("Initialised HTTP Streamable %s - %d tool(s)", name, len(tools))
                except asyncio.TimeoutError:
                    logger.error("Timeout initialising HTTP Streamable %s", name)
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
        if self._closed:
            logger.warning("Cannot list tools: StreamManager is closed")
            return []
            
        if server_name not in self.transports:
            logger.error(f"Server '{server_name}' not found in transports")
            return []
        
        transport = self.transports[server_name]
        
        try:
            tools = await asyncio.wait_for(transport.get_tools(), timeout=10.0)
            logger.debug(f"Found {len(tools)} tools for server {server_name}")
            return tools
        except asyncio.TimeoutError:
            logger.error(f"Timeout listing tools for server {server_name}")
            return []
        except Exception as e:
            logger.error(f"Error listing tools for server {server_name}: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  EXTRA HELPERS - ping / resources / prompts                        #
    # ------------------------------------------------------------------ #
    async def ping_servers(self) -> List[Dict[str, Any]]:
        if self._closed:
            return []
            
        async def _ping_one(name: str, tr: MCPBaseTransport):
            try:
                ok = await asyncio.wait_for(tr.send_ping(), timeout=5.0)
            except Exception:
                ok = False
            return {"server": name, "ok": ok}

        return await asyncio.gather(*(_ping_one(n, t) for n, t in self.transports.items()), return_exceptions=True)

    async def list_resources(self) -> List[Dict[str, Any]]:
        if self._closed:
            return []
            
        out: List[Dict[str, Any]] = []

        async def _one(name: str, tr: MCPBaseTransport):
            try:
                res = await asyncio.wait_for(tr.list_resources(), timeout=10.0)
                resources = (
                    res.get("resources", []) if isinstance(res, dict) else res
                )
                for item in resources:
                    item = dict(item)
                    item["server"] = name
                    out.append(item)
            except Exception as exc:
                logger.debug("resources/list failed for %s: %s", name, exc)

        await asyncio.gather(*(_one(n, t) for n, t in self.transports.items()), return_exceptions=True)
        return out

    async def list_prompts(self) -> List[Dict[str, Any]]:
        if self._closed:
            return []
            
        out: List[Dict[str, Any]] = []

        async def _one(name: str, tr: MCPBaseTransport):
            try:
                res = await asyncio.wait_for(tr.list_prompts(), timeout=10.0)
                prompts = res.get("prompts", []) if isinstance(res, dict) else res
                for item in prompts:
                    item = dict(item)
                    item["server"] = name
                    out.append(item)
            except Exception as exc:
                logger.debug("prompts/list failed for %s: %s", name, exc)

        await asyncio.gather(*(_one(n, t) for n, t in self.transports.items()), return_exceptions=True)
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
        if self._closed:
            return {
                "isError": True,
                "error": "StreamManager is closed",
            }
            
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
    #  ENHANCED shutdown with robust error handling                      #
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """
        Close all transports safely with enhanced error handling.
        
        ENHANCED: Uses asyncio.shield() to protect critical cleanup and
        provides multiple fallback strategies for different failure modes.
        """
        if self._closed:
            logger.debug("StreamManager already closed")
            return
            
        if not self.transports:
            logger.debug("No transports to close")
            self._closed = True
            return
        
        logger.debug(f"Closing {len(self.transports)} transports...")
        
        try:
            # Use shield to protect the cleanup operation from cancellation
            await asyncio.shield(self._do_close_all_transports())
        except asyncio.CancelledError:
            # If shield fails (rare), fall back to synchronous cleanup
            logger.debug("Close operation cancelled, performing synchronous cleanup")
            self._sync_cleanup()
        except Exception as e:
            logger.debug(f"Error during close: {e}")
            self._sync_cleanup()
        finally:
            self._closed = True

    async def _do_close_all_transports(self) -> None:
        """Protected cleanup implementation with multiple strategies."""
        close_results = []
        transport_items = list(self.transports.items())
        
        # Strategy 1: Try concurrent close with timeout
        try:
            await self._concurrent_close(transport_items, close_results)
        except Exception as e:
            logger.debug(f"Concurrent close failed: {e}, falling back to sequential close")
            # Strategy 2: Fall back to sequential close
            await self._sequential_close(transport_items, close_results)
        
        # Always clean up state
        self._cleanup_state()
        
        # Log summary
        if close_results:
            successful_closes = sum(1 for _, success, _ in close_results if success)
            logger.debug(f"Transport cleanup: {successful_closes}/{len(close_results)} closed successfully")

    async def _concurrent_close(self, transport_items: List[Tuple[str, MCPBaseTransport]], close_results: List) -> None:
        """Try to close all transports concurrently."""
        close_tasks = []
        for name, transport in transport_items:
            task = asyncio.create_task(
                self._close_single_transport(name, transport),
                name=f"close_{name}"
            )
            close_tasks.append((name, task))
        
        # Wait for all tasks with a reasonable timeout
        if close_tasks:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *[task for _, task in close_tasks],
                        return_exceptions=True
                    ),
                    timeout=self._shutdown_timeout
                )
                
                # Process results
                for i, (name, _) in enumerate(close_tasks):
                    result = results[i] if i < len(results) else None
                    if isinstance(result, Exception):
                        logger.debug(f"Transport {name} close failed: {result}")
                        close_results.append((name, False, str(result)))
                    else:
                        logger.debug(f"Transport {name} closed successfully")
                        close_results.append((name, True, None))
                        
            except asyncio.TimeoutError:
                # Cancel any remaining tasks
                for name, task in close_tasks:
                    if not task.done():
                        task.cancel()
                        close_results.append((name, False, "timeout"))
                
                # Brief wait for cancellations to complete
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*[task for _, task in close_tasks], return_exceptions=True),
                        timeout=0.5
                    )
                except asyncio.TimeoutError:
                    pass  # Some tasks may not cancel cleanly

    async def _sequential_close(self, transport_items: List[Tuple[str, MCPBaseTransport]], close_results: List) -> None:
        """Close transports one by one as fallback."""
        for name, transport in transport_items:
            try:
                await asyncio.wait_for(
                    self._close_single_transport(name, transport),
                    timeout=0.5  # Short timeout per transport
                )
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

    async def _close_single_transport(self, name: str, transport: MCPBaseTransport) -> None:
        """Close a single transport with error handling."""
        try:
            if hasattr(transport, 'close') and callable(transport.close):
                await transport.close()
            else:
                logger.debug(f"Transport {name} has no close method")
        except Exception as e:
            logger.debug(f"Error closing transport {name}: {e}")
            raise

    def _sync_cleanup(self) -> None:
        """Synchronous cleanup for use when async cleanup fails."""
        try:
            transport_count = len(self.transports)
            self._cleanup_state()
            logger.debug(f"Synchronous cleanup completed for {transport_count} transports")
        except Exception as e:
            logger.debug(f"Error during synchronous cleanup: {e}")

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
        if self._closed:
            return []
            
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

    # ------------------------------------------------------------------ #
    #  NEW: Health check and diagnostic methods                          #
    # ------------------------------------------------------------------ #
    def is_closed(self) -> bool:
        """Check if the StreamManager has been closed."""
        return self._closed

    def get_transport_count(self) -> int:
        """Get the number of active transports."""
        return len(self.transports)

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on all transports."""
        if self._closed:
            return {"status": "closed", "transports": {}}
        
        health_info = {
            "status": "active",
            "transport_count": len(self.transports),
            "transports": {}
        }
        
        for name, transport in self.transports.items():
            try:
                ping_ok = await asyncio.wait_for(transport.send_ping(), timeout=5.0)
                health_info["transports"][name] = {
                    "status": "healthy" if ping_ok else "unhealthy",
                    "ping_success": ping_ok
                }
            except asyncio.TimeoutError:
                health_info["transports"][name] = {
                    "status": "timeout",
                    "ping_success": False
                }
            except Exception as e:
                health_info["transports"][name] = {
                    "status": "error",
                    "ping_success": False,
                    "error": str(e)
                }
        
        return health_info