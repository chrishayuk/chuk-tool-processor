#!/usr/bin/env python
"""
mcp_sse_server.py - FIXED MCP-Compliant SSE Server
─────────────────────────────────────────────────────
A proper MCP SSE server that follows the MCP protocol correctly
and works with chuk-mcp SSE clients.

FIXES:
- Proper session ID handling in /mcp endpoint
- Better error handling and logging
- Session validation improvements
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
        "name": "MCP SSE Demo Server (FIXED)",
        "protocol": "MCP over SSE",
        "version": "1.0.0",
        "endpoints": {
            "sse": "/sse",
            "messages": "/mcp"
        },
        "active_sessions": len(state.sessions)
    }

@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint that provides the message endpoint URL."""
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    # Initialize session BEFORE starting the stream
    state.sessions[session_id] = {
        "id": session_id,
        "created": datetime.now().isoformat(),
        "initialized": False,
        "last_activity": datetime.now().isoformat()
    }
    
    logger.info(f"🆕 New SSE session created: {session_id}")
    logger.info(f"📊 Total sessions now: {len(state.sessions)}")
    
    async def event_stream():
        try:
            # Send the message endpoint URL (must end with /mcp for MCP protocol compliance)
            endpoint_url = f"/mcp?session_id={session_id}"
            yield f"event: endpoint\n"
            yield f"data: {endpoint_url}\n\n"
            logger.info(f"📡 Sent endpoint URL to client: {endpoint_url}")
            
            # Give a moment for the client to process the endpoint
            await asyncio.sleep(0.1)
            
            # Keep connection alive with periodic pings
            while True:
                await asyncio.sleep(30)
                # Check if session still exists before sending ping
                if session_id in state.sessions:
                    ping_data = {
                        "timestamp": datetime.now().isoformat(),
                        "session_id": session_id,
                        "active_sessions": len(state.sessions)
                    }
                    yield f"event: ping\n"
                    yield f"data: {json.dumps(ping_data)}\n\n"
                    logger.debug(f"📡 Ping sent to session {session_id}")
                else:
                    logger.warning(f"⚠️ Session {session_id} no longer exists, stopping SSE")
                    break
                
        except asyncio.CancelledError:
            logger.info(f"🔌 SSE connection closed for session {session_id}")
        except Exception as e:
            logger.error(f"❌ Error in SSE stream: {e}")
        # NOTE: Don't clean up session here - let it persist for MCP calls
    
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
    
    # FIXED: Get session_id from query parameters
    session_id = request.query_params.get("session_id")
    
    # Improved logging
    logger.info(f"📨 Received MCP request for session: {session_id}")
    
    if not session_id:
        logger.error("❌ No session_id provided in request")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32602, "message": "Missing session_id parameter"}
        }
    
    if session_id not in state.sessions:
        logger.error(f"❌ Invalid session_id: {session_id}")
        logger.info(f"📊 Active sessions: {list(state.sessions.keys())}")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32602, "message": f"Invalid session_id: {session_id}"}
        }
    
    session = state.sessions[session_id]
    
    # Update last activity
    session["last_activity"] = datetime.now().isoformat()
    
    try:
        message = await request.json()
        method = message.get('method', 'unknown')
        msg_id = message.get('id')
        
        logger.info(f"🔄 Processing method: {method} (id: {msg_id}, session: {session_id})")
        
        response = await handle_mcp_protocol_message(message, session)
        if response:
            logger.info(f"✅ Sending response for method: {method}")
            return response
        else:
            # Notification - no response
            logger.info(f"📢 Notification processed: {method}")
            return {"status": "accepted"}
            
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in request: {e}")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"}
        }
    except Exception as e:
        logger.error(f"❌ Error handling message: {e}")
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
    
    logger.debug(f"🔍 Handling protocol message: {method}")
    
    try:
        if method == "initialize":
            session["initialized"] = True
            session["client_info"] = params.get("clientInfo", {})
            
            logger.info(f"🚀 Client initialized: {session['client_info'].get('name', 'unknown')}")
            
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
            logger.info(f"✅ Client initialization complete for session {session['id']}")
            return None
        
        elif method == "ping":
            logger.debug(f"🏓 Ping from session {session['id']}")
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        
        elif method == "tools/list":
            logger.info(f"🛠️  Tools list requested by session {session['id']}")
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": state.tools}
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            logger.info(f"🔧 Tool call: {tool_name} by session {session['id']}")
            
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
                result = f"Hello, {name}! This is from the MCP SSE server (session: {session['id'][:8]})."
                
            else:
                logger.warning(f"⚠️ Unknown tool requested: {tool_name}")
                return {
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
                }
            
            logger.info(f"✅ Tool {tool_name} executed successfully")
            
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result) if isinstance(result, dict) else result}]
                }
            }
        
        elif method == "resources/list":
            logger.info(f"📁 Resources list requested by session {session['id']}")
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
            logger.info(f"💬 Prompts list requested by session {session['id']}")
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
        logger.error(f"❌ Error in handle_mcp_protocol_message: {e}")
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }
    
    logger.warning(f"⚠️ Method not found: {method}")
    return {
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }

@app.get("/health")
async def health():
    # Clean up old sessions (older than 2 hours instead of 1)
    current_time = datetime.now()
    old_sessions = []
    
    for session_id, session_data in state.sessions.items():
        try:
            last_activity = datetime.fromisoformat(session_data.get('last_activity', session_data['created']))
            if (current_time - last_activity).total_seconds() > 7200:  # 2 hours
                old_sessions.append(session_id)
        except:
            old_sessions.append(session_id)  # Remove invalid sessions
    
    for session_id in old_sessions:
        del state.sessions[session_id]
        logger.info(f"🗑️  Cleaned up old session: {session_id}")
    
    return {
        "status": "healthy",
        "timestamp": current_time.isoformat(),
        "active_sessions": len(state.sessions),
        "sessions_cleaned": len(old_sessions)
    }

@app.get("/debug/sessions")
async def debug_sessions():
    """Debug endpoint to view active sessions."""
    return {
        "total_sessions": len(state.sessions),
        "sessions": {
            session_id: {
                "created": data["created"],
                "initialized": data.get("initialized", False),
                "last_activity": data.get("last_activity", data["created"]),
                "client_info": data.get("client_info", {})
            }
            for session_id, data in state.sessions.items()
        }
    }

if __name__ == "__main__":
    print("🌊 MCP-Compliant SSE Server (FIXED VERSION)")
    print("=" * 50)
    print("📡 Server: http://localhost:8020")
    print("🔗 SSE: http://localhost:8020/sse")
    print("📬 Messages: http://localhost:8020/mcp")
    print("🔍 Debug: http://localhost:8020/debug/sessions")
    print("🛠️  Tools available:")
    for tool in state.tools:
        print(f"   • {tool['name']}: {tool['description']}")
    print("=" * 50)
    print("🔧 FIXES APPLIED:")
    print("   • Session persists after SSE connection")
    print("   • Removed session cleanup from SSE stream")
    print("   • Better session validation and logging")
    print("   • Extended session lifetime to 2 hours")
    print("   • Added session existence checks")
    print("=" * 50)
    print("🚀 Starting server...\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8020,
        log_level="info"
    )