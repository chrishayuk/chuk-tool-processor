# chuk_tool_processor/mcp/transport/sse_transport.py
"""
SSE transport for MCP communication.

Implements Server-Sent Events transport with two-step async pattern:
1. POST messages to /messages endpoint
2. Receive responses via SSE stream

Note: This transport is deprecated in favor of HTTP Streamable (spec 2025-03-26)
but remains supported for backward compatibility.

FIXED: Updated to support both old format (/messages/) and new event-based format
(event: endpoint + data: https://...) for session discovery.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional
import logging

import httpx

from .base_transport import MCPBaseTransport

logger = logging.getLogger(__name__)


class SSETransport(MCPBaseTransport):
    """
    SSE transport implementing the MCP protocol over Server-Sent Events.
    
    This transport uses a dual-connection approach:
    - SSE stream for receiving responses
    - HTTP POST for sending requests
    
    FIXED: Supports both old and new session discovery formats.
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 headers: Optional[Dict[str, str]] = None,
                 connection_timeout: float = 30.0, 
                 default_timeout: float = 30.0,
                 enable_metrics: bool = True):
        """
        Initialize SSE transport.
        
        Args:
            url: Base URL for the MCP server
            api_key: Optional API key for authentication
            headers: Optional custom headers
            connection_timeout: Timeout for initial connection setup
            default_timeout: Default timeout for operations
            enable_metrics: Whether to track performance metrics
        """
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.configured_headers = headers or {}
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        self.enable_metrics = enable_metrics
        
        logger.debug("SSE Transport initialized with URL: %s", self.url)
        if self.api_key:
            logger.debug("API key configured for authentication")
        if self.configured_headers:
            logger.debug("Custom headers configured: %s", list(self.configured_headers.keys()))
        
        # Connection state
        self.session_id = None
        self.message_url = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self._initialized = False
        
        # HTTP clients
        self.stream_client = None
        self.send_client = None
        
        # SSE stream management
        self.sse_task = None
        self.sse_response = None
        self.sse_stream_context = None
        
        # Performance metrics (consistent with other transports)
        self._metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time": 0.0,
            "avg_response_time": 0.0,
            "last_ping_time": None,
            "initialization_time": None,
            "session_discoveries": 0,
            "stream_errors": 0
        }

    def _construct_sse_url(self, base_url: str) -> str:
        """
        Construct the SSE endpoint URL from the base URL.
        
        Smart detection to avoid double-appending /sse if already present.
        """
        base_url = base_url.rstrip('/')
        
        if base_url.endswith('/sse'):
            logger.debug("URL already contains /sse endpoint: %s", base_url)
            return base_url
        
        sse_url = f"{base_url}/sse"
        logger.debug("Constructed SSE URL: %s -> %s", base_url, sse_url)
        return sse_url

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication and custom headers."""
        headers = {}
        
        # Add configured headers first
        if self.configured_headers:
            headers.update(self.configured_headers)
        
        # Add API key as Bearer token if provided (overrides Authorization header)
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        return headers

    async def initialize(self) -> bool:
        """Initialize SSE connection and perform MCP handshake."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        start_time = time.time()
        
        try:
            logger.debug("Initializing SSE transport...")
            
            # Create HTTP clients with appropriate timeouts
            self.stream_client = httpx.AsyncClient(timeout=self.connection_timeout)
            self.send_client = httpx.AsyncClient(timeout=self.default_timeout)
            
            # Connect to SSE stream
            sse_url = self._construct_sse_url(self.url)
            logger.debug("Connecting to SSE endpoint: %s", sse_url)
            
            self.sse_stream_context = self.stream_client.stream(
                'GET', sse_url, headers=self._get_headers()
            )
            self.sse_response = await self.sse_stream_context.__aenter__()
            
            if self.sse_response.status_code != 200:
                logger.error("SSE connection failed with status: %s", self.sse_response.status_code)
                await self._cleanup()
                return False
            
            logger.debug("SSE streaming connection established")
            
            # Start SSE processing task
            self.sse_task = asyncio.create_task(
                self._process_sse_stream(), 
                name="sse_stream_processor"
            )
            
            # Wait for session discovery with timeout
            logger.debug("Waiting for session discovery...")
            session_timeout = 5.0  # 5 seconds max for session discovery
            session_start = time.time()
            
            while not self.message_url and (time.time() - session_start) < session_timeout:
                await asyncio.sleep(0.1)
            
            if not self.message_url:
                logger.error("Failed to discover session endpoint within %.1fs", session_timeout)
                await self._cleanup()
                return False
            
            if self.enable_metrics:
                self._metrics["session_discoveries"] += 1
            
            logger.debug("Session endpoint discovered: %s", self.session_id)
            
            # Perform MCP initialization handshake
            try:
                init_response = await self._send_request("initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "chuk-tool-processor",
                        "version": "1.0.0"
                    }
                })
                
                if 'error' in init_response:
                    logger.error("MCP initialize failed: %s", init_response['error'])
                    await self._cleanup()
                    return False
                
                # Send initialized notification
                await self._send_notification("notifications/initialized")
                
                self._initialized = True
                
                if self.enable_metrics:
                    init_time = time.time() - start_time
                    self._metrics["initialization_time"] = init_time
                
                logger.debug("SSE transport initialized successfully in %.3fs", time.time() - start_time)
                return True
                
            except Exception as e:
                logger.error("MCP handshake failed: %s", e)
                await self._cleanup()
                return False
                
        except Exception as e:
            logger.error("Error initializing SSE transport: %s", e, exc_info=True)
            await self._cleanup()
            return False

    async def _process_sse_stream(self):
        """
        Process the persistent SSE stream for responses and session discovery.
        
        FIXED: Supports both old format (/messages/) and new event-based format
        (event: endpoint + data: https://...) for session discovery.
        """
        try:
            logger.debug("Starting SSE stream processing...")
            
            current_event = None  # Track current event type
            
            async for line in self.sse_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                # Handle event type declarations
                if line.startswith('event:'):
                    current_event = line.split(':', 1)[1].strip()
                    logger.debug("SSE event type: %s", current_event)
                    continue
                
                # Handle session endpoint discovery (BOTH FORMATS)
                if not self.message_url and line.startswith('data:'):
                    data_part = line.split(':', 1)[1].strip()
                    
                    # NEW FORMAT: event: endpoint + data: https://...
                    if current_event == "endpoint" and data_part.startswith('http'):
                        self.message_url = data_part
                        
                        # Extract session ID from URL if present
                        if 'session_id=' in data_part:
                            self.session_id = data_part.split('session_id=')[1].split('&')[0]
                        
                        logger.debug("Session endpoint discovered via event format: %s", self.session_id)
                        continue
                    
                    # OLD FORMAT: data: /messages/... (backwards compatibility)
                    elif '/messages/' in data_part:
                        endpoint_path = data_part
                        self.message_url = f"{self.url}{endpoint_path}"
                        
                        # Extract session ID if present
                        if 'session_id=' in endpoint_path:
                            self.session_id = endpoint_path.split('session_id=')[1].split('&')[0]
                        
                        logger.debug("Session endpoint discovered via old format: %s", self.session_id)
                        continue
                
                # Handle JSON-RPC responses
                if line.startswith('data:'):
                    data_part = line.split(':', 1)[1].strip()
                    
                    # Skip keepalive pings and empty data
                    if not data_part or data_part.startswith('ping') or data_part in ('{}', '[]'):
                        continue
                    
                    try:
                        response_data = json.loads(data_part)
                        
                        # Handle JSON-RPC responses with request IDs
                        if 'jsonrpc' in response_data and 'id' in response_data:
                            request_id = str(response_data['id'])
                            
                            # Resolve pending request if found
                            if request_id in self.pending_requests:
                                future = self.pending_requests.pop(request_id)
                                if not future.done():
                                    future.set_result(response_data)
                                    logger.debug("Resolved request ID: %s", request_id)
                    
                    except json.JSONDecodeError as e:
                        logger.debug("Non-JSON data in SSE stream (ignoring): %s", e)
                
                # Reset event type after processing data (only if we processed JSON-RPC)
                if line.startswith('data:') and current_event not in ("endpoint",):
                    current_event = None
                        
        except Exception as e:
            if self.enable_metrics:
                self._metrics["stream_errors"] += 1
            logger.error("SSE stream processing error: %s", e)

    async def _send_request(self, method: str, params: Dict[str, Any] = None, 
                           timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send JSON-RPC request and wait for async response via SSE."""
        if not self.message_url:
            raise RuntimeError("SSE transport not connected - no message URL")
        
        request_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        # Create future for async response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Send HTTP POST request
            headers = {
                'Content-Type': 'application/json',
                **self._get_headers()
            }
            
            response = await self.send_client.post(
                self.message_url, 
                headers=headers, 
                json=message
            )
            
            if response.status_code == 202:
                # Async response - wait for result via SSE
                request_timeout = timeout or self.default_timeout
                result = await asyncio.wait_for(future, timeout=request_timeout)
                return result
            elif response.status_code == 200:
                # Immediate response
                self.pending_requests.pop(request_id, None)
                return response.json()
            else:
                self.pending_requests.pop(request_id, None)
                raise RuntimeError(f"HTTP request failed with status: {response.status_code}")
                
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise
        except Exception:
            self.pending_requests.pop(request_id, None)
            raise

    async def _send_notification(self, method: str, params: Dict[str, Any] = None):
        """Send JSON-RPC notification (no response expected)."""
        if not self.message_url:
            raise RuntimeError("SSE transport not connected - no message URL")
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        headers = {
            'Content-Type': 'application/json',
            **self._get_headers()
        }
        
        response = await self.send_client.post(
            self.message_url,
            headers=headers,
            json=message
        )
        
        if response.status_code not in (200, 202):
            logger.warning("Notification failed with status: %s", response.status_code)

    async def send_ping(self) -> bool:
        """Send ping to check connection health."""
        if not self._initialized:
            return False
        
        start_time = time.time()
        try:
            # Use tools/list as a lightweight ping since not all servers support ping
            response = await self._send_request("tools/list", {}, timeout=5.0)
            
            if self.enable_metrics:
                ping_time = time.time() - start_time
                self._metrics["last_ping_time"] = ping_time
                logger.debug("SSE ping completed in %.3fs", ping_time)
            
            return 'error' not in response
        except Exception as e:
            logger.debug("SSE ping failed: %s", e)
            return False

    def is_connected(self) -> bool:
        """Check if the transport is connected and ready."""
        return self._initialized and self.session_id is not None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools from the server."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
        start_time = time.time()
        try:
            response = await self._send_request("tools/list", {})
            
            if 'error' in response:
                logger.error("Error getting tools: %s", response['error'])
                return []
            
            tools = response.get('result', {}).get('tools', [])
            
            if self.enable_metrics:
                response_time = time.time() - start_time
                logger.debug("Retrieved %d tools in %.3fs", len(tools), response_time)
            
            return tools
            
        except Exception as e:
            logger.error("Error getting tools: %s", e)
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], 
                       timeout: Optional[float] = None) -> Dict[str, Any]:
        """Execute a tool with the given arguments."""
        if not self._initialized:
            return {
                "isError": True,
                "error": "Transport not initialized"
            }

        start_time = time.time()
        if self.enable_metrics:
            self._metrics["total_calls"] += 1

        try:
            logger.debug("Calling tool '%s' with arguments: %s", tool_name, arguments)
            
            response = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments
                },
                timeout=timeout
            )
            
            if 'error' in response:
                if self.enable_metrics:
                    self._update_metrics(time.time() - start_time, False)
                
                return {
                    "isError": True,
                    "error": response['error'].get('message', 'Unknown error')
                }
            
            # Extract and normalize result using base class method
            result = response.get('result', {})
            normalized_result = self._normalize_mcp_response({"result": result})
            
            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, True)
            
            return normalized_result
            
        except asyncio.TimeoutError:
            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, False)
            
            return {
                "isError": True,
                "error": "Tool execution timed out"
            }
        except Exception as e:
            if self.enable_metrics:
                self._update_metrics(time.time() - start_time, False)
            
            logger.error("Error calling tool '%s': %s", tool_name, e)
            return {
                "isError": True,
                "error": str(e)
            }

    def _update_metrics(self, response_time: float, success: bool) -> None:
        """Update performance metrics."""
        if success:
            self._metrics["successful_calls"] += 1
        else:
            self._metrics["failed_calls"] += 1
            
        self._metrics["total_time"] += response_time
        if self._metrics["total_calls"] > 0:
            self._metrics["avg_response_time"] = (
                self._metrics["total_time"] / self._metrics["total_calls"]
            )

    async def list_resources(self) -> Dict[str, Any]:
        """List available resources from the server."""
        if not self._initialized:
            return {}
        
        try:
            response = await self._send_request("resources/list", {}, timeout=10.0)
            if 'error' in response:
                logger.debug("Resources not supported: %s", response['error'])
                return {}
            return response.get('result', {})
        except Exception as e:
            logger.debug("Error listing resources: %s", e)
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """List available prompts from the server."""
        if not self._initialized:
            return {}
        
        try:
            response = await self._send_request("prompts/list", {}, timeout=10.0)
            if 'error' in response:
                logger.debug("Prompts not supported: %s", response['error'])
                return {}
            return response.get('result', {})
        except Exception as e:
            logger.debug("Error listing prompts: %s", e)
            return {}

    async def close(self) -> None:
        """Close the transport and clean up resources."""
        if not self._initialized:
            return
        
        # Log final metrics
        if self.enable_metrics and self._metrics["total_calls"] > 0:
            logger.debug(
                "SSE transport closing - Total calls: %d, Success rate: %.1f%%, Avg response time: %.3fs",
                self._metrics["total_calls"],
                (self._metrics["successful_calls"] / self._metrics["total_calls"] * 100),
                self._metrics["avg_response_time"]
            )
        
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up all resources and reset state."""
        # Cancel SSE processing task
        if self.sse_task and not self.sse_task.done():
            self.sse_task.cancel()
            try:
                await self.sse_task
            except asyncio.CancelledError:
                pass
        
        # Close SSE stream context
        if self.sse_stream_context:
            try:
                await self.sse_stream_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("Error closing SSE stream: %s", e)
        
        # Close HTTP clients
        if self.stream_client:
            await self.stream_client.aclose()
        
        if self.send_client:
            await self.send_client.aclose()
        
        # Cancel any pending requests
        for request_id, future in self.pending_requests.items():
            if not future.done():
                future.cancel()
        
        # Reset state
        self._initialized = False
        self.session_id = None
        self.message_url = None
        self.pending_requests.clear()
        self.sse_task = None
        self.sse_response = None
        self.sse_stream_context = None
        self.stream_client = None
        self.send_client = None

    # ------------------------------------------------------------------ #
    #  Metrics and monitoring (consistent with other transports)        #
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
            "session_discoveries": self._metrics.get("session_discoveries", 0),
            "stream_errors": 0
        }

    # ------------------------------------------------------------------ #
    #  Backward compatibility                                            #
    # ------------------------------------------------------------------ #
    def get_streams(self) -> List[tuple]:
        """SSE transport doesn't expose raw streams."""
        return []

    # ------------------------------------------------------------------ #
    #  Context manager support                                           #
    # ------------------------------------------------------------------ #
    async def __aenter__(self):
        """Context manager entry."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize SSETransport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()