#!/usr/bin/env python
"""
mcp_streamable_http_server.py - MCP Streamable HTTP Server
──────────────────────────────────────────────────────────
A proper MCP Streamable HTTP server that follows the 2025-03-26 spec.

This implements the modern single-endpoint approach with optional streaming.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_streamable_http_server")

app = FastAPI()

# Enhanced CORS for MCP compatibility  
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# MCP server state
class MCPServerState:
    def __init__(self):
        self.sessions = {}
        self.server_info = {
            "name": "mcp-streamable-http-demo-server",
            "version": "1.0.0"
        }
        self.capabilities = {
            "tools": {"listChanged": True},
            "resources": {"listChanged": True},
            "prompts": {"listChanged": True}
        }
        self.tools = [
            {
                "name": "http_greet",
                "description": "Greet someone via Streamable HTTP",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name to greet"},
                        "style": {"type": "string", "description": "Greeting style", "enum": ["formal", "casual"], "default": "casual"}
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "session_info",
                "description": "Get current session information",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "http_counter",
                "description": "Increment session counter",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "increment": {"type": "integer", "default": 1}
                    }
                }
            },
            {
                "name": "slow_operation",
                "description": "A deliberately slow operation to demonstrate streaming",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "duration": {"type": "integer", "description": "Duration in seconds", "default": 3}
                    }
                }
            }
        ]

state = MCPServerState()

@app.get("/")
async def root():
    return {
        "name": "MCP Streamable HTTP Demo Server",
        "protocol": "MCP over Streamable HTTP",
        "version": "1.0.0",
        "spec_version": "2025-03-26",
        "endpoints": {
            "mcp": "/mcp"
        },
        "features": [
            "Single endpoint simplicity",
            "Better infrastructure compatibility", 
            "Stateless operation support",
            "Optional streaming when needed"
        ]
    }

@app.post("/mcp")
@app.get("/mcp")
async def mcp_endpoint(request: Request, response: Response):
    """
    Main MCP endpoint for Streamable HTTP transport.
    
    Supports both immediate JSON responses and streaming SSE responses
    based on the client's Accept header and the complexity of the operation.
    """
    
    # Get or create session
    session_id = request.headers.get("mcp-session-id")
    if not session_id or session_id not in state.sessions:
        session_id = str(uuid.uuid4())
        state.sessions[session_id] = {
            "id": session_id,
            "created": datetime.now().isoformat(),
            "counter": 0,
            "messages": [],
            "initialized": False
        }
        logger.info(f"Created new session: {session_id}")
    
    # Set session ID in response
    response.headers["Mcp-Session-Id"] = session_id
    
    session = state.sessions[session_id]
    
    if request.method == "GET":
        # GET request - initiate streaming if requested
        accept_header = request.headers.get("accept", "")
        if "text/event-stream" in accept_header:
            logger.info(f"Starting SSE stream for session {session_id}")
            return StreamingResponse(
                _create_sse_stream(session),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive", 
                    "Access-Control-Allow-Origin": "*",
                }
            )
        else:
            # Regular GET - return server info
            return {
                "server": state.server_info,
                "session": session_id,
                "transport": "streamable_http",
                "spec_version": "2025-03-26"
            }
    
    elif request.method == "POST":
        # POST request - handle MCP message
        try:
            message = await request.json()
            method = message.get("method")
            msg_id = message.get("id")
            
            logger.info(f"Received: {method} (session: {session_id})")
            
            # Check if client accepts streaming
            accept_header = request.headers.get("accept", "")
            supports_streaming = "text/event-stream" in accept_header
            
            # Determine response strategy
            use_streaming = supports_streaming and _should_use_streaming(method, message)
            
            if use_streaming:
                # Return streaming SSE response
                logger.info(f"Using streaming response for {method}")
                return StreamingResponse(
                    _create_streaming_response(message, session),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                    }
                )
            else:
                # Return immediate JSON response
                logger.info(f"Using immediate JSON response for {method}")
                mcp_response = await handle_mcp_message(message, session)
                
                if mcp_response:
                    return JSONResponse(content=mcp_response)
                else:
                    # Notification - no response content
                    return JSONResponse(content={"status": "accepted"}, status_code=202)
                    
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if 'message' in locals() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
            return JSONResponse(content=error_response, status_code=500)

def _should_use_streaming(method: str, message: Dict[str, Any]) -> bool:
    """
    Determine if a request should use streaming response.
    
    This is where the server decides between immediate JSON vs SSE streaming.
    """
    # Use streaming for potentially long-running operations
    streaming_methods = [
        "tools/call",  # Tool calls might take time
        "resources/read",  # Large resources
        "prompts/get",  # Complex prompts
    ]
    
    # For demo purposes, we'll stream some operations
    return method in streaming_methods

async def _create_sse_stream(session: Dict[str, Any]):
    """Create an SSE stream for GET requests."""
    try:
        # Send welcome message
        welcome = {
            "type": "welcome",
            "session_id": session["id"],
            "timestamp": datetime.now().isoformat()
        }
        yield f"event: welcome\n"
        yield f"data: {json.dumps(welcome)}\n\n"
        
        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            ping = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            yield f"event: ping\n"
            yield f"data: {json.dumps(ping)}\n\n"
            
    except Exception as e:
        logger.info(f"SSE stream ended: {e}")

async def _create_streaming_response(message: Dict[str, Any], session: Dict[str, Any]):
    """Create a streaming SSE response for complex operations."""
    
    try:
        # Process the message
        mcp_response = await handle_mcp_message(message, session)
        
        if mcp_response:
            # Send the response as SSE
            yield f"event: message\n"
            yield f"data: {json.dumps(mcp_response)}\n\n"
        
        # Optional: Send completion event
        completion_event = {
            "type": "completion",
            "timestamp": datetime.now().isoformat()
        }
        yield f"event: completion\n"
        yield f"data: {json.dumps(completion_event)}\n\n"
        
    except Exception as e:
        # Send error via SSE
        error_response = {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32603, "message": f"Stream error: {str(e)}"}
        }
        yield f"event: error\n"
        yield f"data: {json.dumps(error_response)}\n\n"

async def handle_mcp_message(message: Dict[str, Any], session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle MCP protocol messages."""
    
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params", {})
    
    try:
        if method == "initialize":
            session["initialized"] = True
            session["client_info"] = params.get("clientInfo", {})
            
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2025-03-26"),
                    "capabilities": state.capabilities,
                    "serverInfo": state.server_info,
                    "instructions": f"Streamable HTTP MCP Server - Session: {session['id']}"
                }
            }
        
        elif method == "notifications/initialized":
            logger.info(f"Client initialization complete for session {session['id']}")
            return None
        
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": state.tools}
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "http_greet":
                name = arguments.get("name", "Anonymous")
                style = arguments.get("style", "casual")
                
                if style == "formal":
                    greeting = f"🌐 Good day, {name}. Welcome to our Streamable HTTP MCP server."
                else:
                    greeting = f"🌐 Hey {name}! Welcome to the HTTP MCP server! 🚀"
                
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": greeting}]
                    }
                }
            
            elif tool_name == "session_info":
                info = {
                    "session_id": session["id"],
                    "created": session["created"],
                    "counter": session["counter"],
                    "transport": "streamable_http",
                    "initialized": session["initialized"],
                    "total_sessions": len(state.sessions),
                    "spec_version": "2025-03-26"
                }
                
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"📊 Session Info: {json.dumps(info, indent=2)}"}]
                    }
                }
            
            elif tool_name == "http_counter":
                increment = arguments.get("increment", 1)
                session["counter"] += increment
                
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"🔢 HTTP Counter: {session['counter']} (+{increment})"}]
                    }
                }
            
            elif tool_name == "slow_operation":
                duration = arguments.get("duration", 3)
                
                # Simulate slow operation
                await asyncio.sleep(duration)
                
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"⏱️ Slow operation completed after {duration} seconds via HTTP transport"}]
                    }
                }
        
        elif method == "resources/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "resources": [
                        {
                            "uri": "http://server-status",
                            "name": "HTTP Server Status",
                            "description": "Current Streamable HTTP server status",
                            "mimeType": "application/json"
                        }
                    ]
                }
            }
        
        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "prompts": [
                        {
                            "name": "http_status_report",
                            "description": "Generate a Streamable HTTP status report",
                            "arguments": [
                                {"name": "detail_level", "description": "Level of detail", "required": False}
                            ]
                        }
                    ]
                }
            }
    
    except Exception as e:
        logger.error(f"Error in handle_mcp_message: {e}")
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }
    
    return {
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(state.sessions),
        "transport": "streamable_http"
    }

if __name__ == "__main__":
    print("🌐 MCP Streamable HTTP Server")
    print("=" * 60)
    print("📡 Modern MCP transport (spec 2025-03-26)")
    print("🔗 Single endpoint: http://localhost:8000/mcp")
    print("✅ Supports both immediate JSON and streaming SSE responses")
    print("🚀 Replaces deprecated SSE transport")
    print("-" * 60)
    print(f"🛠️  Tools available:")
    for tool in state.tools:
        print(f"   • {tool['name']}: {tool['description']}")
    print("=" * 60)
    print("🚀 Starting server...\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )