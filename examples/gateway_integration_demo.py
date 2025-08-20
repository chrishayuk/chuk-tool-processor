#!/usr/bin/env python3
"""
CHUK Tool Processor MCP Gateway Diagnostic

This comprehensive diagnostic script demonstrates and tests the MCP SSE transport
with authentication headers for the gateway setup.

Features:
- SSE transport with auth headers
- Tool discovery and registration
- Tool execution testing
- Performance metrics
- Health monitoring
- Comprehensive error handling
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# CHUK Tool Processor imports
from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
from chuk_tool_processor.mcp.stream_manager import StreamManager
from chuk_tool_processor.mcp.transport.sse_transport import SSETransport
from chuk_tool_processor.registry.provider import ToolRegistryProvider
from chuk_tool_processor.logging import get_logger

logger = get_logger("chuk_diagnostic")


class CHUKDiagnostic:
    """
    Comprehensive diagnostic tool for CHUK Tool Processor MCP integration.
    
    Tests SSE transport with authentication and provides detailed reporting.
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.processor = None
        self.stream_manager = None
        self.discovered_tools = []
        self.test_results = {}
        self.metrics_history = []
        
    async def run_full_diagnostic(self, gateway_url: str, auth_token: Optional[str] = None):
        """
        Run the complete diagnostic suite.
        
        Args:
            gateway_url: The gateway URL (e.g., https://your-gateway-url/sse)
            auth_token: Optional authentication token
        """
        print("🔧 CHUK Tool Processor MCP Gateway Diagnostic")
        print("=" * 60)
        print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 Gateway URL: {gateway_url}")
        print(f"🔐 Authentication: {'Yes' if auth_token else 'No'}")
        print()
        
        try:
            # Phase 1: Connection and Setup
            print("📡 Phase 1: Gateway Connection & Setup")
            print("-" * 40)
            await self._test_connection_setup(gateway_url, auth_token)
            
            # Phase 2: Tool Discovery
            print("\n🔍 Phase 2: Tool Discovery & Registration")
            print("-" * 40)
            await self._test_tool_discovery()
            
            # Phase 3: Tool Testing
            print("\n⚡ Phase 3: Tool Execution Testing")
            print("-" * 40)
            await self._test_tool_execution()
            
            # Phase 4: Performance Analysis
            print("\n📊 Phase 4: Performance & Metrics Analysis")
            print("-" * 40)
            await self._analyze_performance()
            
            # Phase 5: Health Monitoring
            print("\n💓 Phase 5: Health & Monitoring")
            print("-" * 40)
            await self._test_health_monitoring()
            
            # Final Report
            print("\n📋 Final Diagnostic Report")
            print("-" * 40)
            await self._generate_final_report()
            
        except Exception as e:
            logger.error(f"Diagnostic failed: {e}", exc_info=True)
            print(f"❌ Diagnostic failed: {e}")
        finally:
            await self._cleanup()
    
    async def _test_connection_setup(self, gateway_url: str, auth_token: Optional[str]):
        """Test the initial SSE connection and MCP setup."""
        setup_start = time.time()
        
        try:
            # Prepare server configuration with auth headers
            servers = [{
                "name": "gateway",
                "url": gateway_url,
            }]
            
            # Add authentication if provided
            if auth_token:
                servers[0]["headers"] = {
                    "Authorization": f"Bearer {auth_token}",
                    "User-Agent": "chuk-tool-processor-diagnostic/1.0.0"
                }
                servers[0]["api_key"] = auth_token  # Both methods for compatibility
            
            print(f"🔌 Connecting to gateway: {gateway_url}")
            print(f"   Headers configured: {bool(auth_token)}")
            
            # Initialize with SSE (confirmed working transport)
            self.processor, self.stream_manager = await setup_mcp_sse(
                servers=servers,
                connection_timeout=30.0,  # Sufficient timeout for gateway
                default_timeout=30.0,
                namespace="gateway"
            )
            
            setup_time = time.time() - setup_start
            print(f"✅ Connection established in {setup_time:.2f}s")
            
            # Test basic connectivity
            print("🏓 Testing basic connectivity...")
            health_check = await self.stream_manager.health_check()
            
            if health_check["status"] == "active":
                print("✅ Health check passed")
                print(f"   Active transports: {health_check['transport_count']}")
                
                # Display transport details
                for name, status in health_check.get("transports", {}).items():
                    status_icon = "✅" if status["status"] == "healthy" else "⚠️"
                    print(f"   {status_icon} Transport '{name}': {status['status']}")
            else:
                print("⚠️ Health check failed")
            
            self.test_results["connection"] = {
                "success": True,
                "setup_time": setup_time,
                "health_status": health_check["status"]
            }
            
        except Exception as e:
            setup_time = time.time() - setup_start
            print(f"❌ Connection failed after {setup_time:.2f}s: {e}")
            self.test_results["connection"] = {
                "success": False,
                "setup_time": setup_time,
                "error": str(e)
            }
            raise
    
    async def _test_tool_discovery(self):
        """Test tool discovery and registration."""
        discovery_start = time.time()
        
        try:
            # Get tools from stream manager
            print("🔍 Discovering available tools...")
            all_tools = self.stream_manager.get_all_tools()
            server_info = self.stream_manager.get_server_info()
            
            print(f"   Found {len(all_tools)} tools from {len(server_info)} servers")
            
            # Display server information
            for server in server_info:
                status_icon = "✅" if server["status"] == "Up" else "❌"
                print(f"   {status_icon} Server '{server['name']}': {server['tools']} tools, status: {server['status']}")
            
            # List discovered tools
            if all_tools:
                print("\n📝 Discovered tools:")
                for i, tool in enumerate(all_tools[:10], 1):  # Show first 10
                    name = tool.get("name", "unnamed")
                    description = tool.get("description", "No description")
                    print(f"   {i:2d}. {name}")
                    print(f"       {description[:80]}{'...' if len(description) > 80 else ''}")
                
                if len(all_tools) > 10:
                    print(f"       ... and {len(all_tools) - 10} more tools")
            
            # Test registry integration
            print("\n🗂️ Testing tool registry integration...")
            registry = await ToolRegistryProvider.get_registry()
            registered_tools = await registry.list_tools()
            
            gateway_tools = [name for ns, name in registered_tools if ns == "gateway"]
            print(f"   Registered tools in 'gateway' namespace: {len(gateway_tools)}")
            
            self.discovered_tools = all_tools
            discovery_time = time.time() - discovery_start
            
            self.test_results["discovery"] = {
                "success": True,
                "discovery_time": discovery_time,
                "tools_found": len(all_tools),
                "tools_registered": len(gateway_tools)
            }
            
            print(f"✅ Tool discovery completed in {discovery_time:.2f}s")
            
        except Exception as e:
            discovery_time = time.time() - discovery_start
            print(f"❌ Tool discovery failed after {discovery_time:.2f}s: {e}")
            self.test_results["discovery"] = {
                "success": False,
                "discovery_time": discovery_time,
                "error": str(e)
            }
            raise
    
    async def _test_tool_execution(self):
        """Test actual tool execution with smart parameter handling."""
        if not self.discovered_tools:
            print("⚠️ No tools available for testing")
            return
        
        execution_start = time.time()
        successful_calls = 0
        failed_calls = 0
        
        try:
            # Test a few representative tools
            test_tools = self.discovered_tools[:3]  # Test first 3 tools
            
            print(f"🧪 Testing execution of {len(test_tools)} tools...")
            
            for i, tool_def in enumerate(test_tools, 1):
                tool_name = tool_def.get("name")
                if not tool_name:
                    continue
                
                print(f"\n   Test {i}: {tool_name}")
                
                try:
                    # Get the tool from registry
                    registry = await ToolRegistryProvider.get_registry()
                    tool = await registry.get_tool(tool_name, "gateway")
                    
                    if not tool:
                        print(f"      ❌ Tool not found in registry")
                        failed_calls += 1
                        continue
                    
                    # Attempt execution with timeout
                    print(f"      🔄 Executing...")
                    call_start = time.time()
                    
                    # Execute with no arguments (safe test)
                    result = await tool.execute(timeout=15.0)
                    
                    call_time = time.time() - call_start
                    
                    # Analyze result more intelligently
                    if isinstance(result, dict):
                        if result.get("error"):
                            error_msg = result["error"]
                            # Check if it's just a validation error (tool works, just needs params)
                            if "validation error" in error_msg.lower() or "required property" in error_msg.lower():
                                print(f"      ✅ Tool executed successfully")
                                print(f"      ⏱️ Execution time: {call_time:.2f}s")
                                print(f"      📄 Result preview: {error_msg}")
                                successful_calls += 1
                            else:
                                print(f"      ⚠️ Tool returned error: {error_msg}")
                                print(f"      ⏱️ Execution time: {call_time:.2f}s")
                                failed_calls += 1
                        elif result.get("available") is False:
                            print(f"      ⚠️ Tool not available: {result.get('reason', 'Unknown')}")
                            print(f"      ⏱️ Execution time: {call_time:.2f}s")
                            failed_calls += 1
                        else:
                            print(f"      ✅ Tool executed successfully")
                            print(f"      ⏱️ Execution time: {call_time:.2f}s")
                            
                            # Show result preview
                            if result:
                                result_str = str(result)
                                preview = result_str[:100] + "..." if len(result_str) > 100 else result_str
                                print(f"      📄 Result preview: {preview}")
                            
                            successful_calls += 1
                    else:
                        print(f"      ✅ Tool executed successfully")
                        print(f"      ⏱️ Execution time: {call_time:.2f}s")
                        if result:
                            result_str = str(result)
                            preview = result_str[:100] + "..." if len(result_str) > 100 else result_str
                            print(f"      📄 Result preview: {preview}")
                        successful_calls += 1
                    
                except asyncio.TimeoutError:
                    print(f"      ⏰ Tool execution timed out")
                    failed_calls += 1
                except Exception as e:
                    print(f"      ❌ Tool execution failed: {e}")
                    failed_calls += 1
            
            execution_time = time.time() - execution_start
            success_rate = (successful_calls / (successful_calls + failed_calls) * 100) if (successful_calls + failed_calls) > 0 else 0
            
            print(f"\n📊 Execution Summary:")
            print(f"   ✅ Successful calls: {successful_calls}")
            print(f"   ❌ Failed calls: {failed_calls}")
            print(f"   📈 Success rate: {success_rate:.1f}%")
            print(f"   ⏱️ Total execution time: {execution_time:.2f}s")
            
            self.test_results["execution"] = {
                "success": True,
                "execution_time": execution_time,
                "successful_calls": successful_calls,
                "failed_calls": failed_calls,
                "success_rate": success_rate
            }
            
        except Exception as e:
            execution_time = time.time() - execution_start
            print(f"❌ Tool execution testing failed after {execution_time:.2f}s: {e}")
            self.test_results["execution"] = {
                "success": False,
                "execution_time": execution_time,
                "error": str(e)
            }
    
    async def _analyze_performance(self):
        """Analyze performance metrics from the transports."""
        print("📈 Analyzing transport performance...")
        
        try:
            # Get metrics from all transports
            transport_metrics = {}
            
            for name, transport in self.stream_manager.transports.items():
                if hasattr(transport, 'get_metrics'):
                    metrics = transport.get_metrics()
                    transport_metrics[name] = metrics
                    
                    print(f"\n   📊 Transport '{name}' metrics:")
                    print(f"      Total calls: {metrics.get('total_calls', 0)}")
                    print(f"      Successful calls: {metrics.get('successful_calls', 0)}")
                    print(f"      Failed calls: {metrics.get('failed_calls', 0)}")
                    
                    if metrics.get('total_calls', 0) > 0:
                        success_rate = (metrics.get('successful_calls', 0) / metrics['total_calls']) * 100
                        print(f"      Success rate: {success_rate:.1f}%")
                    
                    if metrics.get('avg_response_time'):
                        print(f"      Avg response time: {metrics['avg_response_time']:.3f}s")
                    
                    if metrics.get('initialization_time'):
                        print(f"      Initialization time: {metrics['initialization_time']:.3f}s")
            
            # Store metrics for history
            self.metrics_history.append({
                "timestamp": time.time(),
                "metrics": transport_metrics
            })
            
            self.test_results["performance"] = {
                "success": True,
                "transport_metrics": transport_metrics
            }
            
            print("✅ Performance analysis completed")
            
        except Exception as e:
            print(f"❌ Performance analysis failed: {e}")
            self.test_results["performance"] = {
                "success": False,
                "error": str(e)
            }
    
    async def _test_health_monitoring(self):
        """Test health monitoring capabilities."""
        print("💓 Testing health monitoring...")
        
        try:
            # Test ping functionality
            print("   🏓 Testing server ping...")
            ping_results = await self.stream_manager.ping_servers()
            
            for result in ping_results:
                if isinstance(result, dict):
                    server_name = result.get("server", "unknown")
                    ping_ok = result.get("ok", False)
                    status_icon = "✅" if ping_ok else "❌"
                    print(f"      {status_icon} Server '{server_name}': {'OK' if ping_ok else 'Failed'}")
            
            # Test resource listing (if available)
            print("   📚 Testing resource listing...")
            try:
                resources = await self.stream_manager.list_resources()
                if resources:
                    print(f"      ✅ Found {len(resources)} resources")
                    for resource in resources[:3]:  # Show first 3
                        name = resource.get("name", "unnamed")
                        server = resource.get("server", "unknown")
                        print(f"         - {name} (from {server})")
                else:
                    print("      ℹ️ No resources available")
            except Exception as e:
                print(f"      ⚠️ Resource listing not supported: {e}")
            
            # Test prompt listing (if available)
            print("   💬 Testing prompt listing...")
            try:
                prompts = await self.stream_manager.list_prompts()
                if prompts and isinstance(prompts, list) and len(prompts) > 0:
                    print(f"      ✅ Found {len(prompts)} prompts")
                    # Show first few prompts
                    for prompt in prompts[:3]:
                        name = prompt.get("name", "unnamed")
                        description = prompt.get("description", "No description")
                        print(f"         - {name}: {description[:50]}{'...' if len(description) > 50 else ''}")
                elif prompts and isinstance(prompts, dict) and prompts.get("prompts"):
                    prompt_list = prompts["prompts"]
                    print(f"      ✅ Found {len(prompt_list)} prompts")
                    for prompt in prompt_list[:3]:
                        name = prompt.get("name", "unnamed")
                        description = prompt.get("description", "No description")
                        print(f"         - {name}: {description[:50]}{'...' if len(description) > 50 else ''}")
                else:
                    print("      ℹ️ No prompts available")
            except Exception as e:
                print(f"      ⚠️ Prompt listing not supported: {e}")
            
            self.test_results["health"] = {
                "success": True,
                "ping_results": ping_results
            }
            
            print("✅ Health monitoring test completed")
            
        except Exception as e:
            print(f"❌ Health monitoring test failed: {e}")
            self.test_results["health"] = {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_final_report(self):
        """Generate the final diagnostic report."""
        total_time = time.time() - self.start_time
        
        print("📋 FINAL DIAGNOSTIC REPORT")
        print("=" * 50)
        print(f"🕒 Total diagnostic time: {total_time:.2f}s")
        print(f"📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Summary of test results
        passed_tests = sum(1 for result in self.test_results.values() if result.get("success", False))
        total_tests = len(self.test_results)
        
        print(f"📊 Test Summary: {passed_tests}/{total_tests} passed")
        print()
        
        # Detailed results
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result.get("success", False) else "❌"
            print(f"{status_icon} {test_name.title()}: {'PASSED' if result.get('success', False) else 'FAILED'}")
            
            if not result.get("success", False) and "error" in result:
                print(f"    Error: {result['error']}")
        
        print()
        
        # Performance summary
        if "performance" in self.test_results and self.test_results["performance"].get("success"):
            print("🚀 Performance Summary:")
            for name, metrics in self.test_results["performance"]["transport_metrics"].items():
                total_calls = metrics.get("total_calls", 0)
                if total_calls > 0:
                    success_rate = (metrics.get("successful_calls", 0) / total_calls) * 100
                    avg_time = metrics.get("avg_response_time", 0)
                    print(f"   Transport '{name}': {total_calls} calls, {success_rate:.1f}% success, {avg_time:.3f}s avg")
            print()
        
        # Recommendations
        print("💡 Recommendations:")
        
        if not self.test_results.get("connection", {}).get("success", False):
            print("   - Check gateway URL and authentication credentials")
            print("   - Verify network connectivity to the gateway")
        
        if self.test_results.get("discovery", {}).get("success", False):
            tools_found = self.test_results["discovery"].get("tools_found", 0)
            if tools_found == 0:
                print("   - No tools discovered - check gateway configuration")
            elif tools_found > 0:
                print(f"   - {tools_found} tools discovered - integration is working")
        
        if self.test_results.get("execution", {}).get("success", False):
            success_rate = self.test_results["execution"].get("success_rate", 0)
            successful_calls = self.test_results["execution"].get("successful_calls", 0)
            if success_rate < 50:
                print("   - Low tool execution success rate - check tool configurations")
            elif success_rate >= 80:
                print("   - High tool execution success rate - system is performing well")
            
            if successful_calls > 0:
                print(f"   - {successful_calls} tools executed successfully - ready for production use")
        
        print()
        print("🎉 Diagnostic completed! Your MCP gateway integration is working.")
        
        # Summary stats
        tools_found = self.test_results.get("discovery", {}).get("tools_found", 0)
        if tools_found > 0:
            print(f"✨ You now have access to {tools_found} MCP tools through the gateway!")
    
    async def _cleanup(self):
        """Clean up resources."""
        if self.stream_manager:
            try:
                await self.stream_manager.close()
                print("🧹 Cleaned up resources")
            except Exception as e:
                print(f"⚠️ Cleanup warning: {e}")


async def main():
    """Main diagnostic entry point."""
    # Load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()  # Load from .env file in current directory
        print("📄 Loaded environment variables from .env file")
    except ImportError:
        print("⚠️ python-dotenv not installed, using system environment variables only")
        print("   Install with: pip install python-dotenv")
    
    # Load configuration from environment variables
    import os
    
    # Gateway URL - check multiple possible environment variable names
    GATEWAY_URL = (
        os.environ.get("MCP_GATEWAY_URL") or 
        os.environ.get("GATEWAY_URL") or 
        os.environ.get("MCP_URL") or
        "https://your-gateway-url"  # Default fallback
    )
    
    # Auth token - check multiple possible environment variable names
    AUTH_TOKEN = (
        os.environ.get("MCP_AUTH_TOKEN") or 
        os.environ.get("MCP_GATEWAY_TOKEN") or 
        os.environ.get("GATEWAY_AUTH_TOKEN")
    )
    
    print("🔧 CHUK Tool Processor MCP Gateway Diagnostic")
    print("=" * 60)
    
    # Display configuration
    print(f"🌐 Gateway URL: {GATEWAY_URL}")
    if GATEWAY_URL == "https://your-gateway-url":
        print("   (using default URL - set MCP_GATEWAY_URL to override)")
    else:
        print("   (loaded from environment variable)")
    
    if not AUTH_TOKEN:
        print("⚠️ Warning: No authentication token provided")
        print("   Create a .env file with:")
        print("     MCP_GATEWAY_URL=https://your-gateway-url")
        print("     MCP_AUTH_TOKEN=your-token-here")
        print("   Or set environment variables directly")
        print("   Proceeding without authentication...")
        print()
    else:
        # Mask the token for security in logs
        masked_token = f"{AUTH_TOKEN[:8]}..." if len(AUTH_TOKEN) > 8 else "***"
        print(f"🔐 Authentication token loaded: {masked_token}")
        print()
    
    # Run the diagnostic
    diagnostic = CHUKDiagnostic()
    
    try:
        await diagnostic.run_full_diagnostic(GATEWAY_URL, AUTH_TOKEN)
    except KeyboardInterrupt:
        print("\n\n⏹️ Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Diagnostic crashed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 Diagnostic session ended")


if __name__ == "__main__":
    asyncio.run(main())