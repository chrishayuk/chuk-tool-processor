#!/usr/bin/env python3
"""
Atlassian SSE OAuth transport example with chuk-tool-processor.

This script demonstrates:
1. OAuth 2.1 authentication flow with Atlassian MCP server
2. SSE transport connection with OAuth token
3. Proper initialization_timeout handling for slow servers

Usage:
    cd /Users/chrishay/chris-source/chuk-ai/chuk-tool-processor
    uv run python examples/atlassian_sse.py
"""

import asyncio
import hashlib
import json
import logging
import secrets
import sys
import webbrowser
from base64 import urlsafe_b64encode
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from chuk_tool_processor.mcp.setup_mcp_sse import setup_mcp_sse

# Set up logging - WARNING level to reduce noise
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Only show INFO for httpx requests to see OAuth flow
logging.getLogger("httpx").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback."""

    authorization_code = None

    def do_GET(self):
        """Handle the callback request."""
        query = parse_qs(urlparse(self.path).query)

        if 'code' in query:
            OAuthCallbackHandler.authorization_code = query['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write("""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: green;">Authentication Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error = query.get('error', ['Unknown error'])[0]
            self.wfile.write(f"""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">Authentication Failed</h1>
                <p>Error: {error}</p>
                </body></html>
            """.encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


async def discover_oauth_metadata(server_url: str) -> dict:
    """Discover OAuth Authorization Server metadata (RFC 8414)."""
    print("\n[1/5] Discovering OAuth Authorization Server...")
    print(f"      Server: {server_url}")

    well_known_url = f"{server_url}/.well-known/oauth-authorization-server"

    async with httpx.AsyncClient() as client:
        response = await client.get(well_known_url)
        response.raise_for_status()
        metadata = response.json()

    print(f"      ✓ Authorization endpoint: {metadata['authorization_endpoint']}")
    print(f"      ✓ Token endpoint: {metadata['token_endpoint']}")

    return metadata


async def register_client(registration_endpoint: str) -> dict:
    """Register OAuth client dynamically (RFC 7591)."""
    print("\n[2/5] Registering OAuth client...")

    client_metadata = {
        "client_name": "chuk-tool-processor-atlassian-test",
        "redirect_uris": ["http://127.0.0.1:8765/callback"],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # PKCE provides security
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            registration_endpoint,
            json=client_metadata,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        registration = response.json()

    print(f"      ✓ Client ID: {registration['client_id']}")

    return registration


def generate_pkce_challenge():
    """Generate PKCE code verifier and challenge."""
    code_verifier = urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


async def get_authorization_code(auth_endpoint: str, client_id: str, code_challenge: str) -> str:
    """Get authorization code via browser flow."""
    print("\n[3/5] Starting authorization flow...")

    # Start local callback server
    server = HTTPServer(('127.0.0.1', 8765), OAuthCallbackHandler)

    # Build authorization URL
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "http://127.0.0.1:8765/callback",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "mcp",
    }
    auth_url = f"{auth_endpoint}?{urlencode(params)}"

    print(f"      Opening browser for authorization...")
    print(f"      URL: {auth_url}")
    webbrowser.open(auth_url)

    print("\n      ⏳ Waiting for authorization...")
    print("         (Please complete the OAuth flow in your browser)")

    # Wait for callback
    while OAuthCallbackHandler.authorization_code is None:
        server.handle_request()

    code = OAuthCallbackHandler.authorization_code
    print(f"      ✓ Received authorization code: {code[:20]}...")

    return code


async def exchange_code_for_token(
    token_endpoint: str,
    client_id: str,
    code: str,
    code_verifier: str
) -> dict:
    """Exchange authorization code for access token."""
    print("\n[4/5] Exchanging code for access token...")

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://127.0.0.1:8765/callback",
        "client_id": client_id,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_endpoint,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        tokens = response.json()

    access_token = tokens.get('access_token', '')
    print(f"      ✓ Access token: {access_token[:30]}...")
    print(f"      ✓ Token type: {tokens.get('token_type')}")
    if 'expires_in' in tokens:
        print(f"      ✓ Expires in: {tokens['expires_in']} seconds")

    return tokens


async def test_with_chuk_tool_processor(access_token: str):
    """Test OAuth token with chuk-tool-processor SSE transport."""
    print("\n[5/5] Testing with chuk-tool-processor...")
    print("="*70)

    atlassian_url = "https://mcp.atlassian.com/v1/sse"

    print("\n✓ Test: Connecting to Atlassian MCP server with OAuth via SSE")
    print(f"    URL: {atlassian_url}")
    print("    Initializing connection (may take 60-120 seconds)...")

    try:
        # Use setup_mcp_sse with OAuth token in headers
        servers = [
            {
                "name": "atlassian",
                "url": atlassian_url,
                "headers": {"Authorization": f"Bearer {access_token}"},
            }
        ]

        # Use 120s initialization timeout for potentially slow servers
        processor, stream_manager = await setup_mcp_sse(
            servers=servers,
            namespace="atlassian",
            connection_timeout=30.0,
            default_timeout=30.0,
            initialization_timeout=120.0,  # Extended for slow servers
        )

        print("    ✅ Connection successful!")

        # Get tools
        print("\n✓ Fetching tools from Atlassian")
        tools = stream_manager.get_all_tools()
        print(f"    Retrieved {len(tools)} tools")

        if tools:
            print("\n    Available tools:")
            for tool in tools[:5]:
                name = tool.get('name', 'unknown')
                desc = tool.get('description', 'No description')[:50]
                print(f"      • {name}: {desc}")
            if len(tools) > 5:
                print(f"      ... and {len(tools) - 5} more")

        await stream_manager.close()
        return True

    except asyncio.TimeoutError:
        print("    ❌ Connection timed out after 120s")
        print("\n    Possible issues:")
        print("      • Token may be invalid or expired")
        print("      • Atlassian MCP server not responding")
        print("      • Network connectivity issue")
        return False

    except Exception as e:
        print(f"    ❌ Error: {e}")
        logger.exception("Detailed error:")
        return False


async def main():
    """Main OAuth flow and test."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║          Atlassian SSE OAuth Test with chuk-tool-processor            ║
║                                                                       ║
║  This script performs complete OAuth 2.1 flow and tests               ║
║  that OAuth tokens work correctly with SSE transport                  ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    try:
        atlassian_server = "https://mcp.atlassian.com"

        # Step 1: Discover OAuth server
        metadata = await discover_oauth_metadata(atlassian_server)

        # Step 2: Register client
        registration = await register_client(metadata['registration_endpoint'])
        client_id = registration['client_id']

        # Step 3: Generate PKCE challenge
        code_verifier, code_challenge = generate_pkce_challenge()

        # Step 4: Get authorization code
        auth_code = await get_authorization_code(
            metadata['authorization_endpoint'],
            client_id,
            code_challenge
        )

        # Step 5: Exchange for access token
        tokens = await exchange_code_for_token(
            metadata['token_endpoint'],
            client_id,
            auth_code,
            code_verifier
        )
        access_token = tokens['access_token']

        # Step 6: Test with chuk-tool-processor
        success = await test_with_chuk_tool_processor(access_token)

        if success:
            print("\n" + "="*70)
            print("✅ SUCCESS! OAuth + SSE + initialization_timeout working correctly")
            print("="*70)
            print("\nKey points proven:")
            print("  ✓ Complete OAuth 2.1 flow (RFC 8414 + RFC 7591 + PKCE)")
            print("  ✓ OAuth token passed via headers to SSE transport")
            print("  ✓ Extended initialization_timeout (120s) allows slow servers to initialize")
            print("  ✓ Successfully connected to Atlassian MCP server")
            print("  ✓ Retrieved tools from Atlassian")
            return 0
        else:
            print("\n" + "="*70)
            print("⚠️  OAuth flow completed but connection test failed")
            print("="*70)
            print("\nCheck the error messages above for details.")
            return 1

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Detailed error:")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
