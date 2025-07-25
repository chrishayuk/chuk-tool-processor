#!/usr/bin/env python
"""
working_debug_script.py - Clean working async SSE MCP debug script
Based on the successful persistent SSE connection pattern
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv

# Load .env file
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ Loaded .env file from {env_file}")

class WorkingSSEDebugClient:
    """Clean working async SSE MCP client for debugging."""
    
    def __init__(self, server_url: str, bearer_token: Optional[str] = None):
        self.server_url = server_url.rstrip('/')
        self.bearer_token = bearer_token
        self.session_id = None
        self.message_url = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.sse_task = None
        self.client = None
        self.sse_response = None
        self.sse_stream_context = None
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with auth if available."""
        headers = {}
        if self.bearer_token:
            headers['Authorization'] = f'Bearer {self.bearer_token}'
        return headers
    
    async def connect(self) -> bool:
        """Connect using the working persistent SSE pattern."""
        self.client = httpx.AsyncClient(timeout=60.0)
        
        sse_url = f"{self.server_url}/sse"
        print(f"🔗 Connecting to SSE: {sse_url}")
        
        try:
            print("📡 Using streaming request (proven to work)...")
            
            # Use streaming approach that works
            self.sse_stream_context = self.client.stream('GET', sse_url, headers=self._get_headers())
            self.sse_response = await self.sse_stream_context.__aenter__()
            
            if self.sse_response.status_code != 200:
                print(f"❌ SSE connection failed: {self.sse_response.status_code}")
                text = await self.sse_response.atext()
                print(f"Error: {text}")
                return False
            
            print(f"✅ SSE streaming connection established: {self.sse_response.status_code}")
            
            # Start persistent SSE processing
            self.sse_task = asyncio.create_task(self._process_sse_stream())
            
            # Wait for session discovery
            print("⏳ Waiting for session discovery...")
            for i in range(50):  # 5 seconds max
                if self.message_url:
                    break
                await asyncio.sleep(0.1)
                if i % 10 == 0 and i > 0:
                    print(f"⏳ Still waiting... ({i/10:.1f}s)")
            
            if not self.message_url:
                print("❌ Failed to get session info from SSE")
                return False
            
            print(f"✅ Session ready: {self.session_id}")
            print(f"📍 Message URL: {self.message_url}")
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _process_sse_stream(self):
        """Process the persistent SSE stream for session discovery and responses."""
        try:
            print("👂 Starting persistent SSE stream processing...")
            event_count = 0
            
            async for line in self.sse_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                event_count += 1
                print(f"📡 SSE #{event_count}: {line}")
                
                # Handle initial session setup
                if not self.message_url and line.startswith('data:') and '/messages/' in line:
                    endpoint_path = line.split(':', 1)[1].strip()
                    self.message_url = f"{self.server_url}{endpoint_path}"
                    
                    if 'session_id=' in endpoint_path:
                        self.session_id = endpoint_path.split('session_id=')[1].split('&')[0]
                    
                    print(f"✅ Got session info from SSE")
                    continue
                
                # Handle JSON-RPC responses
                await self._handle_sse_response(line)
                
        except Exception as e:
            print(f"❌ SSE stream error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_sse_response(self, line: str):
        """Handle SSE line that might contain JSON-RPC response."""
        try:
            if not line.startswith('data:'):
                return
            
            data_part = line.split(':', 1)[1].strip()
            
            # Skip pings, empty data, and session announcements
            if not data_part or data_part.startswith('ping') or '/messages/' in data_part:
                return
            
            # Try to parse as JSON-RPC response
            try:
                response_data = json.loads(data_part)
                
                if 'jsonrpc' in response_data and 'id' in response_data:
                    request_id = str(response_data['id'])
                    print(f"🎉 Received JSON-RPC response for ID: {request_id}")
                    
                    # Resolve pending request
                    if request_id in self.pending_requests:
                        future = self.pending_requests.pop(request_id)
                        if not future.done():
                            future.set_result(response_data)
                            print(f"✅ Resolved pending request: {request_id}")
                    else:
                        print(f"⚠️ No pending request for ID: {request_id}")
                
            except json.JSONDecodeError:
                print(f"📡 Non-JSON data: {data_part}")
                
        except Exception as e:
            print(f"⚠️ Error handling SSE response: {e}")
    
    async def send_request(self, method: str, params: Dict[str, Any] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Send MCP request and wait for async response."""
        if not self.message_url:
            raise RuntimeError("Not connected - call connect() first")
        
        request_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        print(f"📤 Sending {method} (ID: {request_id})")
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        try:
            # Send message via separate client
            headers = {
                'Content-Type': 'application/json',
                **self._get_headers()
            }
            
            async with httpx.AsyncClient(timeout=10.0) as send_client:
                response = await send_client.post(self.message_url, headers=headers, json=message)
                print(f"📨 Message response: {response.status_code}")
                
                if response.status_code == 202:
                    print(f"✅ Message accepted - waiting for response via persistent SSE...")
                    
                    # Wait for async response
                    try:
                        result = await asyncio.wait_for(future, timeout=timeout)
                        print(f"✅ Got response for {method}")
                        return result
                    except asyncio.TimeoutError:
                        self.pending_requests.pop(request_id, None)
                        raise TimeoutError(f"Timeout waiting for {method} response after {timeout}s")
                
                elif response.status_code == 200:
                    # Immediate response
                    self.pending_requests.pop(request_id, None)
                    return response.json()
                else:
                    self.pending_requests.pop(request_id, None)
                    raise RuntimeError(f"Request failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            raise
    
    async def send_notification(self, method: str, params: Dict[str, Any] = None):
        """Send MCP notification (no response expected)."""
        if not self.message_url:
            raise RuntimeError("Not connected - call connect() first")
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        print(f"📢 Sending notification: {method}")
        
        headers = {
            'Content-Type': 'application/json',
            **self._get_headers()
        }
        
        async with httpx.AsyncClient(timeout=10.0) as send_client:
            response = await send_client.post(self.message_url, headers=headers, json=message)
            print(f"📨 Notification response: {response.status_code}")
            return response.status_code
    
    async def close(self):
        """Clean up connections."""
        if self.sse_task:
            self.sse_task.cancel()
        if self.sse_stream_context:
            try:
                await self.sse_stream_context.__aexit__(None, None, None)
            except:
                pass
        if self.client:
            await self.client.aclose()

def get_server_config():
    """Get server configuration from environment."""
    url_map = os.getenv('MCP_SERVER_URL_MAP', '{}')
    bearer_token = os.getenv('MCP_BEARER_TOKEN')
    
    try:
        url_config = json.loads(url_map)
    except json.JSONDecodeError:
        return None, None
    
    server_url = url_config.get('perplexity_server')
    return server_url, bearer_token

async def debug_mcp_server():
    """Debug the MCP server with working async SSE client."""
    print("🔍 Working Async SSE MCP Debug Script")
    print("=" * 50)
    
    server_url, bearer_token = get_server_config()
    if not server_url:
        print("❌ No server configuration found")
        return
    
    print(f"🎯 Server: {server_url}")
    print(f"🔑 Token: {'SET' if bearer_token else 'NOT SET'}")
    
    client = WorkingSSEDebugClient(server_url, bearer_token)
    
    try:
        # Step 1: Connect
        print(f"\n{'='*20} CONNECTING {'='*20}")
        if not await client.connect():
            print("❌ Connection failed - stopping debug")
            return
        
        # Step 2: Initialize
        print(f"\n{'='*20} INITIALIZING {'='*20}")
        init_response = await client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "debug-client",
                "version": "1.0.0"
            }
        })
        
        print(f"✅ Initialize successful!")
        print(f"📋 Server: {init_response.get('result', {}).get('serverInfo', {})}")
        print(f"📋 Capabilities: {init_response.get('result', {}).get('capabilities', {})}")
        
        # Step 3: Send initialized notification
        print(f"\n{'='*20} SENDING INITIALIZED {'='*20}")
        await client.send_notification("notifications/initialized")
        
        # Step 4: List tools (try different approaches)
        print(f"\n{'='*20} LISTING TOOLS {'='*20}")
        
        # Try with empty params
        try:
            tools_response = await client.send_request("tools/list", {})
            if 'error' not in tools_response:
                print(f"✅ Tools list successful!")
                tools = tools_response.get('result', {}).get('tools', [])
                print(f"📋 Found {len(tools)} tools:")
                for i, tool in enumerate(tools[:5]):  # Show first 5
                    name = tool.get('name', 'unknown')
                    desc = tool.get('description', 'No description')
                    print(f"   {i+1}. {name}: {desc}")
            else:
                print(f"❌ Tools list failed: {tools_response.get('error', {}).get('message', 'Unknown error')}")
                
                # Try without params
                print(f"🔄 Retrying without params...")
                tools_response = await client.send_request("tools/list")
                if 'error' not in tools_response:
                    print(f"✅ Tools list successful (no params)!")
                    tools = tools_response.get('result', {}).get('tools', [])
                    print(f"📋 Found {len(tools)} tools")
                else:
                    print(f"❌ Still failed: {tools_response.get('error', {}).get('message', 'Unknown error')}")
                    
        except Exception as e:
            print(f"❌ Tools list error: {e}")
        
        # Step 5: Try other methods
        print(f"\n{'='*20} TESTING OTHER METHODS {'='*20}")
        
        test_methods = [
            ("resources/list", {}),
            ("prompts/list", {}),
        ]
        
        for method, params in test_methods:
            try:
                print(f"🔧 Testing {method}...")
                response = await client.send_request(method, params, timeout=10.0)
                if 'error' not in response:
                    print(f"   ✅ {method} successful!")
                else:
                    error_msg = response.get('error', {}).get('message', 'Unknown error')
                    print(f"   ❌ {method} failed: {error_msg}")
            except Exception as e:
                print(f"   ❌ {method} error: {e}")
        
        print(f"\n🎉 Debug completed successfully!")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(debug_mcp_server())