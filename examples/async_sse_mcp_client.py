#!/usr/bin/env python
"""
async_sse_mcp_client.py - Working client for async SSE MCP servers
────────────────────────────────────────────────────────────────

This client properly handles the async SSE pattern where:
1. Client sends MCP request → Server returns 202 Accepted
2. Server processes request asynchronously
3. Server sends response via SSE stream

This should work with your remote server that returns 202 status codes.
"""

import asyncio
import builtins
import contextlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load .env file
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ Loaded .env file from {env_file}")


class AsyncSSEMCPClient:
    """MCP client that handles async SSE responses."""

    def __init__(self, server_url: str, bearer_token: str | None = None):
        self.server_url = server_url.rstrip("/")
        self.bearer_token = bearer_token
        self.session_id = None
        self.message_url = None
        self.pending_requests: dict[str, asyncio.Future] = {}
        self.sse_task = None
        self.sse_response = None  # Store the SSE response
        self.sse_stream_context = None  # Store the stream context
        self.client = None

    async def connect(self) -> bool:
        """Connect to the SSE server and get the message endpoint."""
        self.client = httpx.AsyncClient(timeout=30.0)

        headers = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        try:
            # Connect to SSE endpoint using streaming (this works!)
            sse_url = f"{self.server_url}/sse"
            print(f"🔗 Connecting to SSE: {sse_url}")
            print("📡 Using streaming request (non-streaming times out)...")

            # Use streaming request - this works according to diagnostic
            self.sse_response = await self.client.__aenter__()
            self.sse_stream = await self.sse_response.stream("GET", sse_url, headers=headers).__aenter__()

            if self.sse_stream.status_code != 200:
                print(f"❌ SSE connection failed: {self.sse_stream.status_code}")
                text = await self.sse_stream.atext()
                print(f"Error: {text}")
                return False

            print(f"✅ SSE streaming connection established: {self.sse_stream.status_code}")

            # Start the SSE listener task
            self.sse_task = asyncio.create_task(self._process_sse_stream())

            # Wait for the endpoint to be discovered
            print("⏳ Waiting for endpoint discovery...")
            for i in range(100):  # Wait up to 10 seconds
                if self.message_url:
                    break
                await asyncio.sleep(0.1)
                if i % 10 == 0:
                    print(f"⏳ Still waiting... ({i / 10:.1f}s)")

            if not self.message_url:
                print("❌ Failed to get message endpoint from SSE")
                return False

            print(f"✅ Got message endpoint: {self.message_url}")
            print(f"🆔 Session ID: {self.session_id}")
            return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    async def _process_sse_stream(self) -> None:
        """Process the SSE stream for both endpoint discovery and responses."""
        try:
            print("👂 Starting SSE stream processing...")
            event_count = 0

            async for line in self.sse_response.aiter_lines():
                line = line.strip()
                if not line:
                    continue

                event_count += 1
                print(f"📡 SSE #{event_count}: {line}")

                # Handle endpoint discovery
                if not self.message_url:
                    if line.startswith("event:") and "endpoint" in line:
                        continue
                    elif line.startswith("data:"):
                        endpoint_path = line.split(":", 1)[1].strip()
                        self.message_url = f"{self.server_url}{endpoint_path}"

                        # Extract session ID from URL
                        if "session_id=" in endpoint_path:
                            self.session_id = endpoint_path.split("session_id=")[1].split("&")[0]

                        print("✅ SSE listener ready for responses")
                        continue

                # Process response data (after endpoint is known)
                await self._process_sse_line(line)

                # Add periodic status updates
                if event_count % 5 == 0:
                    print(f"📊 SSE events processed: {event_count}, pending requests: {len(self.pending_requests)}")

        except Exception as e:
            print(f"❌ SSE stream error: {e}")
            import traceback

            traceback.print_exc()

    async def _continue_listening(self, sse_response) -> None:
        """This method is no longer used"""
        pass

    async def _start_sse_listener(self) -> None:
        """This method is no longer used"""
        pass

    async def _process_sse_line(self, line: str) -> None:
        """Process a single SSE line for MCP responses."""
        try:
            # Parse SSE events for MCP responses
            if line.startswith("data:"):
                data_part = line.split(":", 1)[1].strip()

                # Debug: log all SSE data
                print(f"🔍 Raw SSE data: {data_part}")

                # Skip ping/heartbeat messages
                if data_part in ("ping", "heartbeat", ""):
                    return

                try:
                    response_data = json.loads(data_part)
                    print(f"📋 Parsed JSON: {json.dumps(response_data, indent=2)}")

                    if "jsonrpc" in response_data and "id" in response_data:
                        request_id = str(response_data["id"])
                        print(f"📨 Received response for request {request_id}")

                        # Resolve the pending request
                        if request_id in self.pending_requests:
                            future = self.pending_requests.pop(request_id)
                            if not future.done():
                                future.set_result(response_data)
                                print(f"✅ Resolved future for request {request_id}")
                        else:
                            print(f"⚠️ No pending request for ID {request_id}")
                            print(f"📊 Current pending: {list(self.pending_requests.keys())}")

                except json.JSONDecodeError:
                    # Not a JSON response, might be other SSE data
                    print(f"📡 Non-JSON SSE data: {data_part}")
            else:
                print(f"📡 SSE event: {line}")

        except Exception as e:
            print(f"⚠️ Error processing SSE line: {e}")

    async def _listen_for_responses(self, sse_response) -> None:
        """Listen for MCP responses on the SSE stream."""
        # This method is no longer used - replaced by _start_sse_listener
        pass

    async def send_request(self, method: str, params: dict[str, Any] = None, timeout: float = 10.0) -> dict[str, Any]:
        """Send an MCP request and wait for async response."""
        if not self.message_url:
            raise RuntimeError("Not connected - call connect() first")

        request_id = str(uuid.uuid4())
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}

        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        try:
            print(f"📤 Sending {method} request (ID: {request_id})")
            print(f"🔗 URL: {self.message_url}")
            print(f"📝 Message: {json.dumps(message, indent=2)}")

            # Send request
            response = await self.client.post(self.message_url, headers=headers, json=message)

            if response.status_code == 202:
                print("✅ Request accepted (202) - waiting for async response...")
                print(f"⏱️ Timeout: {timeout} seconds")

                # Wait for response via SSE
                try:
                    result = await asyncio.wait_for(future, timeout=timeout)
                    print(f"📨 Got async response for {method}")
                    return result
                except TimeoutError:
                    self.pending_requests.pop(request_id, None)
                    print(f"⏰ Timeout waiting for {method} response after {timeout}s")
                    print(f"📊 Pending requests: {list(self.pending_requests.keys())}")

                    # Check if SSE listener is still running
                    if self.sse_task and not self.sse_task.done():
                        print("✅ SSE listener is still running")
                    else:
                        print("❌ SSE listener has stopped!")
                        if self.sse_task:
                            try:
                                await self.sse_task
                            except Exception as e:
                                print(f"SSE task error: {e}")

                    # Try a simple test to see if server is responding at all
                    print("🧪 Testing if server responds to ping...")
                    try:
                        ping_response = await self.client.get(f"{self.server_url}/")
                        print(f"Ping response: {ping_response.status_code}")
                    except Exception as e:
                        print(f"Ping failed: {e}")

                    raise TimeoutError(f"Timeout waiting for {method} response")

            elif response.status_code == 200:
                # Immediate response (shouldn't happen with this server, but handle it)
                try:
                    return response.json()
                except:
                    raise RuntimeError(f"Invalid JSON response: {response.text}")
            else:
                raise RuntimeError(f"Request failed: {response.status_code} - {response.text}")

        except Exception:
            # Clean up pending request
            self.pending_requests.pop(request_id, None)
            raise

    async def initialize(self) -> dict[str, Any]:
        """Initialize the MCP connection."""
        return await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "async-sse-client", "version": "1.0.0"},
            },
        )

    async def list_tools(self) -> dict[str, Any]:
        """List available tools."""
        return await self.send_request("tools/list")

    async def call_tool(self, name: str, arguments: dict[str, Any] = None) -> dict[str, Any]:
        """Call a specific tool."""
        return await self.send_request("tools/call", {"name": name, "arguments": arguments or {}})

    async def close(self):
        """Close the connection."""
        if self.sse_task:
            self.sse_task.cancel()
        if self.sse_stream_context:
            with contextlib.suppress(builtins.BaseException):
                await self.sse_stream_context.__aexit__(None, None, None)
        if self.client:
            await self.client.aclose()


def get_server_config():
    """Get server configuration from environment."""
    url_map = os.getenv("MCP_SERVER_URL_MAP", "{}")
    bearer_token = os.getenv("MCP_BEARER_TOKEN")

    try:
        url_config = json.loads(url_map)
    except json.JSONDecodeError:
        return None, None

    server_url = url_config.get("perplexity_server")
    return server_url, bearer_token


async def demo_async_client():
    """Demonstrate the async SSE MCP client."""
    print("🚀 Async SSE MCP Client Demo")
    print("=" * 50)

    server_url, bearer_token = get_server_config()
    if not server_url:
        print("❌ No server configuration found")
        return

    print(f"🎯 Server: {server_url}")
    print(f"🔑 Token: {'SET' if bearer_token else 'NOT SET'}")

    client = AsyncSSEMCPClient(server_url, bearer_token)

    try:
        # Connect
        print("\n🔗 Connecting...")
        if not await client.connect():
            print("❌ Connection failed")
            return

        # Initialize
        print("\n🚀 Initializing...")
        init_response = await client.initialize()
        print(f"✅ Initialized: {json.dumps(init_response, indent=2)}")

        # List tools
        print("\n🛠️ Listing tools...")
        tools_response = await client.list_tools()
        print(f"✅ Tools: {json.dumps(tools_response, indent=2)}")

        # Extract tool names
        tools = tools_response.get("result", {}).get("tools", [])
        if tools:
            print("\n📋 Available tools:")
            for tool in tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "No description")
                print(f"  • {name}: {desc}")

            # Test first tool
            first_tool = tools[0]
            tool_name = first_tool.get("name")
            if tool_name:
                print(f"\n🔧 Testing tool: {tool_name}")
                try:
                    tool_response = await client.call_tool(tool_name, {"query": "test query"})
                    print(f"✅ Tool response: {json.dumps(tool_response, indent=2)}")
                except Exception as e:
                    print(f"⚠️ Tool call failed: {e}")
        else:
            print("ℹ️ No tools available")

        print("\n🎉 Demo completed successfully!")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(demo_async_client())
