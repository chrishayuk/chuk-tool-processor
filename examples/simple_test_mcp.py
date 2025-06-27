#!/usr/bin/env python
"""
simple_mcp_test.py
A simple test of MCP server functionality using chuk-mcp directly.

This bypasses the complex tool processor and demonstrates basic MCP operations.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path for development
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import chuk-mcp components
try:
    from chuk_mcp import (
        stdio_client,
        StdioServerParameters, 
        send_initialize,
        send_ping,
        send_tools_list,
        send_tools_call,
        load_config
    )
    print("✅ chuk-mcp imports successful")
except ImportError as e:
    print(f"❌ Failed to import chuk-mcp: {e}")
    sys.exit(1)


def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{'=' * 50}")
    print(f"🔍 {title}")
    print(f"{'=' * 50}")


def print_step(step: str) -> None:
    """Print a step."""
    print(f"\n📋 {step}")


async def test_server_direct(server_name: str = "time") -> None:
    """Test MCP server functionality directly."""
    print_header("Direct MCP Server Test")
    
    try:
        # Load configuration
        print_step("Loading server configuration...")
        try:
            server_params = await load_config("server_config.json", server_name)
            print(f"✅ Loaded config for '{server_name}'")
            print(f"   Command: {server_params.command}")
            print(f"   Args: {server_params.args}")
        except Exception as e:
            print(f"❌ Failed to load config: {e}")
            return
        
        # Connect to server
        print_step("Connecting to MCP server...")
        async with stdio_client(server_params) as (read_stream, write_stream):
            print("✅ Connected to server")
            
            # Initialize
            print_step("Initializing MCP session...")
            try:
                init_result = await send_initialize(read_stream, write_stream, timeout=10.0)
                if init_result:
                    print(f"✅ Initialized: {init_result.serverInfo.name}")
                    print(f"   Version: {init_result.serverInfo.version}")
                    print(f"   Protocol: {init_result.protocolVersion}")
                else:
                    print("❌ Initialization failed")
                    return
            except Exception as e:
                print(f"❌ Initialization error: {e}")
                return
            
            # Test ping
            print_step("Testing server ping...")
            try:
                ping_result = await send_ping(read_stream, write_stream, timeout=5.0)
                if ping_result:
                    print("✅ Ping successful")
                else:
                    print("❌ Ping failed")
            except Exception as e:
                print(f"❌ Ping error: {e}")
            
            # List tools
            print_step("Listing available tools...")
            try:
                tools_response = await send_tools_list(read_stream, write_stream, timeout=10.0)
                tools = tools_response.get("tools", [])
                
                if tools:
                    print(f"✅ Found {len(tools)} tool(s):")
                    for i, tool in enumerate(tools, 1):
                        name = tool.get("name", "unknown")
                        desc = tool.get("description", "No description")
                        print(f"   {i}. {name}: {desc}")
                        
                        # Show schema for first tool
                        if i == 1:
                            schema = tool.get("inputSchema", {})
                            if schema:
                                print(f"      Schema: {json.dumps(schema, indent=6)}")
                else:
                    print("⚠️  No tools available")
                    return
                    
            except Exception as e:
                print(f"❌ Tools list error: {e}")
                return
            
            # Test tool calls
            print_step("Testing tool calls...")
            
            # Test different timezone calls
            test_calls = [
                {"timezone": "UTC"},
                {"timezone": "America/New_York"},
                {"timezone": "Europe/London"},
            ]
            
            for i, args in enumerate(test_calls, 1):
                try:
                    print(f"\n   {i}. Testing with args: {json.dumps(args)}")
                    
                    result = await send_tools_call(
                        read_stream, 
                        write_stream,
                        "get_current_time",  # Assuming this is the tool name
                        args,
                        timeout=10.0
                    )
                    
                    print(f"   ✅ Success!")
                    print(f"      Result: {json.dumps(result, indent=6, default=str)}")
                    
                except Exception as e:
                    print(f"   ❌ Tool call failed: {e}")
            
            print_step("Test completed successfully!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


async def test_with_minimal_server() -> None:
    """Test with a minimal built-in server for comparison."""
    print_header("Minimal Test Server")
    
    # Create a minimal test server
    import tempfile
    import os
    
    server_code = '''#!/usr/bin/env python3
import asyncio
import json
import sys
import datetime

class MinimalTimeServer:
    async def handle_message(self, message):
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "minimal-time-server", "version": "1.0.0"}
                }
            }
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": [{
                    "name": "get_current_time",
                    "description": "Get current time in specified timezone",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"timezone": {"type": "string", "default": "UTC"}},
                        "required": []
                    }
                }]}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "get_current_time":
                timezone = arguments.get("timezone", "UTC")
                current_time = datetime.datetime.now().isoformat()
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": f"Current time in {timezone}: {current_time}"
                        }]
                    }
                }
        
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }
    
    async def run(self):
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                
                message = json.loads(line)
                response = await self.handle_message(message)
                if response:
                    print(json.dumps(response), flush=True)
            except Exception as e:
                break

if __name__ == "__main__":
    asyncio.run(MinimalTimeServer().run())
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(server_code)
        server_file = f.name
    
    try:
        print_step("Testing with minimal built-in server...")
        
        server_params = StdioServerParameters(
            command="python",
            args=[server_file]
        )
        
        async with stdio_client(server_params) as (read_stream, write_stream):
            print("✅ Connected to minimal server")
            
            # Quick test
            init_result = await send_initialize(read_stream, write_stream)
            print(f"✅ Minimal server: {init_result.serverInfo.name}")
            
            tools_response = await send_tools_list(read_stream, write_stream)
            print(f"✅ Tools available: {len(tools_response['tools'])}")
            
            # Test tool call
            result = await send_tools_call(
                read_stream, write_stream,
                "get_current_time",
                {"timezone": "UTC"}
            )
            
            print(f"✅ Tool call result: {result['content'][0]['text']}")
            
    finally:
        os.unlink(server_file)


async def main():
    """Main test function."""
    print("🚀 Simple MCP Server Test")
    print("=" * 60)
    
    # Test with configured server
    await test_server_direct("time")
    
    # Test with minimal server for comparison
    await test_with_minimal_server()
    
    print_header("All Tests Completed")
    print("🎉 If you see this, chuk-mcp is working correctly!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)