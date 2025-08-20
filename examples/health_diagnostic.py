#!/usr/bin/env python3
"""
CHUK Tool Processor Level Diagnostic - Full Stack Health Test

This diagnostic tests the complete MCP stack from CHUK Tool Processor down to 
the transport layer to identify where "unhealthy connection" issues originate.

FOCUS: Reproduce the exact same conditions as mcp_cli to find the root cause
of tools reporting "Tool 'X' is not available (unhealthy connection)".

Usage:
    python chuk_processor_diagnostic.py

Environment Variables Required:
    MCP_GATEWAY_URL - SSE endpoint URL  
    MCP_AUTH_TOKEN - Authentication token
"""

import asyncio
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(verbose=True)
    print("✅ Loaded environment variables from .env file")
except ImportError:
    print("⚠️  python-dotenv not available, using system environment")

import os

# Configuration
GATEWAY_URL = (
    os.environ.get("MCP_GATEWAY_URL") or 
    os.environ.get("GATEWAY_URL") or 
    os.environ.get("MCP_URL")
)

AUTH_TOKEN = (
    os.environ.get("MCP_AUTH_TOKEN") or 
    os.environ.get("MCP_GATEWAY_TOKEN") or 
    os.environ.get("GATEWAY_AUTH_TOKEN")
)

if not GATEWAY_URL or not AUTH_TOKEN:
    print("❌ ERROR: Missing required environment variables!")
    print("Required: MCP_GATEWAY_URL and MCP_AUTH_TOKEN")
    sys.exit(1)

# CHUK Tool Processor imports
try:
    from chuk_tool_processor.core.processor import ToolProcessor
    from chuk_tool_processor.registry.provider import ToolRegistryProvider
    from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse
    from chuk_tool_processor.mcp.transport.sse_transport import SSETransport
    from chuk_tool_processor.mcp.stream_manager import StreamManager
    from chuk_tool_processor.mcp.mcp_tool import MCPTool
    from chuk_tool_processor.logging import get_logger
except ImportError as e:
    print(f"❌ CHUK Tool Processor import failed: {e}")
    sys.exit(1)

logger = get_logger("chuk_processor_diagnostic")


class CHUKProcessorDiagnostic:
    """
    Complete CHUK Tool Processor stack diagnostic to identify 
    the exact source of "unhealthy connection" issues.
    """
    
    def __init__(self):
        self.start_time = time.time()
        
        # Configuration - match MCP CLI setup exactly
        self.base_url = GATEWAY_URL.replace('/sse', '') if GATEWAY_URL.endswith('/sse') else GATEWAY_URL
        self.auth_token = AUTH_TOKEN
        
        self.servers = [{
            "name": "gateway",
            "url": self.base_url,
            "headers": {"Authorization": f"Bearer {self.auth_token}"}
        }]
        
        self.test_results = {}
        self.issues_found = []
        
        print(f"🎯 Target Gateway: {self.base_url}")
        print(f"🔐 Auth Token: {len(self.auth_token)} chars")
    
    async def run_full_stack_diagnostic(self):
        """Run complete diagnostic from ToolProcessor down to transport."""
        print("🔧 CHUK TOOL PROCESSOR FULL STACK DIAGNOSTIC")
        print("=" * 80)
        print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Testing: {self.base_url}")
        print()
        
        try:
            # Level 1: Raw Transport Test
            print("🌊 LEVEL 1: Raw SSE Transport Test")
            print("-" * 50)
            await self._test_raw_transport()
            
            # Level 2: StreamManager Test  
            print("\n📡 LEVEL 2: StreamManager Test")
            print("-" * 50)
            await self._test_stream_manager()
            
            # Level 3: MCP Tool Registration Test
            print("\n🔧 LEVEL 3: MCP Tool Registration Test") 
            print("-" * 50)
            await self._test_mcp_tool_registration()
            
            # Level 4: ToolProcessor Integration Test
            print("\n⚙️  LEVEL 4: ToolProcessor Integration Test")
            print("-" * 50)
            await self._test_tool_processor_integration()
            
            # Level 5: Tool Execution Test (reproduce exact issue)
            print("\n🎯 LEVEL 5: Tool Execution Test (Reproduce Issue)")
            print("-" * 50)
            await self._test_tool_execution_scenarios()
            
            # Root Cause Analysis
            print("\n🔍 ROOT CAUSE ANALYSIS")
            print("-" * 50)
            await self._analyze_root_cause()
            
        except Exception as e:
            print(f"❌ Diagnostic failed: {e}")
            traceback.print_exc()
            
        print(f"\n🏁 Diagnostic completed in {time.time() - self.start_time:.2f}s")
    
    async def _test_raw_transport(self):
        """Test raw SSE transport - baseline health check."""
        print("🌊 Testing raw SSE transport...")
        
        transport_result = {
            "creation_success": False,
            "initialization_success": False,
            "health_check": False,
            "ping_success": False,
            "tools_retrieved": 0,
            "initialization_time": 0.0,
            "ping_time": 0.0,
            "error": None
        }
        
        try:
            # Create transport with exact same config as diagnostic
            print("   🏗️  Creating SSE Transport...")
            transport = SSETransport(
                url=self.base_url,
                api_key=self.auth_token,
                connection_timeout=30.0,
                default_timeout=60.0,
                enable_metrics=True
            )
            transport_result["creation_success"] = True
            print("      ✅ Transport created")
            
            # Initialize
            print("   🚀 Initializing transport...")
            init_start = time.time()
            init_success = await transport.initialize()
            transport_result["initialization_time"] = time.time() - init_start
            transport_result["initialization_success"] = init_success
            
            if init_success:
                print(f"      ✅ Initialization successful ({transport_result['initialization_time']:.2f}s)")
                
                # Health check
                print("   💓 Checking transport health...")
                is_healthy = transport.is_connected()
                transport_result["health_check"] = is_healthy
                print(f"      {'✅' if is_healthy else '❌'} Health check: {is_healthy}")
                
                # Ping test
                print("   🏓 Testing ping...")
                ping_start = time.time()
                ping_success = await transport.send_ping()
                transport_result["ping_time"] = time.time() - ping_start
                transport_result["ping_success"] = ping_success
                print(f"      {'✅' if ping_success else '❌'} Ping: {ping_success} ({transport_result['ping_time']:.2f}s)")
                
                # Get tools
                print("   🔧 Retrieving tools...")
                tools = await transport.get_tools()
                transport_result["tools_retrieved"] = len(tools)
                print(f"      ✅ Retrieved {len(tools)} tools")
                
                # Show transport metrics
                metrics = transport.get_metrics()
                print(f"   📊 Transport metrics:")
                for key in ['consecutive_failures', 'max_consecutive_failures', 'is_connected']:
                    if key in metrics:
                        print(f"      {key}: {metrics[key]}")
                
                await transport.close()
            else:
                print(f"      ❌ Initialization failed")
                self.issues_found.append("Raw transport initialization failed")
                
        except Exception as e:
            transport_result["error"] = str(e)
            print(f"   ❌ Transport test failed: {e}")
            self.issues_found.append(f"Raw transport error: {e}")
        
        self.test_results["raw_transport"] = transport_result
    
    async def _test_stream_manager(self):
        """Test StreamManager - next level up."""
        print("📡 Testing StreamManager...")
        
        stream_manager_result = {
            "creation_success": False,
            "initialization_success": False,
            "tools_discovered": 0,
            "server_info": [],
            "health_checks": [],
            "initialization_time": 0.0,
            "error": None
        }
        
        try:
            print("   🏗️  Creating StreamManager...")
            init_start = time.time()
            
            # Use the same setup as mcp_cli would
            stream_manager = await StreamManager.create_with_sse(
                servers=self.servers,
                connection_timeout=30.0,
                default_timeout=60.0,
                initialization_timeout=120.0
            )
            
            stream_manager_result["initialization_time"] = time.time() - init_start
            stream_manager_result["creation_success"] = True
            stream_manager_result["initialization_success"] = True
            print(f"      ✅ StreamManager created ({stream_manager_result['initialization_time']:.2f}s)")
            
            # Get tools
            print("   🔧 Discovering tools...")
            tools = stream_manager.get_all_tools()
            stream_manager_result["tools_discovered"] = len(tools)
            print(f"      ✅ Discovered {len(tools)} tools")
            
            # Get server info
            print("   📊 Getting server info...")
            server_info = stream_manager.get_server_info()
            stream_manager_result["server_info"] = server_info
            for server in server_info:
                print(f"      Server: {server.get('name')} - {server.get('status')} - {server.get('tools', 0)} tools")
            
            # Test health of underlying transports
            print("   💓 Testing underlying transport health...")
            if hasattr(stream_manager, 'transports'):
                for name, transport in stream_manager.transports.items():
                    is_healthy = transport.is_connected() if hasattr(transport, 'is_connected') else 'unknown'
                    stream_manager_result["health_checks"].append({
                        "transport": name,
                        "healthy": is_healthy
                    })
                    print(f"      Transport {name}: {'✅' if is_healthy else '❌'} {is_healthy}")
            
            await stream_manager.close()
            
        except Exception as e:
            stream_manager_result["error"] = str(e)
            print(f"   ❌ StreamManager test failed: {e}")
            self.issues_found.append(f"StreamManager error: {e}")
        
        self.test_results["stream_manager"] = stream_manager_result
    
    async def _test_mcp_tool_registration(self):
        """Test MCP tool registration process."""
        print("🔧 Testing MCP tool registration...")
        
        registration_result = {
            "setup_success": False,
            "tools_registered": 0,
            "registry_tools": 0,
            "sample_tool_health": {},
            "processor_created": False,
            "setup_time": 0.0,
            "error": None
        }
        
        try:
            print("   🚀 Running setup_mcp_sse...")
            setup_start = time.time()
            
            # This is exactly what mcp_cli does
            processor, stream_manager = await setup_mcp_sse(
                servers=self.servers,
                connection_timeout=30.0,
                default_timeout=60.0,
                namespace="gateway"
            )
            
            registration_result["setup_time"] = time.time() - setup_start
            registration_result["setup_success"] = True
            registration_result["processor_created"] = processor is not None
            print(f"      ✅ Setup completed ({registration_result['setup_time']:.2f}s)")
            
            # Check registry
            print("   📋 Checking tool registry...")
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()
            gateway_tools = [(ns, name) for ns, name in all_tools if ns == "gateway"]
            registration_result["registry_tools"] = len(gateway_tools)
            print(f"      ✅ Found {len(gateway_tools)} tools in 'gateway' namespace")
            
            # Test a sample tool's health
            print("   🧪 Testing sample tool health...")
            if gateway_tools:
                sample_ns, sample_name = gateway_tools[0]
                print(f"      Testing: {sample_ns}.{sample_name}")
                
                try:
                    # Get the tool from registry
                    tool = await registry.get_tool(sample_name, sample_ns)
                    if tool and isinstance(tool, MCPTool):
                        # Test tool availability
                        is_available = tool.is_available()
                        stats = tool.get_stats()
                        
                        registration_result["sample_tool_health"] = {
                            "name": sample_name,
                            "available": is_available,
                            "stats": stats
                        }
                        
                        print(f"         Available: {'✅' if is_available else '❌'} {is_available}")
                        print(f"         State: {stats.get('state', 'unknown')}")
                        print(f"         Has StreamManager: {'✅' if stats.get('has_stream_manager') else '❌'}")
                        
                        if not is_available:
                            self.issues_found.append(f"Sample tool {sample_name} reports unavailable")
                            
                except Exception as e:
                    print(f"         ❌ Tool health check failed: {e}")
                    registration_result["sample_tool_health"]["error"] = str(e)
            
            await stream_manager.close()
            
        except Exception as e:
            registration_result["error"] = str(e)
            print(f"   ❌ Registration test failed: {e}")
            self.issues_found.append(f"Registration error: {e}")
        
        self.test_results["registration"] = registration_result
    
    async def _test_tool_processor_integration(self):
        """Test ToolProcessor integration."""
        print("⚙️  Testing ToolProcessor integration...")
        
        processor_result = {
            "setup_success": False,
            "tools_available": 0,
            "llm_tools_generated": 0,
            "name_mapping_count": 0,
            "sample_execution": {},
            "error": None
        }
        
        try:
            print("   🚀 Setting up ToolProcessor...")
            processor, stream_manager = await setup_mcp_sse(
                servers=self.servers,
                connection_timeout=30.0,
                default_timeout=60.0,
                namespace="gateway"
            )
            
            processor_result["setup_success"] = True
            print("      ✅ ToolProcessor setup successful")
            
            # Get available tools through processor
            print("   📋 Getting tools via ToolProcessor...")
            registry = await ToolRegistryProvider.get_registry()
            all_tools = await registry.list_tools()
            gateway_tools = [(ns, name) for ns, name in all_tools if ns == "gateway"]
            processor_result["tools_available"] = len(gateway_tools)
            print(f"      ✅ {len(gateway_tools)} tools available")
            
            # Test LLM tool generation (this is what mcp_cli uses)
            print("   🤖 Testing LLM tool generation...")
            try:
                # This mimics what ToolManager.get_adapted_tools_for_llm does
                registry = await ToolRegistryProvider.get_registry()
                
                llm_tools = []
                name_mapping = {}
                
                for ns, name in gateway_tools:
                    metadata = await registry.get_metadata(name, ns)
                    if metadata:
                        tool_def = {
                            "type": "function",
                            "function": {
                                "name": name,
                                "description": metadata.description or "",
                                "parameters": metadata.argument_schema or {}
                            }
                        }
                        llm_tools.append(tool_def)
                        name_mapping[name] = name
                
                processor_result["llm_tools_generated"] = len(llm_tools)
                processor_result["name_mapping_count"] = len(name_mapping)
                print(f"      ✅ Generated {len(llm_tools)} LLM tools")
                print(f"      ✅ Name mapping: {len(name_mapping)} entries")
                
            except Exception as e:
                print(f"      ❌ LLM tool generation failed: {e}")
                processor_result["llm_generation_error"] = str(e)
            
            await stream_manager.close()
            
        except Exception as e:
            processor_result["error"] = str(e)
            print(f"   ❌ ToolProcessor test failed: {e}")
            self.issues_found.append(f"ToolProcessor error: {e}")
        
        self.test_results["processor"] = processor_result
    
    async def _test_tool_execution_scenarios(self):
        """Test tool execution scenarios to reproduce the exact issue."""
        print("🎯 Testing tool execution scenarios (reproducing exact issue)...")
        
        execution_result = {
            "setup_success": False,
            "tools_tested": [],
            "success_count": 0,
            "unhealthy_count": 0,
            "other_errors": 0,
            "pattern_analysis": {},
            "error": None
        }
        
        try:
            print("   🚀 Setting up execution environment...")
            processor, stream_manager = await setup_mcp_sse(
                servers=self.servers,
                connection_timeout=30.0,
                default_timeout=60.0,
                namespace="gateway"
            )
            
            execution_result["setup_success"] = True
            
            # Get tools to test (same ones from diagnostic)
            test_tools = [
                {"name": "mcp-grid-dev-echo", "args": {"message": "diagnostic test"}},
                {"name": "mcp-grid-dev-duckduckgo-search", "args": {"query": "test", "max_results": 1}},
                {"name": "mcp-grid-dev-google-search", "args": {"query": "test", "max_results": 1}}
            ]
            
            print(f"   🧪 Testing {len(test_tools)} tools...")
            
            for i, test_tool in enumerate(test_tools):
                tool_name = test_tool["name"]
                args = test_tool["args"]
                
                print(f"      Test {i+1}: {tool_name}")
                
                tool_result = {
                    "name": tool_name,
                    "success": False,
                    "error": None,
                    "unhealthy_connection": False,
                    "execution_time": 0.0,
                    "response_type": None
                }
                
                try:
                    # Execute via registry (same as ToolManager does)
                    registry = await ToolRegistryProvider.get_registry()
                    tool = await registry.get_tool(tool_name, "gateway")
                    
                    if tool:
                        exec_start = time.time()
                        result = await tool.execute(timeout=60.0, **args)
                        tool_result["execution_time"] = time.time() - exec_start
                        
                        if isinstance(result, dict):
                            if result.get("error"):
                                tool_result["error"] = result["error"]
                                if "unhealthy connection" in str(result["error"]).lower():
                                    tool_result["unhealthy_connection"] = True
                                    execution_result["unhealthy_count"] += 1
                                    print(f"         ❌ UNHEALTHY CONNECTION: {result['error']}")
                                else:
                                    execution_result["other_errors"] += 1
                                    print(f"         ❌ Error: {result['error']}")
                            else:
                                tool_result["success"] = True
                                execution_result["success_count"] += 1
                                print(f"         ✅ Success ({tool_result['execution_time']:.2f}s)")
                                
                                # Check result type
                                if result.get("available") is False:
                                    tool_result["response_type"] = "unavailable"
                                elif "results" in str(result):
                                    tool_result["response_type"] = "search_results"
                                elif "message" in str(result):
                                    tool_result["response_type"] = "echo"
                                else:
                                    tool_result["response_type"] = "other"
                        else:
                            tool_result["success"] = True
                            execution_result["success_count"] += 1
                            tool_result["response_type"] = "direct"
                            print(f"         ✅ Success - direct response ({tool_result['execution_time']:.2f}s)")
                    else:
                        tool_result["error"] = "Tool not found in registry"
                        execution_result["other_errors"] += 1
                        print(f"         ❌ Tool not found in registry")
                        
                except Exception as e:
                    tool_result["error"] = str(e)
                    execution_result["other_errors"] += 1
                    print(f"         ❌ Execution exception: {e}")
                
                execution_result["tools_tested"].append(tool_result)
            
            # Pattern analysis
            print("   📊 Pattern analysis...")
            total_tests = len(execution_result["tools_tested"])
            
            execution_result["pattern_analysis"] = {
                "total_tests": total_tests,
                "success_rate": (execution_result["success_count"] / total_tests * 100) if total_tests > 0 else 0,
                "unhealthy_rate": (execution_result["unhealthy_count"] / total_tests * 100) if total_tests > 0 else 0,
                "error_rate": (execution_result["other_errors"] / total_tests * 100) if total_tests > 0 else 0
            }
            
            analysis = execution_result["pattern_analysis"]
            print(f"      Success rate: {analysis['success_rate']:.1f}%")
            print(f"      Unhealthy connection rate: {analysis['unhealthy_rate']:.1f}%")
            print(f"      Other error rate: {analysis['error_rate']:.1f}%")
            
            if execution_result["unhealthy_count"] > 0:
                self.issues_found.append(f"Found {execution_result['unhealthy_count']} unhealthy connection errors")
            
            await stream_manager.close()
            
        except Exception as e:
            execution_result["error"] = str(e)
            print(f"   ❌ Execution test failed: {e}")
            self.issues_found.append(f"Execution test error: {e}")
        
        self.test_results["execution"] = execution_result
    
    async def _analyze_root_cause(self):
        """Analyze results to identify root cause."""
        print("🔍 Analyzing root cause...")
        
        # Collect all results
        raw_transport = self.test_results.get("raw_transport", {})
        stream_manager = self.test_results.get("stream_manager", {})  
        registration = self.test_results.get("registration", {})
        processor = self.test_results.get("processor", {})
        execution = self.test_results.get("execution", {})
        
        print("📊 DIAGNOSTIC SUMMARY:")
        print(f"   Raw Transport: {'✅' if raw_transport.get('health_check') else '❌'} Healthy")
        print(f"   StreamManager: {'✅' if stream_manager.get('initialization_success') else '❌'} Success")
        print(f"   Registration: {'✅' if registration.get('setup_success') else '❌'} Success")
        print(f"   ToolProcessor: {'✅' if processor.get('setup_success') else '❌'} Success")
        print(f"   Tool Execution: {execution.get('success_count', 0)}/{len(execution.get('tools_tested', []))} successful")
        
        print("\n🚨 ISSUES IDENTIFIED:")
        if self.issues_found:
            for i, issue in enumerate(self.issues_found, 1):
                print(f"   {i}. {issue}")
        else:
            print("   ✅ No issues found - system appears healthy")
        
        print("\n🎯 ROOT CAUSE ANALYSIS:")
        
        # Check for the classic pattern: transport healthy but tools report unhealthy
        transport_healthy = raw_transport.get("health_check", False)
        unhealthy_errors = execution.get("unhealthy_count", 0)
        
        if transport_healthy and unhealthy_errors > 0:
            print("   🚨 CLASSIC BUG PATTERN DETECTED:")
            print("      - Raw transport reports healthy")
            print("      - But tool execution reports 'unhealthy connection'")
            print("      - This indicates a bug in the health monitoring logic")
            print()
            print("   🔧 LIKELY FIXES NEEDED:")
            print("      1. Update MCPTool._is_stream_manager_available() to be more lenient")
            print("      2. Fix SSE Transport health check timing issues") 
            print("      3. Add grace period after initialization")
            print("      4. Reduce aggressive failure counting")
            
        elif not transport_healthy:
            print("   🔍 TRANSPORT LEVEL ISSUE:")
            print("      - Raw transport is actually unhealthy")
            print("      - Need to fix SSE transport connectivity")
            
        elif unhealthy_errors == 0:
            print("   ✅ NO UNHEALTHY CONNECTION ISSUES DETECTED:")
            print("      - Transport is healthy")
            print("      - Tools execute successfully")
            print("      - System appears to be working correctly")
            
        else:
            print("   ❓ MIXED RESULTS:")
            print("      - Need further investigation")
            print("      - Check timing and intermittent issues")
        
        print(f"\n⏱️  PERFORMANCE SUMMARY:")
        if raw_transport.get("initialization_time"):
            print(f"   Transport init: {raw_transport['initialization_time']:.2f}s")
        if stream_manager.get("initialization_time"):
            print(f"   StreamManager init: {stream_manager['initialization_time']:.2f}s")
        if registration.get("setup_time"):
            print(f"   Registration: {registration['setup_time']:.2f}s")
        
        # Show execution times
        if execution.get("tools_tested"):
            exec_times = [t.get("execution_time", 0) for t in execution["tools_tested"] if t.get("execution_time")]
            if exec_times:
                avg_time = sum(exec_times) / len(exec_times)
                print(f"   Average tool execution: {avg_time:.2f}s")


async def main():
    """Main diagnostic entry point."""
    print("🔧 CHUK Tool Processor Level Diagnostic")
    print("=" * 60)
    
    diagnostic = CHUKProcessorDiagnostic()
    
    try:
        await diagnostic.run_full_stack_diagnostic()
    except KeyboardInterrupt:
        print("\n\n⏹️ Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Diagnostic crashed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())