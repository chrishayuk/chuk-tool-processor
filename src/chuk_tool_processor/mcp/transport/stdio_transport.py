# chuk_tool_processor/mcp/transport/stdio_transport.py
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import logging

from .base_transport import MCPBaseTransport
from chuk_mcp.transports.stdio import stdio_client
from chuk_mcp.transports.stdio.parameters import StdioParameters
from chuk_mcp.protocol.messages import (
    send_initialize, send_ping, send_tools_list, send_tools_call,
    send_resources_list, send_resources_read,
    send_prompts_list, send_prompts_get,
)

logger = logging.getLogger(__name__)


class StdioTransport(MCPBaseTransport):
    """
    STDIO transport for MCP communication using process pipes.
    
    This transport uses subprocess communication via stdin/stdout pipes
    to communicate with MCP servers.
    """

    def __init__(self, server_params, 
                 connection_timeout: float = 30.0,
                 default_timeout: float = 30.0,
                 enable_metrics: bool = True):
        """
        Initialize STDIO transport.
        
        Args:
            server_params: Server parameters (dict or StdioParameters object)
            connection_timeout: Timeout for initial connection setup
            default_timeout: Default timeout for operations
            enable_metrics: Whether to track performance metrics
        """
        # Convert dict to StdioParameters if needed
        if isinstance(server_params, dict):
            self.server_params = StdioParameters(
                command=server_params.get('command', 'python'),
                args=server_params.get('args', []),
                env=server_params.get('env')
            )
        else:
            self.server_params = server_params
        
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        self.enable_metrics = enable_metrics
        
        # Connection state
        self._context = None
        self._streams = None
        self._initialized = False
        
        # Performance metrics (consistent with other transports)
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None,
            "process_restarts": 0,
            "pipe_errors": 0
        }
        
        logger.debug("STDIO transport initialized for command: %s", 
                    getattr(self.server_params, 'command', 'unknown'))

    async def initialize(self) -> bool:
        """Initialize by delegating to chuk-mcp with timeout protection."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        start_time = time.time()
        
        try:
            logger.debug("Initializing STDIO transport...")
            
            # Create context with timeout protection
            self._context = stdio_client(self.server_params)
            self._streams = await asyncio.wait_for(
                self._context.__aenter__(),
                timeout=self.connection_timeout
            )
            
            # Send initialize message with timeout
            init_result = await asyncio.wait_for(
                send_initialize(*self._streams),
                timeout=self.default_timeout
            )
            
            if init_result:
                self._initialized = True
                
                if self.enable_metrics:
                    init_time = time.time() - start_time
                    self._metrics["initialization_time"] = init_time
                
                logger.debug("STDIO transport initialized successfully in %.3fs", time.time() - start_time)
                return True
            else:
                logger.error("STDIO initialization failed")
                await self._cleanup()
                return False
                
        except asyncio.TimeoutError:
            logger.error("STDIO initialization timed out after %ss", self.connection_timeout)
            await self._cleanup()
            return False
        except Exception as e:
            logger.error("Error initializing STDIO transport: %s", e)
            await self._cleanup()
            return False

    async def close(self) -> None:
        """Close by delegating to chuk-mcp context manager with enhanced cleanup."""
        if not self._initialized:
            return
        
        # Log final metrics
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            logger.debug(
                "STDIO transport closing - Total calls: %d, Success rate: %.1f%%, Avg response time: %.3fs",
                self._metrics["total_calls"],
                (self._metrics["successful_calls"] / self._metrics["total_calls"] * 100),
                self._metrics["avg_response_time"]
            )
        
        if self._context:
            try:
                await self._context.__aexit__(None, None, None)
                logger.debug("STDIO context closed")
            except Exception as e:
                logger.debug("Error during STDIO close: %s", e)
            finally:
                await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up internal state."""
        self._context = None
        self._streams = None
        self._initialized = False

    async def send_ping(self) -> bool:
        """Send ping with performance tracking."""
        if not self._initialized:
            return False
        
        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                send_ping(*self._streams),
                timeout=self.default_timeout
            )
            
            if self.enable_metrics:
                ping_time = time.time() - start_time
                self._metrics["last_ping_time"] = ping_time
                logger.debug("STDIO ping completed in %.3fs: %s", ping_time, result)
            
            return bool(result)
        except asyncio.TimeoutError:
            logger.error("STDIO ping timed out")
            return False
        except Exception as e:
            logger.error("STDIO ping failed: %s", e)
            if self.enable_metrics:
                self._metrics["pipe_errors"] += 1
            return False

    def is_connected(self) -> bool:
        """Check connection status."""
        return self._initialized and self._streams is not None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools list with performance tracking."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
        start_time = time.time()
        try:
            response = await asyncio.wait_for(
                send_tools_list(*self._streams),
                timeout=self.default_timeout
            )
            
            # Normalize response
            if isinstance(response, dict):
                tools = response.get("tools", [])
            elif isinstance(response, list):
                tools = response
            else:
                logger.warning("Unexpected tools response type: %s", type(response))
                tools = []
            
            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug("Retrieved %d tools in %.3fs", len(tools), response_time)
            
            return tools
            
        except asyncio.TimeoutError:
            logger.error("Get tools timed out")
            return []
        except Exception as e:
            logger.error("Error getting tools: %s", e)
            if self.enable_metrics:
                self._metrics["pipe_errors"] += 1
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], 
                       timeout: Optional[float] = None) -> Dict[str, Any]:
        """Call tool with timeout support and performance tracking."""
        if not self._initialized:
            return {"isError": True, "error": "Transport not initialized"}

        tool_timeout = timeout or self.default_timeout
        start_time = time.time()
        
        if self.enable_metrics:
            self._metrics["total_calls"] += 1  # FIXED: INCREMENT FIRST

        try:
            logger.debug("Calling tool '%s' with timeout %ss", tool_name, tool_timeout)
            
            response = await asyncio.wait_for(
                send_tools_call(*self._streams, tool_name, arguments),
                timeout=tool_timeout
            )
            
            response_time = time.time() - start_time
            result = self._normalize_mcp_response(response)
            
            if self.enable_metrics:
                self._update_metrics(response_time, not result.get("isError", False))
            
            if not result.get("isError", False):
                logger.debug("Tool '%s' completed successfully in %.3fs", tool_name, response_time)
            else:
                logger.warning("Tool '%s' failed in %.3fs: %s", tool_name, response_time, result.get('error', 'Unknown error'))
            
            return result
            
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
            
            error_msg = f"Tool execution timed out after {tool_timeout}s"
            logger.error("Tool '%s' %s", tool_name, error_msg)
            return {
                "isError": True,
                "error": error_msg
            }
        except Exception as e:
            response_time = time.time() - start_time
            if self.enable_metrics:
                self._update_metrics(response_time, False)
                self._metrics["pipe_errors"] += 1
            
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error("Tool '%s' error: %s", tool_name, error_msg)
            return {
                "isError": True,
                "error": error_msg
            }

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update performance metrics."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1
            
        self._metrics["total_time"] += response_time
        # FIXED: Only calculate average if we have total calls
        if self._metrics["total_calls"] > 0:
            self._metrics["avg_response_time"] = (
                self._metrics["total_time"] / self._metrics["total_calls"]
            )

    def _normalize_mcp_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize response using shared base class logic with STDIO-specific handling.
        
        STDIO has special requirements for preserving string representations
        of numeric values for backward compatibility.
        """
        # Handle explicit error in response
        if "error" in response:
            error_info = response["error"]
            error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
            return {"isError": True, "error": error_msg}
        
        # Handle successful response with result
        if "result" in response:
            result = response["result"]
            if isinstance(result, dict) and "content" in result:
                return {"isError": False, "content": self._extract_stdio_content(result["content"])}
            return {"isError": False, "content": result}
        
        # Handle direct content-based response
        if "content" in response:
            return {"isError": False, "content": self._extract_stdio_content(response["content"])}
        
        return {"isError": False, "content": response}

    def _extract_stdio_content(self, content_list: Any) -> Any:
        """
        Extract content with STDIO-specific string preservation logic.
        
        STDIO transport preserves string representations of numeric values
        for backward compatibility with existing tests.
        """
        if not isinstance(content_list, list) or not content_list:
            return content_list
        
        if len(content_list) == 1:
            item = content_list[0]
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                
                # STDIO-specific: preserve string format for numeric values
                try:
                    parsed = json.loads(text)
                    # If the parsed result is a simple type and the original was a string,
                    # keep it as a string to maintain compatibility
                    if isinstance(parsed, (int, float, bool)) and isinstance(text, str):
                        # Check if this looks like a simple numeric string
                        if text.strip().isdigit() or (text.strip().replace('.', '', 1).isdigit()):
                            return text  # Return as string for numeric values
                    return parsed
                except json.JSONDecodeError:
                    return text
            return item
        
        return content_list

    async def list_resources(self) -> Dict[str, Any]:
        """List resources with error handling."""
        if not self._initialized:
            return {}
        try:
            response = await asyncio.wait_for(
                send_resources_list(*self._streams),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            logger.error("List resources timed out")
            return {}
        except Exception as e:
            logger.debug("Error listing resources: %s", e)
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """List prompts with error handling."""
        if not self._initialized:
            return {}
        try:
            response = await asyncio.wait_for(
                send_prompts_list(*self._streams),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except asyncio.TimeoutError:
            logger.error("List prompts timed out")
            return {}
        except Exception as e:
            logger.debug("Error listing prompts: %s", e)
            return {}

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific resource."""
        if not self._initialized:
            return {}
        try:
            response = await asyncio.wait_for(
                send_resources_read(*self._streams, uri),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.debug("Error reading resource: %s", e)
            return {}

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a specific prompt."""
        if not self._initialized:
            return {}
        try:
            response = await asyncio.wait_for(
                send_prompts_get(*self._streams, name, arguments or {}),
                timeout=self.default_timeout
            )
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.debug("Error getting prompt: %s", e)
            return {}

    # ------------------------------------------------------------------ #
    #  Metrics and monitoring (now consistent with other transports)    #
    # ------------------------------------------------------------------ #
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance and connection metrics."""
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": self._metrics.get("last_ping_time"),
            "initialization_time": self._metrics.get("initialization_time"),
            "process_restarts": self._metrics.get("process_restarts", 0),
            "pipe_errors": 0
        }

    # ------------------------------------------------------------------ #
    #  Backward compatibility                                            #
    # ------------------------------------------------------------------ #
    def get_streams(self) -> List[tuple]:
        """Provide streams for backward compatibility."""
        return [self._streams] if self._streams else []

    # ------------------------------------------------------------------ #
    #  Context manager support (now uses base class with fixed error)   #
    # ------------------------------------------------------------------ #
    async def __aenter__(self):
        """Context manager support."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize StdioTransport")  # FIXED: message
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()