#!/usr/bin/env python3
"""Debug version with verbose logging."""
import asyncio
import logging
import sys

# Enable ALL debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)

# Test just the HTTP POST to see what Notion returns
import httpx

async def test_notion_response():
    """Test what Notion actually returns."""
    token = "282c6a79-d66f-402e-a1b2-6884ecd368d6"  # From the test run
    
    url = "https://mcp.notion.com/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}"
    }
    
    message = {
        "jsonrpc": "2.0",
        "id": "test-123",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    }
    
    print(f"Sending POST to {url}")
    print(f"Headers: {headers}")
    print(f"Body: {message}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=message, headers=headers)
        
        print(f"\nResponse status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"\nResponse body ({len(response.text)} bytes):")
        print(response.text[:500])
        
        if response.text:
            print("\n First few bytes (hex):", response.content[:50].hex())

if __name__ == "__main__":
    asyncio.run(test_notion_response())
