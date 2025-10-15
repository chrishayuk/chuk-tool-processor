#!/usr/bin/env python3
"""Check what content-type Notion returns."""
import asyncio
import httpx

async def test():
    # Use the fresh token from the last run (you'll need to update this)
    token = input("Enter the access token from the OAuth flow: ").strip()
    
    url = "https://mcp.notion.com/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}"
    }
    
    message = {
        "jsonrpc": "2.0",
        "id": "test-ping",
        "method": "ping"
    }
    
    print(f"Sending ping to {url}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=message, headers=headers)
        
        print(f"\nStatus: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"\nResponse body ({len(response.text)} bytes):")
        print(response.text)

if __name__ == "__main__":
    asyncio.run(test())
