#!/usr/bin/env python3
"""
SSE Connection Health Diagnostic - Focus on Resolving "Unhealthy Connection" Issues

This diagnostic is specifically designed to identify and resolve the root cause
of "unhealthy connection" errors in MCP SSE transport, even when the underlying
SSE stream is working correctly.

HEALTH FOCUS AREAS:
1. SSE stream connectivity and event flow
2. MCP protocol handshake sequence
3. SSE Transport health reporting accuracy
4. Session discovery and message endpoint setup
5. Tool availability vs connection health

Usage:
    python sse_health_diagnostic.py

Environment Variables Required:
    MCP_GATEWAY_URL - SSE endpoint URL
    MCP_AUTH_TOKEN - Authentication token
"""

import asyncio
import sys
import time
import traceback
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    env_file = load_dotenv(verbose=True)
    if env_file:
        print("✅ Loaded environment variables from .env file")
    else:
        print("📄 No .env file found, using system environment variables")
except ImportError:
    print("❌ python-dotenv not installed!")
    print("   Install with: pip install python-dotenv")
    print("   Using system environment variables only")

# Load configuration from environment
import os

GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL") or os.environ.get("GATEWAY_URL") or os.environ.get("MCP_URL")

AUTH_TOKEN = (
    os.environ.get("MCP_AUTH_TOKEN") or os.environ.get("MCP_GATEWAY_TOKEN") or os.environ.get("GATEWAY_AUTH_TOKEN")
)

# Validate configuration
if not GATEWAY_URL:
    print("❌ ERROR: No gateway URL provided!")
    print("Please set one of these environment variables:")
    print("  - MCP_GATEWAY_URL")
    print("  - GATEWAY_URL")
    print("  - MCP_URL")
    print()
    print("Example .env file:")
    print("  MCP_GATEWAY_URL=https://your-sse-endpoint")
    print("  MCP_AUTH_TOKEN=your-token-here")
    sys.exit(1)

# Import HTTP client for raw SSE testing
try:
    import httpx
except ImportError:
    print("❌ httpx not installed!")
    print("   Install with: pip install httpx")
    sys.exit(1)

# CHUK Tool Processor imports
try:
    from chuk_tool_processor.logging import get_logger
    from chuk_tool_processor.mcp.transport.sse_transport import SSETransport
    from chuk_tool_processor.registry.provider import ToolRegistryProvider
except ImportError as e:
    print(f"❌ CHUK Tool Processor import failed: {e}")
    print("Make sure CHUK Tool Processor is properly installed")
    sys.exit(1)

logger = get_logger("sse_health_diagnostic")


class SSEHealthDiagnostic:
    """
    Focused diagnostic to resolve SSE connection health issues.

    Identifies why SSE Transport reports "unhealthy" when SSE streams work fine.
    """

    def __init__(self):
        self.start_time = time.time()
        self.gateway_url = GATEWAY_URL.rstrip("/")
        self.auth_token = AUTH_TOKEN
        self.test_results = {}
        self.health_issues = []

        # Focus on SSE endpoint
        self.is_sse_endpoint = self.gateway_url.endswith("/sse")
        if not self.is_sse_endpoint:
            self.gateway_url = f"{self.gateway_url}/sse"
            print(f"🔧 Appended /sse to URL: {self.gateway_url}")

    async def run_health_diagnostic(self):
        """
        Run focused health diagnostic to resolve connection issues.
        """
        print("🏥 SSE Connection Health Diagnostic - Resolving 'Unhealthy Connection' Issues")
        print("=" * 80)
        print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 SSE Endpoint: {self.gateway_url}")

        if self.auth_token:
            print(f"🔐 Auth Token: {len(self.auth_token)} chars, starts with {self.auth_token[:15]}...")
        else:
            print("⚠️ No authentication token provided")
        print()

        try:
            # Phase 1: Raw SSE Stream Validation
            print("🌊 Phase 1: Raw SSE Stream Health Check")
            print("-" * 50)
            await self._test_raw_sse_stream()

            # Phase 2: MCP Protocol Analysis
            print("\n📋 Phase 2: MCP Protocol Handshake Analysis")
            print("-" * 50)
            await self._test_mcp_protocol_handshake()

            # Phase 3: SSE Transport Health Investigation
            print("\n🔧 Phase 3: SSE Transport Health Investigation")
            print("-" * 50)
            await self._investigate_transport_health()

            # Phase 4: Connection Health Root Cause Analysis
            print("\n🔍 Phase 4: Connection Health Root Cause Analysis")
            print("-" * 50)
            await self._analyze_health_reporting()

            # Final Health Resolution Report
            print("\n🎯 Health Issue Resolution Report")
            print("-" * 50)
            await self._generate_resolution_report()

        except Exception as e:
            logger.error(f"Health diagnostic failed: {e}", exc_info=True)
            print(f"❌ Health diagnostic failed: {e}")
            traceback.print_exc()

        print(f"\n🏁 Health diagnostic completed in {time.time() - self.start_time:.2f}s")

    async def _test_raw_sse_stream(self):
        """Test raw SSE stream to verify basic connectivity works."""
        print("🌊 Testing raw SSE stream connectivity...")

        # Prepare headers
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "User-Agent": "sse-health-diagnostic/1.0.0",
        }

        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        stream_results = {
            "connection_successful": False,
            "events_received": 0,
            "session_discovered": False,
            "keepalive_received": False,
            "error": None,
        }

        try:
            timeout = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                print(f"   🔗 Connecting to: {self.gateway_url}")

                async with client.stream("GET", self.gateway_url, headers=headers) as response:
                    print(f"   📊 Response: {response.status_code} - {response.headers.get('content-type', 'unknown')}")

                    if response.status_code == 200:
                        stream_results["connection_successful"] = True

                        if "text/event-stream" in response.headers.get("content-type", ""):
                            print("   ✅ Valid SSE stream established")

                            # Read events for health analysis
                            print("   📡 Monitoring SSE events (15 second window)...")

                            read_start = time.time()
                            current_event = None

                            async for line in response.aiter_lines():
                                if time.time() - read_start > 15.0:
                                    break

                                line = line.strip()
                                if not line:
                                    continue

                                stream_results["events_received"] += 1

                                if line.startswith("event:"):
                                    current_event = line.split(":", 1)[1].strip()
                                    print(f"      📨 Event: {current_event}")

                                    if current_event == "keepalive":
                                        stream_results["keepalive_received"] = True

                                elif line.startswith("data:"):
                                    data = line.split(":", 1)[1].strip()

                                    # Look for session discovery
                                    if "/messages/" in data or current_event == "endpoint":
                                        stream_results["session_discovered"] = True
                                        print(f"      📍 Session endpoint discovered: {data}")

                                    # Show keepalive data
                                    elif current_event == "keepalive":
                                        print(f"      💓 Keepalive: {data}")

                                # Stop after reasonable number of events
                                if stream_results["events_received"] >= 20:
                                    break

                            read_time = time.time() - read_start
                            print("   📊 Stream Health Summary:")
                            print(f"      Events received: {stream_results['events_received']}")
                            print(f"      Session discovered: {'✅' if stream_results['session_discovered'] else '❌'}")
                            print(f"      Keepalive received: {'✅' if stream_results['keepalive_received'] else '❌'}")
                            print(f"      Read time: {read_time:.2f}s")

                        else:
                            print(f"   ❌ Wrong content type: {response.headers.get('content-type')}")
                            stream_results["error"] = f"Wrong content type: {response.headers.get('content-type')}"

                    elif response.status_code == 401:
                        print("   ❌ Authentication failed - check token")
                        stream_results["error"] = "Authentication failed"

                    elif response.status_code == 403:
                        print("   ❌ Access denied - insufficient permissions")
                        stream_results["error"] = "Access denied"

                    else:
                        print(f"   ❌ Unexpected response: {response.status_code}")
                        stream_results["error"] = f"HTTP {response.status_code}"

        except Exception as e:
            print(f"   ❌ Raw SSE stream test failed: {e}")
            stream_results["error"] = str(e)

        self.test_results["raw_sse_stream"] = stream_results

        # Analysis
        if stream_results["connection_successful"] and stream_results["session_discovered"]:
            print("   ✅ Raw SSE stream is healthy - connection issues likely in transport layer")
        elif stream_results["connection_successful"]:
            print("   ⚠️  SSE stream connects but no session discovery - may affect MCP protocol")
            self.health_issues.append("SSE stream missing session discovery")
        else:
            print("   ❌ Raw SSE stream has issues - this is the root cause")
            self.health_issues.append("Raw SSE stream connectivity failure")

    async def _test_mcp_protocol_handshake(self):
        """Test MCP protocol handshake sequence in detail."""
        print("📋 Testing MCP protocol handshake...")

        handshake_results = {
            "transport_created": False,
            "initialization_started": False,
            "initialization_completed": False,
            "session_discovery": False,
            "message_url_obtained": False,
            "ping_successful": False,
            "health_check_passed": False,
            "error": None,
            "timing": {},
        }

        try:
            # Create SSE Transport
            print("   🏗️  Creating SSE Transport...")
            start_time = time.time()

            # Use base URL (remove /sse) for transport
            base_url = self.gateway_url.replace("/sse", "") if self.gateway_url.endswith("/sse") else self.gateway_url

            transport = SSETransport(
                url=base_url,
                api_key=self.auth_token,
                connection_timeout=30.0,
                default_timeout=60.0,
                enable_metrics=True,
            )

            handshake_results["transport_created"] = True
            handshake_results["timing"]["transport_creation"] = time.time() - start_time
            print(f"      ✅ Transport created ({handshake_results['timing']['transport_creation']:.2f}s)")

            # Test initialization
            print("   🚀 Testing MCP initialization...")
            init_start = time.time()
            handshake_results["initialization_started"] = True

            try:
                # Monitor initialization with timeout
                init_success = await asyncio.wait_for(transport.initialize(), timeout=45.0)

                handshake_results["timing"]["initialization"] = time.time() - init_start

                if init_success:
                    handshake_results["initialization_completed"] = True
                    print(f"      ✅ Initialization completed ({handshake_results['timing']['initialization']:.2f}s)")

                    # Check session discovery
                    if hasattr(transport, "session_id") and transport.session_id:
                        handshake_results["session_discovery"] = True
                        print(f"      ✅ Session ID: {transport.session_id}")

                    if hasattr(transport, "message_url") and transport.message_url:
                        handshake_results["message_url_obtained"] = True
                        print(f"      ✅ Message URL: {transport.message_url}")

                    # Test connection health
                    print("   💓 Testing connection health...")
                    is_connected = transport.is_connected()
                    handshake_results["health_check_passed"] = is_connected

                    if is_connected:
                        print("      ✅ Transport reports healthy")
                    else:
                        print("      ❌ Transport reports unhealthy")
                        self.health_issues.append("Transport reports unhealthy despite successful initialization")

                    # Test ping
                    print("   🏓 Testing ping functionality...")
                    ping_start = time.time()
                    try:
                        ping_success = await asyncio.wait_for(transport.send_ping(), timeout=15.0)

                        handshake_results["timing"]["ping"] = time.time() - ping_start
                        handshake_results["ping_successful"] = ping_success

                        if ping_success:
                            print(f"      ✅ Ping successful ({handshake_results['timing']['ping']:.2f}s)")
                        else:
                            print(f"      ❌ Ping failed ({handshake_results['timing']['ping']:.2f}s)")
                            self.health_issues.append("Ping test failed")

                    except TimeoutError:
                        handshake_results["timing"]["ping"] = time.time() - ping_start
                        print(f"      ⏰ Ping timed out ({handshake_results['timing']['ping']:.2f}s)")
                        self.health_issues.append("Ping timeout")

                    # Get metrics
                    print("   📊 Transport metrics:")
                    metrics = transport.get_metrics()
                    for key, value in metrics.items():
                        if value is not None:
                            if isinstance(value, float):
                                print(f"      {key}: {value:.3f}")
                            else:
                                print(f"      {key}: {value}")

                    handshake_results["metrics"] = metrics

                    # Close transport
                    await transport.close()

                else:
                    handshake_results["error"] = "Initialization returned False"
                    print("      ❌ Initialization failed - returned False")
                    self.health_issues.append("MCP initialization returned False")

            except TimeoutError:
                handshake_results["timing"]["initialization"] = time.time() - init_start
                handshake_results["error"] = (
                    f"Initialization timeout after {handshake_results['timing']['initialization']:.1f}s"
                )
                print(f"      ⏰ Initialization timed out ({handshake_results['timing']['initialization']:.1f}s)")
                self.health_issues.append("MCP initialization timeout")

        except Exception as e:
            handshake_results["error"] = str(e)
            print(f"   ❌ MCP handshake test failed: {e}")
            self.health_issues.append(f"MCP handshake error: {e}")

        self.test_results["mcp_handshake"] = handshake_results

    async def _investigate_transport_health(self):
        """Investigate SSE Transport health reporting accuracy."""
        print("🔧 Investigating transport health reporting...")

        health_investigation = {
            "multiple_transports_tested": 0,
            "health_consistency": [],
            "initialization_attempts": 0,
            "successful_initializations": 0,
            "health_check_results": [],
            "patterns": [],
        }

        # Test multiple transport instances to check consistency
        print("   🔄 Testing multiple transport instances for health consistency...")

        base_url = self.gateway_url.replace("/sse", "") if self.gateway_url.endswith("/sse") else self.gateway_url

        for attempt in range(3):
            print(f"   🧪 Transport instance {attempt + 1}/3...")

            try:
                transport = SSETransport(
                    url=base_url,
                    api_key=self.auth_token,
                    connection_timeout=20.0,
                    default_timeout=30.0,
                    enable_metrics=True,
                )

                health_investigation["multiple_transports_tested"] += 1
                health_investigation["initialization_attempts"] += 1

                # Test initialization
                init_start = time.time()
                init_success = await asyncio.wait_for(transport.initialize(), timeout=30.0)
                init_time = time.time() - init_start

                instance_result = {
                    "attempt": attempt + 1,
                    "init_success": init_success,
                    "init_time": init_time,
                    "health_check": None,
                    "metrics": None,
                }

                if init_success:
                    health_investigation["successful_initializations"] += 1

                    # Check health
                    is_healthy = transport.is_connected()
                    instance_result["health_check"] = is_healthy

                    # Get metrics
                    metrics = transport.get_metrics()
                    instance_result["metrics"] = metrics

                    print(f"      Init: ✅ ({init_time:.2f}s), Health: {'✅' if is_healthy else '❌'}")

                    # Track health patterns
                    health_investigation["health_check_results"].append(is_healthy)

                else:
                    print(f"      Init: ❌ ({init_time:.2f}s)")

                health_investigation["health_consistency"].append(instance_result)
                await transport.close()

                # Small delay between attempts
                await asyncio.sleep(1.0)

            except Exception as e:
                print(f"      ❌ Instance {attempt + 1} failed: {e}")
                health_investigation["health_consistency"].append({"attempt": attempt + 1, "error": str(e)})

        # Analyze patterns
        print("   📊 Health pattern analysis:")

        success_rate = (
            health_investigation["successful_initializations"] / health_investigation["initialization_attempts"] * 100
        )
        print(f"      Initialization success rate: {success_rate:.1f}%")

        health_results = health_investigation["health_check_results"]
        if health_results:
            healthy_count = sum(health_results)
            health_rate = (healthy_count / len(health_results)) * 100
            print(f"      Health check success rate: {health_rate:.1f}%")

            if health_rate < 100:
                health_investigation["patterns"].append("Inconsistent health reporting")
                self.health_issues.append(f"Health check inconsistent: {health_rate:.1f}% success rate")

        if success_rate < 100:
            health_investigation["patterns"].append("Initialization inconsistency")
            self.health_issues.append(f"Initialization inconsistent: {success_rate:.1f}% success rate")

        self.test_results["transport_health_investigation"] = health_investigation

    async def _analyze_health_reporting(self):
        """Analyze why health reporting might be inaccurate."""
        print("🔍 Analyzing health reporting accuracy...")

        analysis_results = {
            "raw_stream_healthy": False,
            "mcp_handshake_successful": False,
            "transport_reports_healthy": False,
            "inconsistency_detected": False,
            "likely_causes": [],
            "recommended_fixes": [],
        }

        # Analyze test results
        raw_sse = self.test_results.get("raw_sse_stream", {})
        mcp_handshake = self.test_results.get("mcp_handshake", {})

        analysis_results["raw_stream_healthy"] = raw_sse.get("connection_successful", False) and raw_sse.get(
            "session_discovered", False
        )

        analysis_results["mcp_handshake_successful"] = mcp_handshake.get(
            "initialization_completed", False
        ) and mcp_handshake.get("message_url_obtained", False)

        analysis_results["transport_reports_healthy"] = mcp_handshake.get("health_check_passed", False)

        print("   📊 Health Analysis Summary:")
        print(f"      Raw SSE stream: {'✅ Healthy' if analysis_results['raw_stream_healthy'] else '❌ Issues'}")
        print(
            f"      MCP handshake: {'✅ Successful' if analysis_results['mcp_handshake_successful'] else '❌ Failed'}"
        )
        print(
            f"      Transport health: {'✅ Healthy' if analysis_results['transport_reports_healthy'] else '❌ Unhealthy'}"
        )

        # Detect inconsistencies
        if (
            analysis_results["raw_stream_healthy"]
            and analysis_results["mcp_handshake_successful"]
            and not analysis_results["transport_reports_healthy"]
        ):
            analysis_results["inconsistency_detected"] = True
            print("   🚨 INCONSISTENCY DETECTED: Stream works but transport reports unhealthy")

            # Investigate likely causes
            analysis_results["likely_causes"].extend(
                [
                    "SSE Transport health check logic bug",
                    "Timeout configuration too aggressive",
                    "Session state management issue",
                    "Metrics calculation error",
                ]
            )

            analysis_results["recommended_fixes"].extend(
                [
                    "Review SSE Transport is_connected() method",
                    "Increase timeout values in transport",
                    "Check session_id and message_url persistence",
                    "Verify metrics tracking accuracy",
                ]
            )

        elif not analysis_results["raw_stream_healthy"]:
            print("   🔍 Root cause: Raw SSE stream has connectivity issues")
            analysis_results["likely_causes"].extend(
                ["Network connectivity problems", "Authentication token issues", "SSE endpoint configuration problems"]
            )

            analysis_results["recommended_fixes"].extend(
                [
                    "Check network connectivity to SSE endpoint",
                    "Verify authentication token validity",
                    "Contact gateway administrator",
                ]
            )

        elif not analysis_results["mcp_handshake_successful"]:
            print("   🔍 Root cause: MCP protocol handshake failing")
            analysis_results["likely_causes"].extend(
                ["MCP protocol version mismatch", "SSE Transport initialization bugs", "Session discovery timeout"]
            )

            analysis_results["recommended_fixes"].extend(
                [
                    "Check MCP protocol version compatibility",
                    "Review SSE Transport initialization code",
                    "Increase session discovery timeout",
                ]
            )

        else:
            print("   ✅ No inconsistencies detected - system appears healthy")

        self.test_results["health_analysis"] = analysis_results

    async def _generate_resolution_report(self):
        """Generate comprehensive resolution report."""
        total_time = time.time() - self.start_time

        print("🎯 SSE CONNECTION HEALTH RESOLUTION REPORT")
        print("=" * 60)
        print(f"🕒 Total diagnostic time: {total_time:.2f}s")
        print(f"📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Health status summary
        raw_sse = self.test_results.get("raw_sse_stream", {})
        mcp_handshake = self.test_results.get("mcp_handshake", {})
        analysis = self.test_results.get("health_analysis", {})

        print("📊 HEALTH STATUS SUMMARY:")
        print(f"  🌊 Raw SSE Stream: {'✅ HEALTHY' if raw_sse.get('connection_successful') else '❌ UNHEALTHY'}")
        print(
            f"  📋 MCP Handshake: {'✅ SUCCESSFUL' if mcp_handshake.get('initialization_completed') else '❌ FAILED'}"
        )
        print(
            f"  🔧 Transport Health: {'✅ REPORTS HEALTHY' if mcp_handshake.get('health_check_passed') else '❌ REPORTS UNHEALTHY'}"
        )
        print()

        # Issues identified
        if self.health_issues:
            print("🚨 HEALTH ISSUES IDENTIFIED:")
            for i, issue in enumerate(self.health_issues, 1):
                print(f"  {i}. {issue}")
            print()

        # Root cause analysis
        if analysis.get("inconsistency_detected"):
            print("🔍 ROOT CAUSE ANALYSIS:")
            print("  The SSE stream is working correctly, but the SSE Transport")
            print("  is incorrectly reporting 'unhealthy connection' status.")
            print("  This is a FALSE POSITIVE in the transport health reporting.")
            print()

            print("💡 LIKELY CAUSES:")
            for cause in analysis.get("likely_causes", []):
                print(f"  • {cause}")
            print()

            print("🔧 RECOMMENDED FIXES:")
            for fix in analysis.get("recommended_fixes", []):
                print(f"  • {fix}")
            print()

        # Performance metrics
        if raw_sse.get("connection_successful"):
            print("📈 PERFORMANCE METRICS:")
            print(f"  SSE events received: {raw_sse.get('events_received', 0)}")
            print(f"  Session discovery: {'✅' if raw_sse.get('session_discovered') else '❌'}")
            print(f"  Keepalive received: {'✅' if raw_sse.get('keepalive_received') else '❌'}")

            if mcp_handshake.get("timing"):
                timing = mcp_handshake["timing"]
                print(f"  MCP init time: {timing.get('initialization', 0):.2f}s")
                if "ping" in timing:
                    print(f"  Ping response time: {timing['ping']:.2f}s")
            print()

        # Final recommendations
        print("🎯 FINAL RECOMMENDATIONS:")

        if analysis.get("inconsistency_detected"):
            print("  1. ✅ Your SSE connection is actually HEALTHY")
            print("  2. 🐛 The 'unhealthy connection' errors are FALSE POSITIVES")
            print("  3. 🔧 Update SSE Transport health check logic")
            print("  4. ⏱️  Consider increasing timeout values")
            print("  5. 🧪 Use this diagnostic to verify real health status")

        elif not raw_sse.get("connection_successful"):
            print("  1. 🔧 Fix SSE endpoint connectivity issues first")
            print("  2. 🔐 Verify authentication token is valid")
            print("  3. 🌐 Check network connectivity to gateway")

        elif not mcp_handshake.get("initialization_completed"):
            print("  1. 🔧 Fix MCP protocol handshake issues")
            print("  2. ⏱️  Increase initialization timeouts")
            print("  3. 📋 Review MCP protocol compatibility")

        else:
            print("  1. ✅ System appears healthy")
            print("  2. 📊 Monitor for intermittent issues")
            print("  3. 🔧 Consider updating transport health logic")

        print()

        # Success criteria
        success_score = 0
        if raw_sse.get("connection_successful"):
            success_score += 40
        if raw_sse.get("session_discovered"):
            success_score += 20
        if mcp_handshake.get("initialization_completed"):
            success_score += 30
        if mcp_handshake.get("health_check_passed"):
            success_score += 10

        print(f"🏥 OVERALL HEALTH SCORE: {success_score}/100")

        if success_score >= 90:
            print("🟢 EXCELLENT - Connection is healthy, transport issues are false positives")
        elif success_score >= 70:
            print("🟡 GOOD - Minor issues, mostly false positives")
        elif success_score >= 50:
            print("🟠 FAIR - Some real issues mixed with false positives")
        else:
            print("🔴 POOR - Significant connection issues need resolution")


async def main():
    """Main health diagnostic entry point."""
    print("🏥 SSE Connection Health Diagnostic")
    print("=" * 50)

    # Display configuration
    print(f"🎯 Target: {GATEWAY_URL}")
    if AUTH_TOKEN:
        print(f"🔐 Auth: {len(AUTH_TOKEN)} characters")
    else:
        print("⚠️ No authentication token")
    print()

    # Run health diagnostic
    diagnostic = SSEHealthDiagnostic()

    try:
        await diagnostic.run_health_diagnostic()
    except KeyboardInterrupt:
        print("\n\n⏹️ Health diagnostic interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Health diagnostic crashed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
