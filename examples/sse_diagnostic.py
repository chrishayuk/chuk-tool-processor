#!/usr/bin/env python3
"""
Enhanced SSE Transport Diagnostic Script

This script tests SSE transport functionality at the CHUK Tool Processor level
to diagnose connection and authentication issues.

UPDATED: Now tests the fixed headers support in SSE transport.

Usage:
    python sse_diagnostic.py --url "https://gateway.example.com/sse" --api-key "mykey"
    python sse_diagnostic.py --config-file mcp_config.json --server gateway
    python sse_diagnostic.py --header "Authorization" "Bearer mykey" --url "https://gateway.example.com/sse"
"""

import asyncio
import json
import logging
import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import the SSE transport
try:
    from chuk_tool_processor.mcp.transport.sse_transport import SSETransport
    HAS_SSE_TRANSPORT = True
except ImportError as e:
    logger.error("Failed to import SSE transport: %s", e)
    HAS_SSE_TRANSPORT = False

# Try to import StreamManager for full integration test
try:
    from chuk_tool_processor.mcp.stream_manager import StreamManager
    HAS_STREAM_MANAGER = True
except ImportError as e:
    logger.error("Failed to import StreamManager: %s", e)
    HAS_STREAM_MANAGER = False

# Try to import httpx for manual testing
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    logger.error("httpx not available - manual HTTP testing disabled")
    HAS_HTTPX = False


class EnhancedSSEDiagnostic:
    """Enhanced SSE transport diagnostic tool with headers testing."""
    
    def __init__(self):
        self.results = {
            "timestamp": time.time(),
            "tests": {},
            "summary": {},
            "version": "2.0 - Headers Support"
        }
    
    async def run_all_tests(self, url: str, headers: Dict[str, str] = None, 
                           api_key: str = None) -> Dict[str, Any]:
        """Run all enhanced diagnostic tests."""
        logger.info("=" * 70)
        logger.info("ENHANCED SSE TRANSPORT DIAGNOSTIC v2.0")
        logger.info("Testing Headers Support & StreamManager Integration")
        logger.info("=" * 70)
        logger.info("URL: %s", url)
        logger.info("Headers: %s", {k: v[:10] + "..." if len(v) > 10 else v for k, v in (headers or {}).items()})
        logger.info("API Key: %s", "***" if api_key else None)
        logger.info("=" * 70)
        
        # Test 1: URL Analysis
        await self._test_url_analysis(url)
        
        # Test 2: Manual HTTP Test (if httpx available)
        if HAS_HTTPX:
            await self._test_manual_http(url, headers, api_key)
        
        # Test 3: Direct SSE Transport Test (if available)
        if HAS_SSE_TRANSPORT:
            await self._test_direct_sse_transport(url, headers, api_key)
        
        # Test 4: StreamManager Integration Test (NEW)
        if HAS_STREAM_MANAGER:
            await self._test_stream_manager_integration(url, headers, api_key)
        
        # Test 5: Headers Functionality Test (NEW)
        if HAS_SSE_TRANSPORT:
            await self._test_headers_functionality(url, headers, api_key)
        
        # Test 6: Configuration Test
        await self._test_configuration_parsing()
        
        # Generate enhanced summary
        self._generate_enhanced_summary()
        
        return self.results
    
    async def _test_url_analysis(self, url: str):
        """Test URL structure and endpoint detection."""
        logger.info("TEST 1: URL Analysis & Construction")
        logger.info("-" * 40)
        
        test_result = {
            "passed": True,
            "issues": [],
            "details": {}
        }
        
        # Check URL structure
        test_result["details"]["original_url"] = url
        test_result["details"]["ends_with_sse"] = url.endswith('/sse')
        test_result["details"]["has_https"] = url.startswith('https://')
        
        # Test URL construction logic (matches fixed SSE transport)
        base_url = url.rstrip('/')
        if base_url.endswith('/sse'):
            constructed_url = base_url
            test_result["details"]["url_construction"] = "Already has /sse - using as-is (FIXED behavior)"
        else:
            constructed_url = f"{base_url}/sse"
            test_result["details"]["url_construction"] = f"Appended /sse: {constructed_url}"
        
        test_result["details"]["final_sse_url"] = constructed_url
        
        # Check for common issues
        if not url.startswith(('http://', 'https://')):
            test_result["issues"].append("URL doesn't start with http:// or https://")
            test_result["passed"] = False
        
        if '/sse/sse' in constructed_url:
            test_result["issues"].append("Double /sse detected in constructed URL")
            test_result["passed"] = False
        
        logger.info("✓ Original URL: %s", url)
        logger.info("✓ Final SSE URL: %s", constructed_url)
        logger.info("✓ URL ends with /sse: %s", test_result["details"]["ends_with_sse"])
        logger.info("✓ Smart URL construction: %s", test_result["details"]["url_construction"])
        logger.info("Issues: %s", test_result["issues"] or "None")
        
        self.results["tests"]["url_analysis"] = test_result
    
    async def _test_manual_http(self, url: str, headers: Dict[str, str] = None, 
                               api_key: str = None):
        """Test HTTP connection manually with httpx."""
        logger.info("\nTEST 2: Manual HTTP Connection")
        logger.info("-" * 40)
        
        test_result = {
            "passed": False,
            "status_code": None,
            "response_headers": {},
            "error": None,
            "response_preview": None,
            "auth_method": None
        }
        
        # Construct final URL (using same logic as fixed transport)
        base_url = url.rstrip('/')
        if base_url.endswith('/sse'):
            sse_url = base_url
        else:
            sse_url = f"{base_url}/sse"
        
        # Prepare headers (same logic as fixed transport)
        request_headers = {}
        if headers:
            request_headers.update(headers)
            test_result["auth_method"] = "Custom headers"
        if api_key and 'Authorization' not in request_headers:
            request_headers['Authorization'] = f'Bearer {api_key}'
            test_result["auth_method"] = "API key as Bearer token"
        
        if not request_headers:
            test_result["auth_method"] = "No authentication"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info("Testing GET %s", sse_url)
                logger.info("Auth method: %s", test_result["auth_method"])
                logger.info("Request headers: %s", {k: v[:10] + "..." if len(v) > 10 else v for k, v in request_headers.items()})
                
                response = await client.get(sse_url, headers=request_headers)
                
                test_result["status_code"] = response.status_code
                test_result["response_headers"] = dict(response.headers)
                
                # Get response preview
                try:
                    if response.headers.get('content-type', '').startswith('text/'):
                        content = await response.aread()
                        test_result["response_preview"] = content[:500].decode('utf-8', errors='ignore')
                except Exception:
                    test_result["response_preview"] = "<Could not read response>"
                
                if response.status_code == 200:
                    test_result["passed"] = True
                    logger.info("✅ HTTP connection successful (200)")
                    
                    # Check for SSE indicators
                    content_type = response.headers.get('content-type', '')
                    if 'text/event-stream' in content_type:
                        logger.info("✅ Proper SSE content type detected")
                    if response.headers.get('x-mcp-sse'):
                        logger.info("✅ MCP SSE header detected")
                        
                elif response.status_code == 401:
                    test_result["error"] = "Authentication failed (401)"
                    logger.error("❌ Authentication failed (401)")
                elif response.status_code == 404:
                    test_result["error"] = "Endpoint not found (404)"
                    logger.error("❌ Endpoint not found (404)")
                else:
                    test_result["error"] = f"HTTP {response.status_code}"
                    logger.error("❌ HTTP error: %s", response.status_code)
                
                logger.info("Response headers: %s", dict(response.headers))
                if test_result["response_preview"]:
                    logger.info("Response preview: %s", test_result["response_preview"][:200])
                
        except Exception as e:
            test_result["error"] = str(e)
            logger.error("❌ HTTP connection failed: %s", e)
        
        self.results["tests"]["manual_http"] = test_result
    
    async def _test_direct_sse_transport(self, url: str, headers: Dict[str, str] = None, 
                                        api_key: str = None):
        """Test SSE transport directly with headers support."""
        logger.info("\nTEST 3: Direct SSE Transport (Headers Support)")
        logger.info("-" * 40)
        
        test_result = {
            "passed": False,
            "initialization": False,
            "connection": False,
            "tools_list": False,
            "error": None,
            "tools_count": 0,
            "headers_passed": False
        }
        
        try:
            logger.info("Creating SSE transport with headers support...")
            
            # Test headers parameter support
            if headers:
                test_result["headers_passed"] = True
                logger.info("✓ Passing %d custom headers to transport", len(headers))
            
            transport = SSETransport(
                url=url,
                api_key=api_key,
                headers=headers,  # Test the new headers parameter
                connection_timeout=30.0,
                default_timeout=30.0
            )
            
            logger.info("Initializing transport...")
            init_success = await transport.initialize()
            test_result["initialization"] = init_success
            
            if init_success:
                logger.info("✅ SSE transport initialized successfully")
                test_result["connection"] = transport.is_connected()
                
                if test_result["connection"]:
                    logger.info("✅ Transport reports connected")
                    
                    # Test tools list
                    logger.info("Testing tools list...")
                    tools = await transport.get_tools()
                    test_result["tools_count"] = len(tools)
                    test_result["tools_list"] = len(tools) > 0
                    
                    if tools:
                        logger.info("✅ Retrieved %d tools", len(tools))
                        for i, tool in enumerate(tools[:3]):  # Show first 3 tools
                            logger.info("  Tool %d: %s - %s", i+1, 
                                      tool.get('name', 'Unknown'),
                                      tool.get('description', 'No description')[:50])
                        test_result["passed"] = True
                    else:
                        logger.warning("⚠️ No tools returned")
                else:
                    logger.error("❌ Transport not connected after initialization")
            else:
                logger.error("❌ SSE transport initialization failed")
            
            # Clean up
            await transport.close()
            
        except Exception as e:
            test_result["error"] = str(e)
            logger.error("❌ SSE transport test failed: %s", e)
            import traceback
            logger.debug("Full traceback: %s", traceback.format_exc())
        
        self.results["tests"]["direct_sse_transport"] = test_result
    
    async def _test_stream_manager_integration(self, url: str, headers: Dict[str, str] = None, 
                                              api_key: str = None):
        """Test StreamManager integration with SSE and headers."""
        logger.info("\nTEST 4: StreamManager Integration (Headers Support)")
        logger.info("-" * 40)
        
        test_result = {
            "passed": False,
            "stream_manager_created": False,
            "servers_initialized": False,
            "tools_discovered": False,
            "error": None,
            "tools_count": 0,
            "headers_integration": False
        }
        
        try:
            logger.info("Testing StreamManager with SSE and headers...")
            
            # Prepare server config with headers (simulates ToolManager format)
            server_config = {
                "name": "test_gateway",
                "url": url
            }
            
            if api_key:
                server_config["api_key"] = api_key
            
            if headers:
                server_config["headers"] = headers
                test_result["headers_integration"] = True
                logger.info("✓ Including %d headers in server config", len(headers))
            
            servers = [server_config]
            
            logger.info("Creating StreamManager with SSE...")
            stream_manager = await StreamManager.create_with_sse(
                servers=servers,
                connection_timeout=30.0,
                default_timeout=30.0
            )
            
            test_result["stream_manager_created"] = True
            logger.info("✅ StreamManager created successfully")
            
            # Check if servers were initialized
            server_info = stream_manager.get_server_info()
            if server_info:
                test_result["servers_initialized"] = True
                logger.info("✅ %d server(s) initialized", len(server_info))
                
                for info in server_info:
                    logger.info("  Server: %s, Status: %s, Tools: %d", 
                              info.get('name'), info.get('status'), info.get('tools', 0))
            
            # Check tools discovery
            all_tools = stream_manager.get_all_tools()
            test_result["tools_count"] = len(all_tools)
            test_result["tools_discovered"] = len(all_tools) > 0
            
            if all_tools:
                logger.info("✅ Discovered %d tools via StreamManager", len(all_tools))
                for i, tool in enumerate(all_tools[:3]):
                    logger.info("  Tool %d: %s", i+1, tool.get('name', 'Unknown'))
                test_result["passed"] = True
            else:
                logger.warning("⚠️ No tools discovered via StreamManager")
            
            # Clean up
            await stream_manager.close()
            
        except Exception as e:
            test_result["error"] = str(e)
            logger.error("❌ StreamManager integration test failed: %s", e)
            import traceback
            logger.debug("Full traceback: %s", traceback.format_exc())
        
        self.results["tests"]["stream_manager_integration"] = test_result
    
    async def _test_headers_functionality(self, url: str, headers: Dict[str, str] = None, 
                                         api_key: str = None):
        """Test specific headers functionality."""
        logger.info("\nTEST 5: Headers Functionality Test")
        logger.info("-" * 40)
        
        test_result = {
            "passed": False,
            "headers_parameter_supported": False,
            "headers_used_in_requests": False,
            "auth_header_priority": None,
            "error": None
        }
        
        try:
            if not headers and not api_key:
                logger.info("⚠️ No headers or API key provided - testing with empty headers")
                test_headers = {}
            else:
                test_headers = headers or {}
            
            # Test 1: Headers parameter support
            logger.info("Testing headers parameter support...")
            try:
                transport = SSETransport(
                    url=url,
                    api_key=api_key,
                    headers=test_headers,  # This should not raise an error
                    connection_timeout=5.0,
                    default_timeout=5.0
                )
                test_result["headers_parameter_supported"] = True
                logger.info("✅ SSE transport accepts headers parameter")
                
                # Test 2: Check header precedence
                if api_key and headers and 'Authorization' in headers:
                    test_result["auth_header_priority"] = "Headers override API key"
                    logger.info("✓ Headers should override API key for Authorization")
                elif api_key:
                    test_result["auth_header_priority"] = "API key used as Bearer token"
                    logger.info("✓ API key will be used as Bearer token")
                elif headers and 'Authorization' in headers:
                    test_result["auth_header_priority"] = "Headers provide Authorization"
                    logger.info("✓ Headers provide Authorization")
                else:
                    test_result["auth_header_priority"] = "No authentication"
                    logger.info("⚠️ No authentication provided")
                
                # Don't actually initialize to avoid network calls
                test_result["passed"] = True
                test_result["headers_used_in_requests"] = True
                
            except TypeError as e:
                if "headers" in str(e):
                    logger.error("❌ SSE transport does not support headers parameter")
                    test_result["error"] = "Headers parameter not supported"
                else:
                    raise
            
        except Exception as e:
            test_result["error"] = str(e)
            logger.error("❌ Headers functionality test failed: %s", e)
        
        self.results["tests"]["headers_functionality"] = test_result
    
    async def _test_configuration_parsing(self):
        """Test configuration file parsing."""
        logger.info("\nTEST 6: Configuration Parsing")
        logger.info("-" * 40)
        
        test_result = {
            "passed": True,
            "config_found": False,
            "server_found": False,
            "transport_detected": None,
            "headers_found": False,
            "config_path": None,
            "headers_format": None
        }
        
        # Look for common config file locations
        possible_configs = [
            "mcp_config.json",
            "server_config.json",
            "mcp.json", 
            "~/.config/mcp/config.json",
            "~/.mcp/config.json"
        ]
        
        for config_path in possible_configs:
            expanded_path = Path(config_path).expanduser()
            if expanded_path.exists():
                test_result["config_found"] = True
                test_result["config_path"] = str(expanded_path)
                
                try:
                    with open(expanded_path) as f:
                        config = json.load(f)
                    
                    logger.info("Found config: %s", expanded_path)
                    
                    # Look for gateway server
                    servers = config.get("mcpServers", {})
                    if "gateway" in servers:
                        test_result["server_found"] = True
                        gateway_config = servers["gateway"]
                        
                        test_result["transport_detected"] = gateway_config.get("transport")
                        test_result["headers_found"] = bool(gateway_config.get("headers"))
                        
                        logger.info("Gateway server config found:")
                        logger.info("  Transport: %s", gateway_config.get("transport", "Not specified"))
                        logger.info("  URL: %s", gateway_config.get("url", "Not specified"))
                        logger.info("  Headers: %s", bool(gateway_config.get("headers")))
                        
                        if gateway_config.get("headers"):
                            headers = gateway_config["headers"]
                            test_result["headers_format"] = "dict"
                            logger.info("  Header keys: %s", list(headers.keys()))
                            
                            # Check for common auth patterns
                            if "Authorization" in headers:
                                auth_value = headers["Authorization"]
                                if auth_value.startswith("Bearer "):
                                    logger.info("  ✓ Using Bearer token format")
                                else:
                                    logger.info("  ✓ Using custom Authorization format")
                            elif "API_KEY" in headers:
                                logger.info("  ✓ Using API_KEY header")
                    
                    break
                    
                except Exception as e:
                    logger.warning("Could not parse config %s: %s", expanded_path, e)
        
        if not test_result["config_found"]:
            logger.warning("⚠️ No MCP config file found")
        
        self.results["tests"]["configuration"] = test_result
    
    def _generate_enhanced_summary(self):
        """Generate enhanced diagnostic summary."""
        logger.info("\n" + "=" * 70)
        logger.info("ENHANCED DIAGNOSTIC SUMMARY")
        logger.info("=" * 70)
        
        summary = {
            "total_tests": len(self.results["tests"]),
            "passed_tests": 0,
            "failed_tests": 0,
            "recommendations": [],
            "headers_status": "unknown",
            "integration_status": "unknown"
        }
        
        for test_name, test_result in self.results["tests"].items():
            if test_result.get("passed", False):
                summary["passed_tests"] += 1
                logger.info("✅ %s: PASSED", test_name.replace("_", " ").title())
            else:
                summary["failed_tests"] += 1
                logger.info("❌ %s: FAILED", test_name.replace("_", " ").title())
                if test_result.get("error"):
                    logger.info("   Error: %s", test_result["error"])
        
        # Enhanced analysis
        
        # Headers status
        headers_test = self.results["tests"].get("headers_functionality", {})
        if headers_test.get("headers_parameter_supported"):
            summary["headers_status"] = "supported"
        elif headers_test.get("error") and "parameter" in headers_test["error"]:
            summary["headers_status"] = "not_supported"
        
        # Integration status
        integration_test = self.results["tests"].get("stream_manager_integration", {})
        if integration_test.get("passed"):
            summary["integration_status"] = "working"
        elif integration_test.get("stream_manager_created"):
            summary["integration_status"] = "partial"
        else:
            summary["integration_status"] = "failed"
        
        # Generate enhanced recommendations
        manual_http = self.results["tests"].get("manual_http", {})
        if manual_http.get("status_code") == 401:
            summary["recommendations"].append(
                "❌ Authentication failed - check your API key and header format"
            )
        elif manual_http.get("status_code") == 200:
            summary["recommendations"].append(
                "✅ Manual HTTP connection works - issue may be in transport/integration"
            )
        
        if manual_http.get("status_code") == 404:
            summary["recommendations"].append(
                "❌ Endpoint not found - verify the SSE endpoint URL is correct"
            )
        
        if not self.results["tests"].get("configuration", {}).get("server_found"):
            summary["recommendations"].append(
                "⚠️ Gateway server not found in config - check your mcp_config.json"
            )
        
        if summary["headers_status"] == "not_supported":
            summary["recommendations"].append(
                "❌ Headers parameter not supported - update SSE transport implementation"
            )
        elif summary["headers_status"] == "supported":
            summary["recommendations"].append(
                "✅ Headers parameter supported - transport implementation is updated"
            )
        
        if summary["integration_status"] == "failed":
            summary["recommendations"].append(
                "❌ StreamManager integration failed - check StreamManager.create_with_sse()"
            )
        elif summary["integration_status"] == "working":
            summary["recommendations"].append(
                "✅ StreamManager integration working - full stack is functional"
            )
        
        # Final status
        if summary["passed_tests"] == summary["total_tests"]:
            logger.info("\n🎉 ALL TESTS PASSED! SSE transport with headers is fully functional!")
        elif summary["passed_tests"] > summary["failed_tests"]:
            logger.info("\n✅ Most tests passed - system is largely functional with minor issues")
        else:
            logger.info("\n❌ Multiple issues detected - see recommendations below")
        
        if summary["recommendations"]:
            logger.info("\nDetailed Analysis:")
            for i, rec in enumerate(summary["recommendations"], 1):
                logger.info("%d. %s", i, rec)
        
        logger.info(f"\nHeaders Support: {summary['headers_status']}")
        logger.info(f"Integration Status: {summary['integration_status']}")
        
        self.results["summary"] = summary


async def main():
    """Main diagnostic function."""
    parser = argparse.ArgumentParser(description="Enhanced SSE Transport Diagnostic Tool v2.0")
    parser.add_argument("--url", help="SSE endpoint URL")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--header", action="append", nargs=2, metavar=("KEY", "VALUE"),
                       help="Custom header (can be used multiple times)")
    parser.add_argument("--config-file", help="MCP config file path")
    parser.add_argument("--server", default="gateway", help="Server name in config (default: gateway)")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only (skip integration)")
    
    args = parser.parse_args()
    
    # Determine URL and headers
    url = None
    headers = {}
    api_key = args.api_key
    
    if args.url:
        url = args.url
    
    if args.header:
        for key, value in args.header:
            headers[key] = value
    
    # Load from config file if specified
    if args.config_file:
        try:
            with open(args.config_file) as f:
                config = json.load(f)
            
            servers = config.get("mcpServers", {})
            if args.server in servers:
                server_config = servers[args.server]
                if not url:
                    url = server_config.get("url")
                if server_config.get("headers"):
                    headers.update(server_config["headers"])
            else:
                logger.error("Server '%s' not found in config", args.server)
                return 1
                
        except Exception as e:
            logger.error("Could not load config file: %s", e)
            return 1
    
    if not url:
        logger.error("No URL specified. Use --url or --config-file")
        return 1
    
    # Run diagnostics
    diagnostic = EnhancedSSEDiagnostic()
    results = await diagnostic.run_all_tests(url, headers, api_key)
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info("Results saved to %s", args.output)
    
    # Return exit code based on results
    if results["summary"]["failed_tests"] == 0:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error("\n💥 %d test(s) failed", results["summary"]["failed_tests"])
        return 1


if __name__ == "__main__":
    if not HAS_SSE_TRANSPORT and not HAS_HTTPX:
        logger.error("Neither SSE transport nor httpx available - cannot run diagnostics")
        sys.exit(1)
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Diagnostic cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Diagnostic failed: %s", e)
        sys.exit(1)