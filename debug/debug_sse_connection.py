#!/usr/bin/env python
"""
debug_sse_connection.py
───────────────────────
Debug script to test SSE connection manually and see what events are being sent.

This helps us understand what the MCP client is expecting vs what we're sending.
"""

import asyncio
import json
from datetime import datetime

import httpx


async def test_sse_connection():
    """Test the SSE connection manually."""
    print("🔍 Testing SSE connection manually...")

    url = "http://localhost:8000/sse"

    try:
        async with httpx.AsyncClient() as client, client.stream("GET", url) as response:
            print(f"📡 Connected to: {url}")
            print(f"📊 Status: {response.status_code}")
            print(f"📋 Headers: {dict(response.headers)}")
            print("🔄 Receiving events...\n")

            event_count = 0

            async for line in response.aiter_lines():
                if line.strip():
                    event_count += 1
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] Event {event_count}: {line}")

                    # Stop after getting a few events or timeout
                    if event_count > 20:
                        print("📊 Received enough events, stopping...")
                        break

            print(f"\n✅ Received {event_count} events total")

    except TimeoutError:
        print("⏰ Connection timed out")
    except httpx.RequestError as e:
        print(f"❌ Connection error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def test_basic_endpoints():
    """Test basic HTTP endpoints."""
    print("🔍 Testing basic endpoints...")

    endpoints = ["http://localhost:8000/", "http://localhost:8000/health", "http://localhost:8000/tools"]

    async with httpx.AsyncClient() as client:
        for url in endpoints:
            try:
                response = await client.get(url)
                data = response.json()
                print(f"✅ {url}: {response.status_code}")
                print(f"   Data: {json.dumps(data, indent=2)[:200]}...")
            except Exception as e:
                print(f"❌ {url}: {e}")


async def main():
    """Run all debug tests."""
    print("🎯 SSE Connection Debug Tool")
    print("=" * 40)

    # Test basic endpoints first
    await test_basic_endpoints()

    print("\n" + "=" * 40)

    # Test SSE connection
    await test_sse_connection()

    print("\n🎉 Debug complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Debug interrupted")
    except Exception as e:
        print(f"❌ Debug error: {e}")
