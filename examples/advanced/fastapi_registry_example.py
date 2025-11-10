#!/usr/bin/env python
# examples/fastapi_registry_example.py
"""
FastAPI Application using the async-native tool registry.

This example shows:
1. Integration with FastAPI
2. Async registry initialization during app startup
3. Tool discovery and execution via API endpoints
4. Streaming response support
5. Automatic API documentation using tool metadata
"""

import asyncio
import logging
import os
import signal
import sys
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from chuk_tool_processor import (
    ensure_registrations,
    get_default_registry,
    initialize,
    register_tool,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tool-api")

# Filter runtime warnings
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")


# ----------------------------------------
# Define FastAPI lifespan context manager
# ----------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize registry on startup
    logger.info("Initializing tool registry...")
    registry = await initialize()
    await ensure_registrations()  # Ensure all tools are registered

    # Log discovered tools
    tools = await registry.list_tools()
    logger.info(f"Registry initialized with {len(tools)} tools")
    for namespace, name in tools:
        logger.info(f"Tool available: {namespace}.{name}")

    yield  # Give control back to FastAPI

    # Simple cleanup logic
    logger.info("Application shutting down...")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Tool Registry API",
    description="API for executing tools from the async-native registry",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------------------
# Define some example tools
# ----------------------------------------


@register_tool(name="weather", namespace="api", description="Get weather for a location")
class WeatherTool:
    """Get current weather for a city."""

    async def execute(self, city: str, units: str = "metric") -> dict[str, Any]:
        """
        Get simulated weather data for a city.

        Args:
            city: City name
            units: Units system (metric/imperial)

        Returns:
            Weather data object
        """
        # Simulate network delay
        await asyncio.sleep(0.5)

        # Simulate weather data
        import random

        temp = random.uniform(15, 30)  # celsius
        if units == "imperial":
            temp = temp * 9 / 5 + 32  # convert to fahrenheit

        return {
            "city": city,
            "temperature": round(temp, 1),
            "units": "C" if units == "metric" else "F",
            "conditions": random.choice(["Sunny", "Cloudy", "Rainy", "Windy"]),
            "humidity": random.randint(30, 90),
            "timestamp": datetime.now().isoformat(),
        }


@register_tool(name="translate", namespace="api", description="Translate text")
class TranslateTool:
    """Translate text between languages."""

    async def execute(self, text: str, source_lang: str = "en", target_lang: str = "es") -> dict[str, str]:
        """
        Simulate translating text between languages.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Dictionary with original and translated text
        """
        # Simulate processing time
        await asyncio.sleep(0.3)

        # Very basic "translation" for demo purposes
        translations = {
            "en-es": {"hello": "hola", "world": "mundo", "thanks": "gracias"},
            "en-fr": {"hello": "bonjour", "world": "monde", "thanks": "merci"},
            "en-de": {"hello": "hallo", "world": "welt", "thanks": "danke"},
        }

        lang_pair = f"{source_lang}-{target_lang}"
        if lang_pair not in translations:
            return {
                "original": text,
                "translated": text,  # Just echo back for unsupported languages
                "source_lang": source_lang,
                "target_lang": target_lang,
            }

        # Very simplistic word substitution (for demo only)
        translated = text.lower()
        for eng, foreign in translations[lang_pair].items():
            translated = translated.replace(eng, foreign)

        return {"original": text, "translated": translated, "source_lang": source_lang, "target_lang": target_lang}


@register_tool(name="stream_logs", namespace="api", supports_streaming=True)
class StreamLogsTool:
    """Stream simulated log entries."""

    async def execute(self, lines: int = 10, interval: float = 0.5) -> list[str]:
        """
        Generate a stream of log entries.

        Args:
            lines: Number of log lines to generate
            interval: Delay between lines in seconds

        Returns:
            List of log entries (for non-streaming usage)
        """
        import random

        log_levels = ["INFO", "DEBUG", "WARNING", "ERROR"]
        services = ["api", "database", "auth", "worker"]
        messages = [
            "Request processed",
            "Connection established",
            "Cache hit",
            "Cache miss",
            "Rate limit reached",
            "Authentication successful",
            "Request validation failed",
            "Database query executed",
        ]

        results = []
        for i in range(lines):
            timestamp = datetime.now().isoformat()
            level = random.choice(log_levels)
            service = random.choice(services)
            message = random.choice(messages)
            log_entry = f"[{timestamp}] {level} {service}: {message} (event {i + 1})"

            results.append(log_entry)

            # In real streaming implementation, this would yield each result
            await asyncio.sleep(interval)

        return results


# ----------------------------------------
# Pydantic models for API requests/responses
# ----------------------------------------


class ToolExecuteRequest(BaseModel):
    """Generic model for tool execution request."""

    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolInfo(BaseModel):
    """Information about a registered tool."""

    name: str = Field(..., description="Tool name")
    namespace: str = Field(..., description="Tool namespace")
    description: str | None = Field(None, description="Tool description")
    supports_streaming: bool = Field(False, description="Whether tool supports streaming")
    tags: list[str] = Field(default_factory=list, description="Tool tags")
    argument_schema: dict[str, Any] | None = Field(None, description="Argument schema")


# ----------------------------------------
# FastAPI dependency for registry access
# ----------------------------------------


async def get_registry():
    """Dependency for accessing the registry."""
    registry = await get_default_registry()
    return registry


# ----------------------------------------
# API endpoints
# ----------------------------------------


@app.get("/", include_in_schema=False)
async def root():
    """Redirect to docs."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/docs")


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools(
    namespace: str | None = Query(None, description="Filter by namespace"), registry=Depends(get_registry)
):
    """List all registered tools."""
    # Get all tool metadata
    if namespace:
        metadata_list = await registry.list_metadata(namespace=namespace)
    else:
        metadata_list = await registry.list_metadata()

    # Convert to response format
    tools = []
    for meta in metadata_list:
        tool_info = ToolInfo(
            name=meta.name,
            namespace=meta.namespace,
            description=meta.description,
            supports_streaming=getattr(meta, "supports_streaming", False),
            tags=list(meta.tags) if meta.tags else [],
            argument_schema=meta.argument_schema,
        )
        tools.append(tool_info)

    return tools


@app.post("/tools/{namespace}/{name}/execute")
async def execute_tool(
    namespace: str,
    name: str,
    request: ToolExecuteRequest,
    stream: bool = Query(False, description="Stream the response if tool supports it"),
    registry=Depends(get_registry),
):
    """Execute a tool by namespace and name."""
    # Check if tool exists
    tool_impl = await registry.get_tool(name, namespace)
    if not tool_impl:
        raise HTTPException(status_code=404, detail=f"Tool {namespace}.{name} not found")

    # Get metadata
    metadata = await registry.get_metadata(name, namespace)

    try:
        # Instantiate the tool
        tool = tool_impl()

        # Check for streaming support
        supports_streaming = getattr(metadata, "supports_streaming", False)
        if stream and supports_streaming:
            # Execute in streaming mode
            return StreamingResponse(stream_tool_results(tool, request.arguments), media_type="text/event-stream")
        else:
            # Execute normally
            result = await tool.execute(**request.arguments)
            return JSONResponse(content={"result": result})

    except Exception as e:
        logger.exception(f"Error executing {namespace}.{name}")
        raise HTTPException(status_code=500, detail=str(e))


async def stream_tool_results(tool, arguments):
    """Generator for streaming tool results."""
    try:
        # Start execution
        results = await tool.execute(**arguments)

        # Stream each result
        for item in results:
            # Format as Server-Sent Event
            yield f"data: {item}\n\n"
            await asyncio.sleep(0.01)  # Small delay to ensure chunking

        # End of stream
        yield "event: complete\ndata: Stream complete\n\n"

    except Exception as e:
        # Send error event
        error_msg = f"Error: {str(e)}"
        yield f"event: error\ndata: {error_msg}\n\n"


@app.get("/namespaces")
async def list_namespaces(registry=Depends(get_registry)):
    """List all tool namespaces."""
    namespaces = await registry.list_namespaces()
    return {"namespaces": namespaces}


# ----------------------------------------
# Terminate handler for clean shutdown
# ----------------------------------------
def signal_handler(sig, frame):
    """Handle termination signals with minimal processing."""
    # Avoid using any logging functions to prevent reentrant calls
    print(f"\nExiting due to signal ({signal.Signals(sig).name})", file=sys.stderr)
    os._exit(0)  # Exit immediately without more processing


# Register signal handlers for direct termination
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ----------------------------------------
# Main entry point
# ----------------------------------------
if __name__ == "__main__":
    # Add the script name to the module name
    uvicorn.run("fastapi_registry_example:app", host="0.0.0.0", port=8000, reload=True)
