# chuk_tool_processor/mcp/transport/sse_transport.py
"""
Fixed SSE transport that matches your server's actual behavior.
Based on your working debug script.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Dict, Any, List, Optional, Tuple
import logging

import httpx

from .base_transport import MCPBaseTransport

logger = logging.getLogger(__name__)


class SSETransport(MCPBaseTransport):
    """
    SSE transport that works with your server's two-step async pattern:
    1. POST messages to /messages endpoint
    2. Receive responses via SSE stream
    """

    def __init__(self, url: str, api_key: Optional[str] = None, 
                 connection_timeout: float = 30.0, default_timeout: float = 30.0):
        """Initialize SSE transport."""
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.connection_timeout = connection_timeout
        self.default_timeout = default_timeout
        
        # State
        self.session_id = None
        self.message_url = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self._initialized = False
        
        # HTTP clients
        self.stream_client = None
        self.send_client = None
        
        # SSE stream
        self.sse_task = None
        self.sse_response = None
        self.sse_stream_context = None

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with auth if available."""
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    async def initialize(self) -> bool:
        """Initialize SSE connection and MCP handshake."""
        if self._initialized:
            logger.warning("Transport already initialized")
            return True
        
        try:
            logger.info("Initializing SSE transport...")
            
            # Create HTTP clients
            self.stream_client = httpx.AsyncClient(timeout=self.connection_timeout)
            self.send_client = httpx.AsyncClient(timeout=self.default_timeout)
            
            # Connect to SSE stream
            sse_url = f"{self.url}/sse"
            logger.debug(f"Connecting to SSE: {sse_url}")
            
            self.sse_stream_context = self.stream_client.stream(
                'GET', sse_url, headers=self._get_headers()
            )
            self.sse_response = await self.sse_stream_context.__aenter__()
            
            if self.sse_response.status_code != 200:
                logger.error(f"SSE connection failed: {self.sse_response.status_code}")
                return False
            
            logger.info("SSE streaming connection established")
            
            # Start SSE processing task
            self.sse_task = asyncio.create_task(self._process_sse_stream())
            
            # Wait for session discovery
            logger.debug("Waiting for session discovery...")
            for i in range(50):  # 5 seconds max
                if self.message_url:
                    break
                await asyncio.sleep(0.1)
            
            if not self.message_url:
                logger.error("Failed to get session info from SSE")
                return False
            
            logger.info(f"Session ready: {self.session_id}")
            
            # Now do MCP initialization
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
                    logger.error(f"Initialize failed: {init_response['error']}")
                    return False
                
                # Send initialized notification
                await self._send_notification("notifications/initialized")
                
                self._initialized = True
                logger.info("SSE transport initialized successfully")
                return True
                
            except Exception as e:
                logger.error(f"MCP initialization failed: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing SSE transport: {e}", exc_info=True)
            await self._cleanup()
            return False

    async def _process_sse_stream(self):
        """Process the persistent SSE stream."""
        try:
            logger.debug("Starting SSE stream processing...")
            
            async for line in self.sse_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                # Handle session endpoint discovery
                if not self.message_url and line.startswith('data:') and '/messages/' in line:
                    endpoint_path = line.split(':', 1)[1].strip()
                    self.message_url = f"{self.url}{endpoint_path}"
                    
                    if 'session_id=' in endpoint_path:
                        self.session_id = endpoint_path.split('session_id=')[1].split('&')[0]
                    
                    logger.debug(f"Got session info: {self.session_id}")
                    continue
                
                # Handle JSON-RPC responses
                if line.startswith('data:'):
                    data_part = line.split(':', 1)[1].strip()
                    
                    # Skip pings and empty data
                    if not data_part or data_part.startswith('ping'):
                        continue
                    
                    try:
                        response_data = json.loads(data_part)
                        
                        if 'jsonrpc' in response_data and 'id' in response_data:
                            request_id = str(response_data['id'])
                            
                            # Resolve pending request
                            if request_id in self.pending_requests:
                                future = self.pending_requests.pop(request_id)
                                if not future.done():
                                    future.set_result(response_data)
                                    logger.debug(f"Resolved request: {request_id}")
                    
                    except json.JSONDecodeError:
                        pass  # Not JSON, ignore
                        
        except Exception as e:
            logger.error(f"SSE stream error: {e}")

    async def _send_request(self, method: str, params: Dict[str, Any] = None, 
                           timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send request and wait for async response."""
        if not self.message_url:
            raise RuntimeError("Not connected")
        
        request_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Send message
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
                # Wait for async response
                timeout = timeout or self.default_timeout
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            elif response.status_code == 200:
                # Immediate response
                self.pending_requests.pop(request_id, None)
                return response.json()
            else:
                self.pending_requests.pop(request_id, None)
                raise RuntimeError(f"Request failed: {response.status_code}")
                
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            raise
        except Exception:
            self.pending_requests.pop(request_id, None)
            raise

    async def _send_notification(self, method: str, params: Dict[str, Any] = None):
        """Send notification (no response expected)."""
        if not self.message_url:
            raise RuntimeError("Not connected")
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        headers = {
            'Content-Type': 'application/json',
            **self._get_headers()
        }
        
        await self.send_client.post(
            self.message_url,
            headers=headers,
            json=message
        )

    async def send_ping(self) -> bool:
        """Send ping to check connection."""
        if not self._initialized:
            return False
        
        try:
            # Your server might not support ping, so we'll just check if we can list tools
            response = await self._send_request("tools/list", {}, timeout=5.0)
            return 'error' not in response
        except Exception:
            return False

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get tools list."""
        if not self._initialized:
            logger.error("Cannot get tools: transport not initialized")
            return []
        
        try:
            response = await self._send_request("tools/list", {})
            
            if 'error' in response:
                logger.error(f"Error getting tools: {response['error']}")
                return []
            
            tools = response.get('result', {}).get('tools', [])
            logger.debug(f"Retrieved {len(tools)} tools")
            return tools
            
        except Exception as e:
            logger.error(f"Error getting tools: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], 
                       timeout: Optional[float] = None) -> Dict[str, Any]:
        """Call a tool."""
        if not self._initialized:
            return {
                "isError": True,
                "error": "Transport not initialized"
            }

        try:
            logger.debug(f"Calling tool {tool_name} with args: {arguments}")
            
            response = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments
                },
                timeout=timeout
            )
            
            if 'error' in response:
                return {
                    "isError": True,
                    "error": response['error'].get('message', 'Unknown error')
                }
            
            # Extract result
            result = response.get('result', {})
            
            # Handle content format
            if 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) == 1:
                    content_item = content[0]
                    if isinstance(content_item, dict) and content_item.get('type') == 'text':
                        text_content = content_item.get('text', '')
                        try:
                            # Try to parse as JSON
                            parsed_content = json.loads(text_content)
                            return {
                                "isError": False,
                                "content": parsed_content
                            }
                        except json.JSONDecodeError:
                            return {
                                "isError": False,
                                "content": text_content
                            }
                
                return {
                    "isError": False,
                    "content": content
                }
            
            return {
                "isError": False,
                "content": result
            }
            
        except asyncio.TimeoutError:
            return {
                "isError": True,
                "error": f"Tool execution timed out"
            }
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {
                "isError": True,
                "error": str(e)
            }

    async def list_resources(self) -> Dict[str, Any]:
        """List resources."""
        if not self._initialized:
            return {}
        
        try:
            response = await self._send_request("resources/list", {}, timeout=10.0)
            if 'error' in response:
                logger.debug(f"Resources not supported: {response['error']}")
                return {}
            return response.get('result', {})
        except Exception:
            return {}

    async def list_prompts(self) -> Dict[str, Any]:
        """List prompts."""
        if not self._initialized:
            return {}
        
        try:
            response = await self._send_request("prompts/list", {}, timeout=10.0)
            if 'error' in response:
                logger.debug(f"Prompts not supported: {response['error']}")
                return {}
            return response.get('result', {})
        except Exception:
            return {}

    async def close(self) -> None:
        """Close the transport."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self.sse_task:
            self.sse_task.cancel()
            try:
                await self.sse_task
            except asyncio.CancelledError:
                pass
        
        if self.sse_stream_context:
            try:
                await self.sse_stream_context.__aexit__(None, None, None)
            except Exception:
                pass
        
        if self.stream_client:
            await self.stream_client.aclose()
        
        if self.send_client:
            await self.send_client.aclose()
        
        self._initialized = False
        self.session_id = None
        self.message_url = None
        self.pending_requests.clear()

    def get_streams(self) -> List[tuple]:
        """Not applicable for this transport."""
        return []

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._initialized and self.session_id is not None

    async def __aenter__(self):
        """Context manager support."""
        success = await self.initialize()
        if not success:
            raise RuntimeError("Failed to initialize SSE transport")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()

    def __repr__(self) -> str:
        """String representation."""
        status = "initialized" if self._initialized else "not initialized"
        return f"SSETransport(status={status}, url={self.url}, session={self.session_id})"