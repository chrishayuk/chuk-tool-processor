#!/usr/bin/env python
# examples/reliable_test_sse_server.py
"""
Reliable MCP-compliant SSE test server with guaranteed responses.

This server ensures every request gets a response and handles concurrent
requests properly. Designed for testing the SSE transport without timeouts.

Usage:
    python examples/reliable_test_sse_server.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
import logging
from typing import Any, Dict, List
from datetime import datetime

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("❌ FastAPI and uvicorn are required to run this test server.")
    print("Install them with: pip install fastapi uvicorn")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-mcp-server")

app = FastAPI(title="Reliable Test MCP SSE Server", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simplified connection management
active_connections: Dict[str, asyncio.Queue] = {}
initialized_sessions: set = set()

# Deterministic mock responses (no randomness to avoid flaky behavior)
MOCK_RESPONSES = {
    "perplexity_search": "This is a simulated conversational search result from the reliable test server. The response includes relevant information and context about the query.",
    
    "perplexity_deep_research": "This is a comprehensive research response from the reliable test server. It includes detailed analysis, multiple perspectives, and simulated citations. The research covers historical context, current developments, and future implications with extensive background information.",
    
    "perplexity_quick_fact": "Quick fact from reliable test server."
}

# MCP Tool definitions
TOOLS = [
    {
        "name": "perplexity_search",
        "description": "Quick conversational answer using Perplexity sonar-pro",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "User query to be answered briefly"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "perplexity_deep_research",
        "description": "Comprehensive, citation-rich answer using Perplexity sonar-deep-research",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "User query requiring in-depth research"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "perplexity_quick_fact",
        "description": "Ultra-fast fact checking using Perplexity sonar-pro",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Simple factual query"
                }
            },
            "required": ["query"]
        }
    }
]

@app.get("/")
async def root():
    """Root endpoint with server info."""
    return {
        "name": "Reliable Test MCP SSE Server",
        "version": "1.0.0",
        "description": "Guaranteed response MCP server for testing",
        "protocol": "MCP SSE",
        "tools": len(TOOLS),
        "active_connections": len(active_connections),
        "endpoints": {
            "sse": "/sse",
            "messages": "/messages/{session_id}"
        }
    }

@app.get("/sse")
async def sse_endpoint():
    """SSE endpoint - simplified and reliable."""
    session_id = str(uuid.uuid4()).replace("-", "")
    logger.info(f"New SSE connection: {session_id}")
    
    async def generate_events():
        # Create queue for this session
        queue = asyncio.Queue()
        active_connections[session_id] = queue
        logger.info(f"Session {session_id} queue created")
        
        # Send endpoint event immediately
        yield f"event: endpoint\n"
        yield f"data: /messages/?session_id={session_id}\n\n"
        logger.info(f"Sent endpoint event for session {session_id}")
        
        try:
            while True:
                try:
                    # Wait for messages with shorter timeout for responsiveness
                    message = await asyncio.wait_for(queue.get(), timeout=5.0)
                    logger.info(f"Sending response for session {session_id}: {message.get('id', 'no-id')}")
                    yield f"event: message\n"
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: heartbeat\n"
                    yield f"data: {json.dumps({'timestamp': datetime.now().isoformat()})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE connection {session_id} cancelled")
        except Exception as e:
            logger.error(f"SSE connection {session_id} error: {e}")
        finally:
            # Cleanup
            active_connections.pop(session_id, None)
            initialized_sessions.discard(session_id)
            logger.info(f"Session {session_id} cleaned up")
    
    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"
        }
    )

async def send_response_safely(session_id: str, response: dict):
    """Safely send response to session queue."""
    try:
        if session_id in active_connections:
            queue = active_connections[session_id]
            await queue.put(response)
            logger.info(f"Response queued for session {session_id}: {response.get('id', 'no-id')}")
            return True
        else:
            logger.warning(f"Session {session_id} not found for response")
            return False
    except Exception as e:
        logger.error(f"Failed to queue response for session {session_id}: {e}")
        return False

@app.post("/messages/")
async def handle_message(request: Request):
    """Handle MCP JSON-RPC messages with guaranteed responses."""
    # Get session ID
    session_id = request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")
    
    if session_id not in active_connections:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    
    try:
        message = await request.json()
        logger.info(f"Received message for session {session_id}: {message.get('method', 'no-method')} (id: {message.get('id', 'no-id')})")
    except Exception as e:
        logger.error(f"Invalid JSON from session {session_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    method = message.get("method")
    msg_id = message.get("id")
    
    # Schedule response sending (don't block HTTP response)
    asyncio.create_task(process_message(session_id, method, msg_id, message))
    
    return JSONResponse(content="Accepted", status_code=202)

async def process_message(session_id: str, method: str, msg_id: str, message: dict):
    """Process message and send response asynchronously."""
    try:
        # Small delay to simulate processing (but keep it short)
        await asyncio.sleep(0.05)  # Even shorter delay
        
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {},
                        "prompts": {},
                        "experimental": {}
                    },
                    "serverInfo": {
                        "name": "reliable-test-mcp-server",
                        "version": "1.0.0"
                    }
                }
            }
            initialized_sessions.add(session_id)
            logger.info(f"Session {session_id} initialized")
            
        elif method == "notifications/initialized":
            # No response needed for notifications
            logger.info(f"Session {session_id} sent initialized notification")
            return
            
        elif method == "tools/list":
            if session_id not in initialized_sessions:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32600,
                        "message": "Session not initialized"
                    }
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": TOOLS
                    }
                }
            
        elif method == "tools/call":
            if session_id not in initialized_sessions:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32600,
                        "message": "Session not initialized"
                    }
                }
            else:
                params = message.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                query = arguments.get("query", "")
                
                # Log the specific request for debugging
                logger.info(f"Processing tool call {msg_id}: {tool_name} with query: '{query[:50]}...'")
                
                # Generate deterministic response based on tool
                if tool_name in MOCK_RESPONSES:
                    # Include request ID in response for correlation tracking
                    result_text = f"{MOCK_RESPONSES[tool_name]} [Request ID: {msg_id}] Query: '{query}'"
                    
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": result_text
                                }
                            ]
                        }
                    }
                    logger.info(f"Generated response for tool {tool_name} (request {msg_id})")
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found"
                        }
                    }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found"
                }
            }
        
        # Send the response
        success = await send_response_safely(session_id, response)
        if success:
            logger.info(f"Response sent successfully for {method} (id: {msg_id})")
        else:
            logger.error(f"Failed to send response for {method} (id: {msg_id})")
            
    except Exception as e:
        logger.error(f"Error processing message {method}: {e}")
        # Send error response
        error_response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }
        await send_response_safely(session_id, error_response)

def main():
    """Run the reliable test server."""
    print("🚀 Starting Reliable Test MCP SSE Server...")
    print("📡 Server will be available at: http://localhost:8000")
    print("🔧 Available tools:")
    for tool in TOOLS:
        print(f"   - {tool['name']}: {tool['description']}")
    print("✅ This server guarantees responses to all requests")
    print("💡 Use Ctrl+C to stop the server")
    print()
    
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="warning",  # Reduce uvicorn noise
            access_log=False
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped")

if __name__ == "__main__":
    main()