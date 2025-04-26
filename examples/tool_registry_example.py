#!/usr/bin/env python
# examples/tool_registry_example.py
#!/usr/bin/env python
"""
Example script demonstrating the tool registry functionality.

This example shows:
1. Registering tools with decorators
2. Manual tool registration
3. Listing available tools and namespaces
4. Retrieving and using tools
5. Querying tool metadata
"""

import asyncio
import sys
import os
from typing import Dict, Any, Optional, List

# Add parent directory to path for imports when running the script directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chuk_tool_processor.registry import (
    register_tool,
    ToolRegistryProvider,
    get_registry
)
from chuk_tool_processor.logging import get_logger

# Set up logger
logger = get_logger("example")


# Example 1: Register a tool using the decorator
@register_tool(name="calculator", namespace="math", tags={"math", "calculation"})
class CalculatorTool:
    """A calculator tool that performs basic arithmetic operations."""
    
    def execute(self, operation: str, a: float, b: float) -> Dict[str, Any]:
        """
        Execute a mathematical operation.
        
        Args:
            operation: The operation to perform (add, subtract, multiply, divide)
            a: First operand
            b: Second operand
            
        Returns:
            Dictionary containing operation details and result
        """
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Cannot divide by zero")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {operation}")
            
        return {
            "operation": operation,
            "operands": [a, b],
            "result": result
        }


# Example 2: Register an async tool
@register_tool(namespace="web")
class FetchTool:
    """Tool to fetch data from a URL."""
    
    async def execute(self, url: str, timeout: Optional[float] = 10.0) -> Dict[str, Any]:
        """
        Fetch data from a URL.
        
        Args:
            url: The URL to fetch
            timeout: Request timeout in seconds
            
        Returns:
            Response data
        """
        # This is a mock implementation - in a real tool, we would use aiohttp or httpx
        await asyncio.sleep(0.5)  # Simulate network delay
        
        return {
            "url": url,
            "status": 200,
            "content": f"Data fetched from {url}",
            "headers": {"Content-Type": "text/plain"}
        }


# Example 3: A tool to be registered manually
class WeatherTool:
    """Tool to get weather information for a location."""
    
    def execute(self, location: str, units: str = "metric") -> Dict[str, Any]:
        """
        Get weather information for a location.
        
        Args:
            location: Location name or coordinates
            units: Units for measurements (metric/imperial)
            
        Returns:
            Weather data
        """
        # Mock implementation
        temperature = 22.5 if units == "metric" else 72.5
        
        return {
            "location": location,
            "temperature": temperature,
            "units": units,
            "conditions": "Sunny",
            "humidity": 65,
            "wind": 10
        }


async def search_tools(registry, keyword: str) -> List[Dict[str, Any]]:
    """
    Search for tools matching a keyword in their name, description, or tags.
    
    Args:
        registry: The tool registry
        keyword: Keyword to search for
        
    Returns:
        List of matching tool information
    """
    results = []
    keyword = keyword.lower()
    
    # Get all tools
    tools = registry.list_tools()
    
    for namespace, name in tools:
        # Get tool metadata
        metadata = registry.get_metadata(name, namespace)
        if not metadata:
            continue
            
        # Check if keyword matches name, description, or tags
        matches = False
        if keyword in name.lower():
            matches = True
        elif metadata.description and keyword in metadata.description.lower():
            matches = True
        elif any(keyword in tag.lower() for tag in metadata.tags):
            matches = True
            
        if matches:
            results.append({
                "namespace": namespace,
                "name": name,
                "description": metadata.description,
                "is_async": metadata.is_async,
                "tags": list(metadata.tags)
            })
            
    return results


async def main():
    """Main function demonstrating registry functionality."""
    print("\n=== CHUK Tool Registry Example ===\n")
    
    # Get the global registry
    registry = ToolRegistryProvider.get_registry()
    
    # Example 3: Manually register a tool
    registry.register_tool(
        WeatherTool(),  # Note: passing an instance, not the class
        name="weather", 
        namespace="data",
        metadata={
            "description": "Get weather information for a location",
            "tags": {"weather", "data", "location"},
            "version": "1.2.0"
        }
    )
    
    # List all namespaces
    print("Available namespaces:")
    namespaces = registry.list_namespaces()
    for namespace in namespaces:
        print(f"  - {namespace}")
    print()
    
    # List all tools
    print("Available tools:")
    tools = registry.list_tools()
    for namespace, name in tools:
        metadata = registry.get_metadata(name, namespace)
        description = metadata.description if metadata else "No description"
        print(f"  - {namespace}.{name}: {description}")
    print()
    
    # Using the calculator tool
    print("Using the calculator tool:")
    calculator_class = registry.get_tool("calculator", "math")
    if calculator_class:
        # Need to instantiate the class
        calculator = calculator_class()
        try:
            result = calculator.execute("multiply", 12.5, 3.5)
            print(f"  12.5 * 3.5 = {result['result']}")
            
            result = calculator.execute("divide", 100, 4)
            print(f"  100 / 4 = {result['result']}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  Calculator tool not found!")
    print()
    
    # Using the weather tool
    print("Using the weather tool:")
    weather = registry.get_tool("weather", "data")
    if weather:
        # Weather tool is already an instance, no need to instantiate
        result = weather.execute("San Francisco")
        print(f"  Weather in {result['location']}: {result['temperature']}°C, {result['conditions']}")
        print(f"  Humidity: {result['humidity']}%, Wind: {result['wind']} km/h")
    else:
        print("  Weather tool not found!")
    print()
    
    # Using the async fetch tool
    print("Using the fetch tool (async):")
    fetch_class = registry.get_tool("FetchTool", "web")
    if fetch_class:
        # Need to instantiate the class
        fetch = fetch_class()
        result = await fetch.execute("https://example.com/api/data")
        print(f"  Status: {result['status']}")
        print(f"  Content: {result['content']}")
    else:
        print("  Fetch tool not found!")
    print()
    
    # Search for tools
    print("Searching for tools with keyword 'math':")
    results = await search_tools(registry, "math")
    for tool in results:
        print(f"  - {tool['namespace']}.{tool['name']}")
        print(f"    Description: {tool['description']}")
        print(f"    Tags: {', '.join(tool['tags'])}")
        print(f"    Async: {tool['is_async']}")
        print()
    
    print("Searching for tools with keyword 'data':")
    results = await search_tools(registry, "data")
    for tool in results:
        print(f"  - {tool['namespace']}.{tool['name']}")
        print(f"    Description: {tool['description']}")
        print(f"    Tags: {', '.join(tool['tags'])}")
        print(f"    Async: {tool['is_async']}")
        print()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())