#!/usr/bin/env python
# tool_calling_example_usage_2.py
import asyncio
import json
import sys
from typing import Dict, Any, Optional, List

# Updated imports for the new structure
from chuk_tool_processor.registry import ToolRegistryProvider, register_tool
from chuk_tool_processor.utils.validation import ValidatedTool
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.execution.wrappers.retry import retryable
from chuk_tool_processor.execution.wrappers.caching import cacheable
from chuk_tool_processor.execution.wrappers.rate_limiting import rate_limited
from chuk_tool_processor.logging import request_logging, get_logger, log_context_span

# Set up logger
logger = get_logger("example")

# Get the global registry
registry = ToolRegistryProvider.get_registry()


# Define some tools using decorators
@register_tool(name="calculator", namespace="math")
@retryable(max_retries=2)
@cacheable(ttl=3600)  # Cache for 1 hour
class CalculatorTool:
    """A simple calculator tool that performs basic arithmetic operations."""
    
    def execute(self, operation: str, a: float, b: float) -> Dict[str, Any]:
        """
        Execute a basic arithmetic operation.
        
        Args:
            operation: One of "add", "subtract", "multiply", "divide"
            a: First operand
            b: Second operand
            
        Returns:
            Dictionary with result and operation details
        """
        logger.info(f"Calculating {operation} with {a} and {b}")
        result = None
        
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Division by zero")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        return {
            "operation": operation,
            "operands": [a, b],
            "result": result
        }


# Define a tool using the ValidatedTool base class
@register_tool(namespace="data")
@rate_limited(limit=5, period=60.0)  # 5 requests per minute
class WeatherTool(ValidatedTool):
    """Tool to fetch weather information for a location."""
    
    class Arguments(ValidatedTool.Arguments):
        location: str
        units: str = "metric"  # Default to metric
    
    class Result(ValidatedTool.Result):
        temperature: float
        conditions: str
        humidity: Optional[int] = None
        wind_speed: Optional[float] = None
    
    def _execute(self, location: str, units: str = "metric") -> Dict[str, Any]:
        """
        Fetch weather for a location.
        
        Args:
            location: City name or coordinates
            units: "metric" or "imperial"
            
        Returns:
            Weather data
        """
        logger.info(f"Fetching weather for {location} in {units} units")
        
        # Simulate API call (in real implementation, would call a weather API)
        # Simulate occasional transient errors for retry demonstration
        import random
        if random.random() < 0.3:
            raise ConnectionError("Weather API temporarily unavailable")
        
        # Demo implementation - return mock data
        return {
            "temperature": 22.5 if units == "metric" else 72.5,
            "conditions": "Partly Cloudy",
            "humidity": 65,
            "wind_speed": 10.0
        }


# Example LLM texts with different types of tool calls
EXAMPLE_TEXTS = [
    # JSON function_call format
    '''
    I'll calculate that for you.
    
    {
      "function_call": {
        "name": "calculator",
        "arguments": {"operation": "multiply", "a": 123.45, "b": 67.89}
      }
    }
    ''',
    
    # XML format for weather tool
    '''
    Let me check the weather for you.
    
    <tool name="WeatherTool" args='{"location": "New York", "units": "metric"}' />
    ''',
    
    # No tool calls
    '''
    The capital of France is Paris. It's a beautiful city known for the Eiffel Tower
    and fine cuisine.
    '''
]


async def process_llm_response(text: str) -> str:
    """
    Process an LLM response text and handle any tool calls found.
    
    Args:
        text: LLM response text to process
        
    Returns:
        Text with tool results injected
    """
    with request_logging() as request_id:
        # Create tool processor with all features enabled
        processor = ToolProcessor(
            enable_caching=True,
            enable_rate_limiting=True,
            enable_retries=True,
            max_retries=2
        )
        
        # Process the text to find and execute tool calls
        with log_context_span("process_text", {"text_length": len(text)}):
            logger.info(f"Processing text: {text[:50]}...")
            results = await processor.process_text(text, timeout=5.0)
        
        # Handle results
        if not results:
            logger.info("No tool calls found or executed")
            return text
        
        # Format results for display
        output = text + "\n\n### Tool Results:\n"
        
        for i, result in enumerate(results):
            output += f"\n#### {i+1}. {result.tool}\n"
            
            if result.error:
                output += f"Error: {result.error}\n"
            else:
                # Format the result nicely
                if isinstance(result.result, dict):
                    formatted = json.dumps(result.result, indent=2)
                elif isinstance(result.result, list):
                    formatted = json.dumps(result.result, indent=2)
                else:
                    formatted = str(result.result)
                
                output += f"```\n{formatted}\n```\n"
            
            # Add execution metadata
            duration = (result.end_time - result.start_time).total_seconds()
            output += f"Execution time: {duration:.3f}s\n"
            
            if hasattr(result, "cached") and result.cached:
                output += "Result was cached\n"
            
            if hasattr(result, "attempts") and result.attempts > 1:
                output += f"Required {result.attempts} attempts\n"
        
        return output


async def main():
    """Run the example with different test texts."""
    print("\n=== Enhanced Tool Processor Example ===\n")
    
    # Register our tools
    logger.info("Registering calculator and weather tools")
    
    # Process each example
    for i, text in enumerate(EXAMPLE_TEXTS):
        print(f"\n\n=== Example {i+1} ===")
        print(f"Input text:\n{text}\n")
        
        # Process the text
        try:
            result = await process_llm_response(text)
            print(f"Output text:\n{result}\n")
        except Exception as e:
            print(f"Error processing example {i+1}: {e}")
            import traceback
            traceback.print_exc()
        
        print("=" * 80)


if __name__ == "__main__":
    # Use asyncio.run to run the async main function
    asyncio.run(main())