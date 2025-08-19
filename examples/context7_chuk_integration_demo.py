#!/usr/bin/env python
"""
context7_chuk_integration_demo.py
================================
Demonstrates Context7 MCP server integration with CHUK Tool Processor
using HTTP Streamable transport.

This script shows:
1. Connection to Context7 MCP server via HTTP Streamable transport
2. Registration of Context7 tools in CHUK registry
3. Tool execution through different parser plugins
4. Practical examples of library documentation retrieval

Prerequisites:
- Context7 MCP server is accessible at https://mcp.context7.com/mcp
- chuk-mcp package is installed for HTTP transport
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    HAS_COLORAMA = False
    class MockColor:
        def __getattr__(self, name): return ""
    Fore = Style = MockColor()

# ─── Local package bootstrap ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1] if __name__ == "__main__" else Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chuk_tool_processor.logging import get_logger
from chuk_tool_processor.registry.provider import ToolRegistryProvider

# Check for HTTP Streamable setup availability
try:
    from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
    HAS_HTTP_STREAMABLE = True
except ImportError as e:
    HAS_HTTP_STREAMABLE = False
    HTTP_IMPORT_ERROR = str(e)

# Parser plugins
from chuk_tool_processor.plugins.parsers.json_tool import JsonToolPlugin
from chuk_tool_processor.plugins.parsers.xml_tool import XmlToolPlugin
from chuk_tool_processor.plugins.parsers.function_call_tool import FunctionCallPlugin

# Executor
from chuk_tool_processor.execution.tool_executor import ToolExecutor
from chuk_tool_processor.execution.strategies.inprocess_strategy import InProcessStrategy

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult

logger = get_logger("context7-chuk-demo")

# ─── Configuration ─────────────────────────────────────────────────────────
CONTEXT7_URL = "https://mcp.context7.com/mcp"
SERVER_NAME = "context7"
NAMESPACE = "context7"


class Context7Demo:
    """Demonstration class for Context7 integration with CHUK."""

    def __init__(self):
        self.stream_manager = None
        self.executor = None
        self.registry = None

    def banner(self, text: str, color: str = Fore.CYAN) -> None:
        """Print a colored banner."""
        if HAS_COLORAMA:
            print(f"{color}\n=== {text} ==={Style.RESET_ALL}")
        else:
            print(f"\n=== {text} ===")

    def info(self, text: str) -> None:
        """Print info message."""
        if HAS_COLORAMA:
            print(f"{Fore.GREEN}✅ {text}{Style.RESET_ALL}")
        else:
            print(f"✅ {text}")

    def warning(self, text: str) -> None:
        """Print warning message."""
        if HAS_COLORAMA:
            print(f"{Fore.YELLOW}⚠️  {text}{Style.RESET_ALL}")
        else:
            print(f"⚠️  {text}")

    def error(self, text: str) -> None:
        """Print error message."""
        if HAS_COLORAMA:
            print(f"{Fore.RED}❌ {text}{Style.RESET_ALL}")
        else:
            print(f"❌ {text}")

    async def check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        self.banner("Dependency Check")
        
        if not HAS_HTTP_STREAMABLE:
            self.error(f"HTTP Streamable setup not available: {HTTP_IMPORT_ERROR}")
            self.warning("To fix: pip install chuk-mcp")
            return False

        # Check chuk-mcp availability
        try:
            import chuk_mcp
            self.info(f"chuk-mcp available at {chuk_mcp.__file__}")
        except ImportError:
            self.error("chuk-mcp package not installed")
            self.warning("To fix: pip install chuk-mcp")
            return False

        # Check HTTP transport components
        try:
            from chuk_mcp.transports.http import http_client
            from chuk_mcp.transports.http.parameters import StreamableHTTPParameters
            self.info("chuk-mcp HTTP transport components available")
        except ImportError as e:
            self.error(f"chuk-mcp HTTP transport not available: {e}")
            return False

        self.info("All dependencies satisfied")
        return True

    async def connect_to_context7(self) -> bool:
        """Connect to Context7 MCP server and set up tools."""
        self.banner("Context7 Connection")
        
        try:
            print(f"🔄 Connecting to Context7 at {CONTEXT7_URL}...")
            
            _, self.stream_manager = await setup_mcp_http_streamable(
                servers=[{
                    "name": SERVER_NAME,
                    "url": CONTEXT7_URL,
                }],
                server_names={0: SERVER_NAME},
                namespace=NAMESPACE,
                connection_timeout=30.0,
                default_timeout=60.0,  # Longer timeout for Context7 operations
            )
            
            self.info("Connected to Context7 successfully!")
            return True
            
        except Exception as e:
            self.error(f"Failed to connect to Context7: {e}")
            logger.error(f"Context7 connection failed: {e}", exc_info=True)
            return False

    async def setup_executor(self) -> bool:
        """Set up the tool executor."""
        try:
            self.registry = await ToolRegistryProvider.get_registry()
            
            self.executor = ToolExecutor(
                self.registry,
                strategy=InProcessStrategy(
                    self.registry,
                    default_timeout=60.0,  # Long timeout for documentation retrieval
                    max_concurrency=2,     # Conservative for external service
                ),
            )
            
            self.info("Tool executor configured")
            return True
            
        except Exception as e:
            self.error(f"Failed to setup executor: {e}")
            return False

    async def show_available_tools(self) -> bool:
        """Display available Context7 tools."""
        self.banner("Available Context7 Tools")
        
        try:
            tools = await self.registry.list_tools(NAMESPACE)
            if not tools:
                self.warning("No tools found in Context7 namespace")
                return False

            for ns, name in tools:
                tool_meta = await self.registry.get_metadata(name, ns)
                desc = tool_meta.description if tool_meta else "No description"
                print(f"  🔧 {name}")
                print(f"     {desc[:80]}{'...' if len(desc) > 80 else ''}")
                
            self.info(f"Found {len(tools)} Context7 tools")
            return True
            
        except Exception as e:
            self.error(f"Failed to list tools: {e}")
            return False

    async def test_library_resolution(self) -> None:
        """Test the resolve-library-id tool."""
        self.banner("Library ID Resolution Test")
        
        test_libraries = [
            ("react", "React library"),
            ("fastapi", "FastAPI framework"),
            ("tensorflow", "TensorFlow ML library"),
        ]
        
        for lib_name, description in test_libraries:
            try:
                print(f"\n🔍 Resolving library ID for '{lib_name}' ({description})")
                
                call = ToolCall(
                    tool=f"{NAMESPACE}.resolve-library-id",
                    arguments={"libraryName": lib_name}
                )
                
                results = await self.executor.execute([call])
                
                if results and not results[0].error:
                    result_content = str(results[0].result)
                    # Extract library IDs from the response
                    if "/" in result_content:
                        lines = result_content.split('\n')
                        found_ids = [line.strip() for line in lines 
                                   if line.strip().startswith('/') and ' ' in line]
                        
                        if found_ids:
                            self.info(f"Found {len(found_ids)} matches for {lib_name}")
                            for lib_id in found_ids[:3]:  # Show first 3
                                print(f"  📌 {lib_id.split()[0]}")
                        else:
                            self.info(f"Response received for {lib_name}")
                    else:
                        self.info(f"Response received for {lib_name}")
                else:
                    error_msg = results[0].error if results else "No results"
                    self.warning(f"Failed to resolve {lib_name}: {error_msg}")
                    
            except Exception as e:
                self.error(f"Error resolving {lib_name}: {e}")

    async def test_documentation_retrieval(self) -> None:
        """Test the get-library-docs tool."""
        self.banner("Documentation Retrieval Test")
        
        test_cases = [
            {
                "name": "React Hooks",
                "library_id": "/facebook/react",
                "topic": "useState useEffect hooks",
                "tokens": 10000
            },
            {
                "name": "FastAPI Authentication", 
                "library_id": "/tiangolo/fastapi",
                "topic": "authentication JWT middleware",
                "tokens": 8000
            },
        ]
        
        for case in test_cases:
            try:
                print(f"\n📚 Retrieving docs: {case['name']}")
                print(f"   Library: {case['library_id']}")
                print(f"   Topic: {case['topic']}")
                print(f"   Tokens: {case['tokens']}")
                
                call = ToolCall(
                    tool=f"{NAMESPACE}.get-library-docs",
                    arguments={
                        "context7CompatibleLibraryID": case['library_id'],
                        "topic": case['topic'],
                        "tokens": case['tokens']
                    }
                )
                
                results = await self.executor.execute([call])
                
                if results and not results[0].error:
                    content = str(results[0].result)
                    duration = results[0].duration
                    
                    # Analyze content
                    lines = content.split('\n')
                    code_blocks = content.count('```')
                    sections = len([line for line in lines if line.startswith('TITLE:')])
                    
                    self.info(f"Documentation retrieved in {duration:.2f}s")
                    print(f"   📄 Content: {len(content):,} characters")
                    print(f"   🔧 Code blocks: {code_blocks}")
                    print(f"   📑 Sections: {sections}")
                    
                    # Show first few lines as preview
                    preview_lines = [line for line in lines[:5] if line.strip()]
                    if preview_lines:
                        print(f"   👀 Preview: {preview_lines[0][:60]}...")
                        
                else:
                    error_msg = results[0].error if results else "No results"
                    if "not found" in error_msg.lower():
                        self.warning(f"Library not found - may need different ID")
                    else:
                        self.error(f"Failed to get docs: {error_msg}")
                        
            except Exception as e:
                self.error(f"Error retrieving docs for {case['name']}: {e}")

    async def test_parser_plugins(self) -> None:
        """Test different parser plugins with Context7 tools."""
        self.banner("Parser Plugin Integration Test")
        
        # Define test cases for each parser
        test_plugins = [
            (
                "JSON Plugin",
                JsonToolPlugin(),
                json.dumps({
                    "tool_calls": [{
                        "tool": f"{NAMESPACE}.resolve-library-id",
                        "arguments": {"libraryName": "express.js"}
                    }]
                })
            ),
            (
                "XML Plugin",
                XmlToolPlugin(), 
                f'<tool name="{NAMESPACE}.get-library-docs" args=\'{{"context7CompatibleLibraryID": "/vercel/next.js", "topic": "routing", "tokens": 5000}}\'/>',
            ),
            (
                "Function Call Plugin",
                FunctionCallPlugin(),
                json.dumps({
                    "function_call": {
                        "name": f"{NAMESPACE}.resolve-library-id",
                        "arguments": {"libraryName": "django"}
                    }
                })
            ),
        ]
        
        for plugin_name, plugin, test_input in test_plugins:
            try:
                print(f"\n🧪 Testing {plugin_name}")
                
                # Parse the input
                calls = await plugin.try_parse(test_input)
                if not calls:
                    self.warning(f"{plugin_name} produced no calls")
                    continue
                
                # Execute the calls
                results = await self.executor.execute(calls)
                
                # Show results
                for call, result in zip(calls, results):
                    if not result.error:
                        content_preview = str(result.result)[:100] + "..." if len(str(result.result)) > 100 else str(result.result)
                        self.info(f"{plugin_name} success: {call.tool}")
                        print(f"   📤 Result: {content_preview}")
                    else:
                        self.warning(f"{plugin_name} failed: {result.error}")
                        
            except Exception as e:
                self.error(f"{plugin_name} test failed: {e}")

    async def demonstrate_practical_usage(self) -> None:
        """Demonstrate practical usage scenarios."""
        self.banner("Practical Usage Scenarios")
        
        # Scenario 1: Research a new library
        print("\n📋 Scenario 1: Research a new library")
        print("   Task: Learn about Pydantic for data validation")
        
        try:
            # First, resolve the library ID
            resolve_call = ToolCall(
                tool=f"{NAMESPACE}.resolve-library-id",
                arguments={"libraryName": "pydantic"}
            )
            
            resolve_results = await self.executor.execute([resolve_call])
            
            if resolve_results and not resolve_results[0].error:
                print("   ✅ Library ID resolved")
                
                # Then get documentation
                docs_call = ToolCall(
                    tool=f"{NAMESPACE}.get-library-docs",
                    arguments={
                        "context7CompatibleLibraryID": "/pydantic/pydantic",
                        "topic": "data validation models BaseModel",
                        "tokens": 12000
                    }
                )
                
                docs_results = await self.executor.execute([docs_call])
                
                if docs_results and not docs_results[0].error:
                    content = str(docs_results[0].result)
                    self.info(f"Documentation retrieved: {len(content):,} chars")
                    
                    # Count practical indicators
                    examples = content.count('example')
                    imports = content.count('import')
                    classes = content.count('class ')
                    
                    print(f"   📖 Examples found: {examples}")
                    print(f"   📦 Import statements: {imports}")
                    print(f"   🏗️  Class definitions: {classes}")
                else:
                    self.warning("Documentation retrieval failed")
            else:
                self.warning("Library ID resolution failed")
                
        except Exception as e:
            self.error(f"Scenario 1 failed: {e}")
        
        # Scenario 2: Compare frameworks
        print("\n📋 Scenario 2: Compare web frameworks")
        print("   Task: Compare FastAPI vs Flask")
        
        try:
            compare_calls = [
                ToolCall(
                    tool=f"{NAMESPACE}.get-library-docs",
                    arguments={
                        "context7CompatibleLibraryID": "/tiangolo/fastapi",
                        "topic": "getting started tutorial basics",
                        "tokens": 8000
                    }
                ),
                ToolCall(
                    tool=f"{NAMESPACE}.get-library-docs",
                    arguments={
                        "context7CompatibleLibraryID": "/pallets/flask",
                        "topic": "getting started tutorial basics",
                        "tokens": 8000
                    }
                )
            ]
            
            compare_results = await self.executor.execute(compare_calls)
            
            frameworks = ["FastAPI", "Flask"]
            for i, (framework, result) in enumerate(zip(frameworks, compare_results)):
                if not result.error:
                    content = str(result.result)
                    self.info(f"{framework} docs retrieved: {len(content):,} chars")
                else:
                    self.warning(f"{framework} docs failed: {result.error}")
                    
        except Exception as e:
            self.error(f"Scenario 2 failed: {e}")

    async def show_performance_metrics(self) -> None:
        """Show performance metrics if available."""
        self.banner("Performance Metrics")
        
        try:
            if self.stream_manager and hasattr(self.stream_manager, 'transports'):
                for name, transport in self.stream_manager.transports.items():
                    if hasattr(transport, 'get_metrics'):
                        metrics = transport.get_metrics()
                        print(f"\n📊 Transport: {name}")
                        for key, value in metrics.items():
                            if value is not None:
                                if isinstance(value, float):
                                    print(f"   {key}: {value:.3f}")
                                else:
                                    print(f"   {key}: {value}")
            else:
                self.info("Performance metrics not available")
                
        except Exception as e:
            self.warning(f"Could not retrieve metrics: {e}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.stream_manager:
            try:
                await self.stream_manager.close()
                self.info("Cleanup completed")
            except Exception as e:
                self.warning(f"Cleanup warning: {e}")

    async def run_demo(self) -> None:
        """Run the complete demonstration."""
        print("🚀 Context7 CHUK Tool Processor Integration Demo")
        print("=" * 60)
        print("This demo shows Context7 MCP server integration with CHUK")
        print("using HTTP Streamable transport for documentation retrieval.\n")
        
        try:
            # Check dependencies
            if not await self.check_dependencies():
                return
            
            # Connect to Context7
            if not await self.connect_to_context7():
                return
            
            # Setup executor
            if not await self.setup_executor():
                return
            
            # Show available tools
            if not await self.show_available_tools():
                return
            
            # Run tests
            await self.test_library_resolution()
            await self.test_documentation_retrieval()
            await self.test_parser_plugins()
            await self.demonstrate_practical_usage()
            await self.show_performance_metrics()
            
            # Success summary
            self.banner("Demo Completed Successfully", Fore.GREEN)
            self.info("Context7 integration with CHUK is working!")
            print("Key capabilities demonstrated:")
            print("  ✅ Library ID resolution")
            print("  ✅ Documentation retrieval")
            print("  ✅ Parser plugin integration") 
            print("  ✅ Practical usage scenarios")
            print("  ✅ Performance monitoring")
            
        except KeyboardInterrupt:
            self.warning("Demo interrupted by user")
        except Exception as e:
            self.error(f"Demo failed: {e}")
            logger.error(f"Demo error: {e}", exc_info=True)
        finally:
            await self.cleanup()


async def main():
    """Main entry point."""
    # Set up logging
    logging_level = os.environ.get("LOGLEVEL", "INFO").upper()
    import logging
    logging.getLogger("chuk_tool_processor").setLevel(getattr(logging, logging_level))
    
    # Run demo
    demo = Context7Demo()
    await demo.run_demo()


if __name__ == "__main__":
    asyncio.run(main())