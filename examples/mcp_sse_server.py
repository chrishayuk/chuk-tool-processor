#!/usr/bin/env python
"""
mcp_sse_server.py - MCP-Compliant SSE Server
──────────────────────────────────────────────────────
A proper MCP SSE server that follows the MCP protocol correctly
and works with chuk-mcp SSE clients.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_sse_server")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MCP server state
class MCPServerState:
    def __init__(self):
        self.sessions = {}
        self.server_info = {
            "name": "mcp-sse-demo-server",
            "version": "1.0.0"
        }
        self.capabilities = {
            "tools": {"listChanged": True},
            "resources": {"listChanged": True},
            "prompts": {"listChanged": True}
        }
        self.tools = [
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
            },
            {
                "name": "hello",
                "description": "Say hello to someone",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name to greet"}
                    },
                    "required": ["name"]
                }
            }
        ]

state = MCPServerState()

@app.get("/")
async def root():
    return {
        "name": "MCP SSE Demo Server",
        "protocol": "MCP over SSE",
        "version": "1.0.0",
        "endpoints": {
            "sse": "/sse",
            "messages": "/mcp"
        }
    }

@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint that provides the message endpoint URL."""
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    # Initialize session
    state.sessions[session_id] = {
        "id": session_id,
        "created": datetime.now().isoformat(),
        "initialized": False
    }
    
    logger.info(f"New SSE session: {session_id}")
    
    async def event_stream():
        try:
            # Send the message endpoint URL (must end with /mcp for MCP protocol compliance)
            endpoint_url = f"/mcp?session_id={session_id}"
            yield f"event: endpoint\n"
            yield f"data: {endpoint_url}\n\n"
            logger.info(f"Sent endpoint URL: {endpoint_url}")
            
            # Keep connection alive with periodic pings
            while True:
                await asyncio.sleep(30)
                ping_data = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": session_id
                }
                yield f"event: ping\n"
                yield f"data: {json.dumps(ping_data)}\n\n"
                
        except asyncio.CancelledError:
            logger.info(f"SSE connection closed for session {session_id}")
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
        finally:
            # Clean up session
            if session_id in state.sessions:
                del state.sessions[session_id]
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )

@app.post("/mcp")
async def handle_mcp_message(request: Request):
    """Handle MCP JSON-RPC messages via standard /mcp endpoint."""
    
    session_id = request.query_params.get("session_id")
    if not session_id or session_id not in state.sessions:
        return {"error": "Invalid or missing session_id"}
    
    session = state.sessions[session_id]
    
    try:
        message = await request.json()
        logger.info(f"Received message: {message.get('method')} (session: {session_id})")
        
        response = await handle_mcp_protocol_message(message, session)
        if response:
            logger.info(f"Sending response: {response.get('result', response.get('error'))}")
            return response
        else:
            # Notification - no response
            return {"status": "accepted"}
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        return {
            "jsonrpc": "2.0",
            "id": message.get("id") if 'message' in locals() else None,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }

async def handle_mcp_protocol_message(message: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP protocol messages according to the spec."""
    
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
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": state.capabilities,
                    "serverInfo": state.server_info,
                    "instructions": f"MCP SSE Demo Server - Session: {session['id']}"
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
            
            if tool_name == "perplexity_search":
                query = arguments.get("query", "")
                result = {
                    "answer": f"Mock Perplexity search result for: {query}",
                    "sources": ["https://example1.com", "https://example2.com"],
                    "timestamp": datetime.now().isoformat()
                }
                
            elif tool_name == "perplexity_deep_research":
                query = arguments.get("query", "")
                result = {
                    "analysis": f"Mock deep research for: {query}",
                    "findings": ["Finding 1", "Finding 2", "Finding 3"],
                    "timestamp": datetime.now().isoformat()
                }
                
            elif tool_name == "perplexity_quick_fact":
                query = arguments.get("query", "")
                result = {
                    "fact": f"Mock quick fact: {query}",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat()
                }
                
            elif tool_name == "hello":
                name = arguments.get("name", "World")
                result = f"Hello, {name}! This is from the MCP SSE server."
                
            else:
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
                }
            
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result) if isinstance(result, dict) else result}]
                }
            }
        
        elif method == "resources/list":
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "resources": [
                        {
                            "uri": "sse://server-status",
                            "name": "Server Status",
                            "description": "Current SSE server status"
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
                            "name": "search_prompt",
                            "description": "Generate a search prompt",
                            "arguments": [
                                {"name": "topic", "description": "Search topic", "required": True}
                            ]
                        }
                    ]
                }
            }
    
    except Exception as e:
        logger.error(f"Error in handle_mcp_protocol_message: {e}")
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
        "active_sessions": len(state.sessions)
    }

if __name__ == "__main__":
    print("🌊 MCP-Compliant SSE Server")
    print("=" * 50)
    print("📡 Server: http://localhost:8000")
    print("🔗 SSE: http://localhost:8000/sse")
    print("📬 Messages: http://localhost:8000/mcp")
    print("🛠️  Tools available:")
    for tool in state.tools:
        print(f"   • {tool['name']}: {tool['description']}")
    print("=" * 50)
    print("🚀 Starting server...\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    )