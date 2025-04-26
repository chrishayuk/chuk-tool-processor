# chuk_tool_processor/plugins/function_call_tool.py
import json
import re
from typing import List, Any, Dict
from pydantic import ValidationError

# imports
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.utils.logging import get_logger

# logger
logger = get_logger("chuk_tool_processor.plugins.function_call_tool")

class FunctionCallPlugin:
    """
    Parse OpenAI-style `function_call` payloads embedded in the LLM response.
    
    Supports two formats:
    1. JSON object with function_call field:
      {
        "function_call": {
          "name": "my_tool",
          "arguments": '{"x":1,"y":"two"}'
        }
      }
      
    2. JSON object with function_call field and already parsed arguments:
      {
        "function_call": {
          "name": "my_tool",
          "arguments": {"x":1, "y":"two"}
        }
      }
    """
    def try_parse(self, raw: str) -> List[ToolCall]:
        calls: List[ToolCall] = []
        
        # First, try to parse as a complete JSON object
        try:
            payload = json.loads(raw)
            
            # Check if this is a function call payload
            if isinstance(payload, dict) and "function_call" in payload:
                fc = payload.get("function_call")
                if not isinstance(fc, dict):
                    return []
                
                name = fc.get("name")
                args = fc.get("arguments", {})
                
                # Arguments sometimes come back as a JSON-encoded string
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        # Leave as empty dict if malformed but still create the call
                        args = {}
                
                # Only proceed if we have a valid name
                if not isinstance(name, str) or not name:
                    return []
                
                try:
                    call = ToolCall(tool=name, arguments=args if isinstance(args, Dict) else {})
                    calls.append(call)
                    logger.debug(f"Found function call to {name}")
                except ValidationError:
                    # invalid tool name or args shape
                    logger.warning(f"Invalid function call: {name}")
            
            # Look for nested function calls
            if not calls:
                # Try to find function calls in nested objects
                json_str = json.dumps(payload)
                json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
                matches = re.finditer(json_pattern, json_str)
                
                for match in matches:
                    # Skip if it's the complete string we already parsed
                    json_substr = match.group(0)
                    if json_substr == json_str:
                        continue
                        
                    try:
                        nested_payload = json.loads(json_substr)
                        if isinstance(nested_payload, dict) and "function_call" in nested_payload:
                            nested_calls = self.try_parse(json_substr)
                            calls.extend(nested_calls)
                    except json.JSONDecodeError:
                        continue
                
        except json.JSONDecodeError:
            # If it's not valid JSON, try to extract function calls using regex
            json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
            matches = re.finditer(json_pattern, raw)
            
            for match in matches:
                json_str = match.group(0)
                try:
                    nested_calls = self.try_parse(json_str)
                    calls.extend(nested_calls)
                except Exception:
                    continue
        
        return calls