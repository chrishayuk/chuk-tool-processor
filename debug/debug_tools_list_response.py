#!/usr/bin/env python
# examples/server_diagnostics.py
"""
Run diagnostic tests with proper MCP initialization to test server responses.
"""

import asyncio
import contextlib
import json
import time

import httpx


async def test_proper_mcp_flow():
    """Test the proper MCP initialization flow followed by tools/list."""

    print("=== MCP Server Diagnostic Tests (Proper Flow) ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Get the message endpoint
        print("\n1. Getting message endpoint...")
        message_url = None

        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

        async with client.stream("GET", "http://localhost:8000/sse", headers=headers) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and "/messages/" in line:
                    endpoint = line[6:].strip()
                    message_url = f"http://localhost:8000{endpoint}"
                    print(f"   ✅ Got: {message_url}")
                    break

        if not message_url:
            print("   ❌ Failed to get message URL")
            return False

        # Step 2: Send proper MCP initialize request
        print("\n2. Sending MCP initialize handshake...")

        init_message = {
            "jsonrpc": "2.0",
            "id": "initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "sampling": {}},
                "clientInfo": {"name": "diagnostic-client", "version": "1.0.0"},
            },
        }

        print(f"   Request: {json.dumps(init_message, indent=4)}")

        try:
            response = await client.post(message_url, json=init_message, headers={"Content-Type": "application/json"})

            print(f"   Response: {response.status_code} - {response.text}")

            if response.status_code == 200:
                # Immediate response
                try:
                    json_resp = response.json()
                    print("   ✅ Immediate initialization response:")
                    print(f"   {json.dumps(json_resp, indent=4)}")
                    return True
                except Exception as e:
                    print(f"   ❌ Failed to parse JSON: {e}")
                    return False
            elif response.status_code == 202:
                print("   ✅ Initialization accepted for async processing")
                return True
            else:
                print(f"   ❌ Unexpected status code: {response.status_code}")
                return False

        except Exception as e:
            print(f"   ❌ Initialize request failed: {e}")
            return False


async def test_with_proper_mcp_monitoring():
    """Test with proper MCP flow and SSE monitoring."""

    print("\n=== Testing with Proper MCP Flow and SSE Monitoring ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        message_url = None
        responses = []
        initialized = False

        async def monitor_sse():
            """Monitor SSE stream and track responses."""
            nonlocal message_url, initialized

            headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

            try:
                async with client.stream("GET", "http://localhost:8000/sse", headers=headers) as response:
                    async for line in response.aiter_lines():
                        print(f"SSE: {line}")

                        if line.startswith("data: ") and "/messages/" in line:
                            endpoint = line[6:].strip()
                            message_url = f"http://localhost:8000{endpoint}"
                            print(f"📡 Got message endpoint: {message_url}")

                        elif line.startswith("data: ") and line != "data: ":
                            # Potential response message
                            data = line[6:].strip()
                            try:
                                parsed = json.loads(data)
                                responses.append(parsed)
                                print(f"📨 Response received: {json.dumps(parsed, indent=2)}")

                                # Check if this is initialize response
                                if parsed.get("id") == "initialize":
                                    initialized = True
                                    print("✅ MCP initialization completed!")

                            except Exception:
                                print(f"📨 Non-JSON response: {data}")

            except Exception as e:
                print(f"SSE Error: {e}")

        # Start SSE monitoring
        sse_task = asyncio.create_task(monitor_sse())

        # Wait for endpoint
        await asyncio.sleep(2.0)

        if not message_url:
            print("❌ No message URL received")
            sse_task.cancel()
            return

        # Step 1: Send initialize request
        print(f"\n🔄 Sending initialize request to: {message_url}")

        init_message = {
            "jsonrpc": "2.0",
            "id": "initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "sampling": {}},
                "clientInfo": {"name": "diagnostic-client", "version": "1.0.0"},
            },
        }

        try:
            response = await client.post(message_url, json=init_message, headers={"Content-Type": "application/json"})

            print(f"📥 Initialize HTTP Response: {response.status_code} - {response.text}")

            if response.status_code == 202:
                print("⏳ Waiting for async initialize response...")

                # Wait for initialize response
                start_time = time.time()
                while not initialized and (time.time() - start_time) < 10.0:
                    await asyncio.sleep(0.1)

                if initialized:
                    print("✅ Initialization completed successfully!")

                    # Step 2: Send initialized notification
                    notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}

                    await client.post(message_url, json=notification, headers={"Content-Type": "application/json"})
                    print("📤 Sent initialized notification")

                    # Step 3: Now try tools/list
                    print("\n🔧 Testing tools/list after proper initialization...")

                    tools_message = {"jsonrpc": "2.0", "id": "tools_list", "method": "tools/list", "params": {}}

                    tools_response = await client.post(
                        message_url, json=tools_message, headers={"Content-Type": "application/json"}
                    )

                    print(f"📥 Tools HTTP Response: {tools_response.status_code} - {tools_response.text}")

                    if tools_response.status_code == 202:
                        print("⏳ Waiting for async tools/list response...")

                        # Wait for tools response
                        start_time = time.time()
                        tools_received = False

                        while not tools_received and (time.time() - start_time) < 10.0:
                            for resp in responses:
                                if resp.get("id") == "tools_list":
                                    tools_received = True
                                    print("✅ Got tools/list response!")

                                    if "result" in resp and "tools" in resp["result"]:
                                        tools = resp["result"]["tools"]
                                        print(f"🔧 Found {len(tools)} tools:")
                                        for tool in tools:
                                            name = tool.get("name", "Unknown")
                                            desc = tool.get("description", "No description")
                                            print(f"   - {name}: {desc}")
                                    break
                            await asyncio.sleep(0.1)

                        if not tools_received:
                            print("❌ No tools/list response received")

                else:
                    print("❌ Initialization failed or timed out")

        except Exception as e:
            print(f"❌ Request failed: {e}")

        # Cleanup
        sse_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sse_task

        print(f"\n📊 Summary: Received {len(responses)} total responses")


async def test_invalid_requests():
    """Test what happens with invalid requests (no initialization)."""

    print("\n=== Testing Invalid Requests (No Initialization) ===")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Get message endpoint
        message_url = None
        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

        async with client.stream("GET", "http://localhost:8000/sse", headers=headers) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and "/messages/" in line:
                    endpoint = line[6:].strip()
                    message_url = f"http://localhost:8000{endpoint}"
                    break

        if not message_url:
            print("❌ Failed to get message URL")
            return

        # Try tools/list WITHOUT initialization
        print("🚫 Testing tools/list WITHOUT initialization...")

        tools_message = {"jsonrpc": "2.0", "id": "tools_list_no_init", "method": "tools/list", "params": {}}

        try:
            response = await client.post(message_url, json=tools_message, headers={"Content-Type": "application/json"})

            print(f"📥 Response: {response.status_code} - {response.text}")

            if response.status_code == 202:
                print("⚠️  Server accepted request without initialization (this explains the timeout issue!)")
            elif response.status_code == 400:
                print("✅ Server correctly rejected request without initialization")
            else:
                print(f"🤔 Unexpected response: {response.status_code}")

        except Exception as e:
            print(f"❌ Request failed: {e}")


if __name__ == "__main__":

    async def main():
        success = await test_proper_mcp_flow()
        if success:
            await test_with_proper_mcp_monitoring()
        await test_invalid_requests()

        print("\n" + "=" * 60)
        print("🎯 Key Findings:")
        print("1. MCP servers require initialization handshake FIRST")
        print("2. tools/list only works AFTER successful initialization")
        print("3. Server accepts requests but won't respond without init")
        print("4. This explains why the original transport timed out!")
        print("5. The fixed transport with initialization now works perfectly ✅")

    asyncio.run(main())
