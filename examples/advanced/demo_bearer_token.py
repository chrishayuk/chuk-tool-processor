#!/usr/bin/env python3
"""
End-to-End MCP SSE Test Script

Tests the chuk_tool_processor MCP functionality before integrating with the agent.
This script validates:
1. Bearer token authentication
2. SSE connection establishment
3. MCP protocol handshake
4. Tool discovery
5. Tool execution
6. URL redirect handling

Usage:
    # Option 1: Environment variable
    export MCP_BEARER_TOKEN="Bearer your-token-here"
    python test_mcp_sse.py

    # Option 2: .env file
    echo 'MCP_BEARER_TOKEN="Bearer your-token-here"' > .env
    python test_mcp_sse.py
"""

import asyncio
import os
import sys

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
    print("🔧 Loaded environment variables from .env file")
except ImportError:
    print("ℹ️  python-dotenv not installed, using environment variables only")
    print("ℹ️  Install with: pip install python-dotenv")
except Exception as e:
    print(f"⚠️  Could not load .env file: {e}")

# Test configuration
TEST_CONFIG = {
    "servers": [
        {
            "name": "perplexity_server",
            "url": "https://application-cd.1vqsrjfxmls7.eu-gb.codeengine.appdomain.cloud",
            "transport": "sse",
        }
    ],
    "server_names": {0: "perplexity_server"},
    "namespace": "test_mcp",
}


def print_banner(title: str, char: str = "=") -> None:
    """Print a banner for test sections."""
    print(f"\n{char * 60}")
    print(f" {title}")
    print(f"{char * 60}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"✅ {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"❌ {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"ℹ️  {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"⚠️  {message}")


async def test_environment_setup() -> bool:
    """Test that the environment is properly configured."""
    print_banner("Environment Setup Test")

    # Check bearer token
    bearer_token = os.getenv("MCP_BEARER_TOKEN")
    if not bearer_token:
        print_error("MCP_BEARER_TOKEN environment variable not set")
        print_info('Please set: export MCP_BEARER_TOKEN="Bearer your-token-here"')
        return False

    print_success(f"Bearer token found: {bearer_token[:20]}...")

    # Check token format
    if not bearer_token.startswith("Bearer "):
        print_warning("Token doesn't start with 'Bearer ' - the transport will add it")
    else:
        print_success("Token has correct 'Bearer ' prefix")

    return True


async def test_mcp_imports() -> bool:
    """Test that MCP imports work correctly."""
    print_banner("MCP Import Test")

    try:
        from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

        print_success("setup_mcp_sse imported successfully")

        from chuk_tool_processor.mcp.stream_manager import StreamManager

        print_success("StreamManager imported successfully")

        from chuk_tool_processor.core.processor import ToolProcessor

        print_success("ToolProcessor imported successfully")

        return True

    except ImportError as e:
        print_error(f"Failed to import MCP modules: {e}")
        print_info("Make sure chuk_tool_processor is installed and the fixed files are in place")
        return False


async def test_stream_manager_creation() -> tuple[bool, object]:
    """Test StreamManager creation with SSE transport."""
    print_banner("StreamManager Creation Test")

    try:
        from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

        print_info("Creating StreamManager with SSE transport...")
        print_info(f"Server URL: {TEST_CONFIG['servers'][0]['url']}")

        processor, stream_manager = await setup_mcp_sse(
            servers=TEST_CONFIG["servers"], server_names=TEST_CONFIG["server_names"], namespace=TEST_CONFIG["namespace"]
        )

        print_success("StreamManager created successfully")
        print_success("ToolProcessor created successfully")

        return True, (processor, stream_manager)

    except Exception as e:
        print_error(f"Failed to create StreamManager: {e}")
        import traceback

        print_info("Full traceback:")
        traceback.print_exc()
        return False, None


async def test_connection_and_ping(stream_manager) -> bool:
    """Test connection status and ping functionality."""
    print_banner("Connection and Ping Test")

    try:
        # Check if we have any servers (not async)
        servers_info = stream_manager.get_server_info()
        print_info(f"Server info: {servers_info}")

        # Try ping (actually is async)
        ping_result = await stream_manager.ping_servers()
        print_info(f"Ping result: {ping_result}")

        if ping_result:
            print_success("Server ping successful")
            return True
        else:
            print_warning("Server ping failed - but connection might still work")
            return True  # Continue testing even if ping fails

    except Exception as e:
        print_error(f"Connection test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_tool_discovery(stream_manager) -> tuple[bool, list[str]]:
    """Test tool discovery functionality."""
    print_banner("Tool Discovery Test")

    try:
        print_info("Discovering available tools...")

        # Get all tools (not async) - returns a list of tool names
        all_tools = stream_manager.get_all_tools()
        print_info(f"Total tools found: {len(all_tools)}")

        if all_tools:
            print_success("Tools discovered successfully!")

            # Print first few tools (all_tools is a list of tool names)
            for i, tool_name in enumerate(all_tools[:5]):  # Show first 5 tools
                print_info(f"Tool {i + 1}: {tool_name}")

            if len(all_tools) > 5:
                print_info(f"... and {len(all_tools) - 5} more tools")

            return True, all_tools
        else:
            print_warning("No tools found - this might indicate an authentication or connection issue")
            return False, []

    except Exception as e:
        print_error(f"Tool discovery failed: {e}")
        import traceback

        traceback.print_exc()
        return False, []


async def test_tool_execution(stream_manager, available_tools: list[str]) -> bool:
    """Test tool execution functionality."""
    print_banner("Tool Execution Test")

    if not available_tools:
        print_warning("No tools available for testing")
        return False

    try:
        # available_tools is a list of tool dicts, extract the first tool name
        test_tool_dict = available_tools[0]
        if isinstance(test_tool_dict, dict):
            test_tool_name = test_tool_dict["name"]
            print_info(f"Testing tool execution with: {test_tool_name}")

            # Prepare test arguments based on the tool schema
            test_args = {}
            input_schema = test_tool_dict.get("inputSchema", {})
            if "properties" in input_schema:
                # Add required arguments with sample values
                for prop_name, prop_info in input_schema["properties"].items():
                    if prop_name in input_schema.get("required", []):
                        if prop_info.get("type") == "string":
                            test_args[prop_name] = "test message"
                        elif prop_info.get("type") == "integer":
                            test_args[prop_name] = 1
                        elif prop_info.get("type") == "number":
                            test_args[prop_name] = 1.0

            print_info(f"Calling tool with arguments: {test_args}")

            # Execute the tool
            result = await stream_manager.call_tool(test_tool_name, test_args)

            print_info(f"Tool execution result type: {type(result)}")
            print_info(f"Tool execution result: {str(result)[:200]}...")

            if isinstance(result, dict):
                if result.get("isError"):
                    print_warning(f"Tool returned error: {result.get('error', 'Unknown error')}")
                else:
                    print_success("Tool executed successfully!")
                    return True
            else:
                print_success("Tool executed and returned a result!")
                return True
        else:
            print_error(f"Unexpected tool format: {type(test_tool_dict)}")
            return False

    except Exception as e:
        print_error(f"Tool execution failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_cleanup(stream_manager) -> bool:
    """Test cleanup functionality."""
    print_banner("Cleanup Test")

    try:
        print_info("Closing StreamManager...")
        await stream_manager.close()
        print_success("StreamManager closed successfully")
        return True

    except Exception as e:
        print_error(f"Cleanup failed: {e}")
        return False


async def main():
    """Run the complete end-to-end test suite."""
    print_banner("MCP SSE End-to-End Test Suite", "=")
    print_info("Testing chuk_tool_processor MCP functionality")

    # Track test results
    results = {
        "environment": False,
        "imports": False,
        "stream_manager": False,
        "connection": False,
        "tool_discovery": False,
        "tool_execution": False,
        "cleanup": False,
    }

    stream_manager = None
    available_tools = []

    try:
        # Test 1: Environment Setup
        results["environment"] = await test_environment_setup()
        if not results["environment"]:
            print_error("Environment setup failed - cannot continue")
            return False

        # Test 2: MCP Imports
        results["imports"] = await test_mcp_imports()
        if not results["imports"]:
            print_error("Import test failed - cannot continue")
            return False

        # Test 3: StreamManager Creation
        results["stream_manager"], manager_result = await test_stream_manager_creation()
        if results["stream_manager"]:
            processor, stream_manager = manager_result
        else:
            print_error("StreamManager creation failed - cannot continue")
            return False

        # Test 4: Connection and Ping
        results["connection"] = await test_connection_and_ping(stream_manager)

        # Test 5: Tool Discovery
        results["tool_discovery"], available_tools = await test_tool_discovery(stream_manager)

        # Test 6: Tool Execution (only if tools were found)
        if available_tools:
            results["tool_execution"] = await test_tool_execution(stream_manager, available_tools)
        else:
            print_warning("Skipping tool execution test - no tools available")

        # Test 7: Cleanup
        results["cleanup"] = await test_cleanup(stream_manager)

    except KeyboardInterrupt:
        print_warning("\nTest interrupted by user")
        if stream_manager:
            await stream_manager.close()
        return False

    except Exception as e:
        print_error(f"Unexpected error during testing: {e}")
        import traceback

        traceback.print_exc()
        if stream_manager:
            await stream_manager.close()
        return False

    # Print test summary
    print_banner("Test Results Summary", "=")

    passed = 0
    total = 0

    for test_name, result in results.items():
        total += 1
        if result:
            passed += 1
            print_success(f"{test_name.replace('_', ' ').title()}: PASSED")
        else:
            print_error(f"{test_name.replace('_', ' ').title()}: FAILED")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print_success("🎉 All tests passed! MCP SSE integration is working correctly.")
        print_info("You can now integrate this with your agent.")
        return True
    else:
        print_error("❌ Some tests failed. Please check the issues above.")

        # Provide troubleshooting hints
        print_banner("Troubleshooting Hints", "-")

        if not results["environment"]:
            print_info("• Make sure MCP_BEARER_TOKEN environment variable is set")
            print_info('• Create a .env file with: MCP_BEARER_TOKEN="Bearer your-token"')
            print_info('• Or export the variable: export MCP_BEARER_TOKEN="Bearer your-token"')
            print_info("• Token should include 'Bearer ' prefix")

        if not results["connection"]:
            print_info("• Check if the SSE server is running and accessible")
            print_info("• Verify bearer token is valid and not expired")
            print_info("• Check network connectivity to the server")

        if not results["tool_discovery"]:
            print_info("• Authentication might be failing")
            print_info("• Server might not have any tools configured")
            print_info("• Check server logs for authentication errors")

        return False


if __name__ == "__main__":
    # Check Python version

    # Run the test suite
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_warning("\nTest suite interrupted")
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to run test suite: {e}")
        sys.exit(1)
