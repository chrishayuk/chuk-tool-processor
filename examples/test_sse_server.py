#!/usr/bin/env python
"""
test_sse_server.py - INSTANT RESPONSE VERSION
─────────────────────────────────────────────
SSE server that sends events immediately without any delays.

The issue might be that the MCP client has a very short timeout and needs
events to be sent instantly upon connection.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instant_sse_server")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tools definition
TOOLS = [
    {
        "name": "perplexity_search",
        "description": "Search using Perplexity AI (mock)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "perplexity_deep_research", 
        "description": "Deep research with Perplexity AI (mock)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "perplexity_quick_fact",
        "description": "Quick facts from Perplexity AI (mock)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Fact query"}
            },
            "required": ["query"]
        }
    }
]


def create_sse_event(data: Dict[str, Any]) -> str:
    """Create an SSE event with proper formatting."""
    json_str = json.dumps(data, separators=(',', ':'))  # Compact JSON
    return f"data: {json_str}\n\n"


async def instant_events_generator() -> AsyncGenerator[str, None]:
    """Generate all events instantly upon connection."""
    logger.info("SSE client connected - sending instant events")
    
    # Send all events immediately in sequence without any delays
    
    # 1. Initialization response
    init_msg = {
        "jsonrpc": "2.0",
        "id": "init",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "mock_perplexity_server", 
                "version": "1.0.0"
            }
        }
    }
    yield create_sse_event(init_msg)
    logger.info("✅ Sent init")
    
    # 2. Tools list notification
    tools_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed",
        "params": {}
    }
    yield create_sse_event(tools_notification)
    logger.info("✅ Sent tools notification")
    
    # 3. Tools list response  
    tools_response = {
        "jsonrpc": "2.0",
        "id": "tools_list",
        "result": {"tools": TOOLS}
    }
    yield create_sse_event(tools_response)
    logger.info("✅ Sent tools list")
    
    # 4. Ready signal
    ready_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/ready", 
        "params": {
            "timestamp": datetime.now().isoformat()
        }
    }
    yield create_sse_event(ready_notification)
    logger.info("✅ Sent ready signal")
    
    logger.info("🎉 All events sent instantly")
    
    # Keep connection alive (this part can have delays)
    try:
        import asyncio
        while True:
            await asyncio.sleep(60)  # Long interval for keepalive
            ping = {
                "jsonrpc": "2.0",
                "method": "notifications/ping",
                "params": {"timestamp": datetime.now().isoformat()}
            }
            yield create_sse_event(ping)
    except Exception as e:
        logger.info(f"SSE connection ended: {e}")


@app.get("/")
async def root():
    return {
        "name": "Instant SSE Server",
        "status": "running", 
        "protocol": "JSON-RPC 2.0 over SSE (instant)",
        "tools": len(TOOLS)
    }


@app.get("/sse")
async def sse_endpoint():
    """SSE endpoint that sends events instantly."""
    logger.info("🚀 SSE endpoint hit - starting instant event stream")
    
    return StreamingResponse(
        instant_events_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache", 
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.get("/tools")
async def get_tools():
    return {"tools": TOOLS}


@app.post("/call/{tool_name}")
async def call_tool(tool_name: str, arguments: Dict[str, Any]):
    """Handle tool calls with instant responses."""
    logger.info(f"🔧 Tool call: {tool_name}")
    
    tool = next((t for t in TOOLS if t["name"] == tool_name), None)
    if not tool:
        return {"isError": True, "error": f"Tool {tool_name} not found"}
    
    # Generate instant mock response (no delay)
    query = arguments.get("query", "")
    
    if "search" in tool_name:
        result = {
            "answer": f"Instant mock search result for: {query}",
            "sources": ["https://example.com/instant1", "https://example.com/instant2"],
            "timestamp": datetime.now().isoformat()
        }
    elif "research" in tool_name:
        result = {
            "analysis": f"Instant mock research for: {query}",
            "findings": ["Instant insight 1", "Quick trend 2", "Fast implication 3"],
            "timestamp": datetime.now().isoformat()
        }
    elif "fact" in tool_name:
        result = {
            "fact": f"Instant mock fact about: {query}",
            "confidence": 0.95,
            "timestamp": datetime.now().isoformat()
        }
    else:
        result = {"response": f"Instant mock response for {query}"}
    
    return {"isError": False, "content": result}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    print("⚡ Instant SSE Server")
    print("📡 http://localhost:8000")
    print("🔗 SSE: http://localhost:8000/sse")
    print("⚡ Events sent instantly upon connection")
    print(f"🛠️  {len(TOOLS)} mock tools available")
    print("🛑 Ctrl+C to stop\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1", 
        port=8000,
        log_level="info"
    )