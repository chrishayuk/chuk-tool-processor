# chuk_tool_processor/utils/validation.py
from typing import Any, Dict, Optional, Type, get_type_hints, Union, List, Callable
from pydantic import BaseModel, ValidationError, create_model
import inspect
from functools import wraps

from chuk_tool_processor.core.exceptions import ToolValidationError


def validate_arguments(tool_name: str, tool_func: Callable, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate tool arguments against function signature.
    
    Args:
        tool_name: Name of the tool for error reporting.
        tool_func: Tool function to validate against.
        args: Arguments to validate.
        
    Returns:
        Validated arguments dict.
        
    Raises:
        ToolValidationError: If validation fails.
    """
    try:
        # Get type hints from function
        type_hints = get_type_hints(tool_func)
        
        # Remove return type hint if present
        if 'return' in type_hints:
            type_hints.pop('return')
        
        # Create dynamic Pydantic model for validation
        field_definitions = {
            name: (type_hint, ...) for name, type_hint in type_hints.items()
        }
        
        # Add optional fields based on default values
        sig = inspect.signature(tool_func)
        for param_name, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                if param_name in field_definitions:
                    field_type, _ = field_definitions[param_name]
                    field_definitions[param_name] = (field_type, param.default)
        
        # Create model
        model = create_model(f"{tool_name}Args", **field_definitions)
        
        # Validate args
        validated = model(**args)
        return validated.dict()
    
    except ValidationError as e:
        raise ToolValidationError(tool_name, e.errors())
    except Exception as e:
        raise ToolValidationError(tool_name, {"general": str(e)})


def validate_result(tool_name: str, tool_func: Callable, result: Any) -> Any:
    """
    Validate tool result against function return type.
    
    Args:
        tool_name: Name of the tool for error reporting.
        tool_func: Tool function to validate against.
        result: Result to validate.
        
    Returns:
        Validated result.
        
    Raises:
        ToolValidationError: If validation fails.
    """
    try:
        # Get return type hint
        type_hints = get_type_hints(tool_func)
        return_type = type_hints.get('return')
        
        if return_type is None:
            # No return type to validate against
            return result
        
        # Create dynamic Pydantic model for validation
        model = create_model(
            f"{tool_name}Result",
            result=(return_type, ...)
        )
        
        # Validate result
        validated = model(result=result)
        return validated.result
    
    except ValidationError as e:
        raise ToolValidationError(tool_name, e.errors())
    except Exception as e:
        raise ToolValidationError(tool_name, {"general": str(e)})


def with_validation(cls):
    """
    Class decorator to add type validation to tool classes.
    
    Example:
        @with_validation
        class MyTool:
            def execute(self, x: int, y: str) -> float:
                return float(x) + float(y)
    """
    original_execute = cls.execute
    
    @wraps(original_execute)
    def execute_with_validation(self, **kwargs):
        # Get tool name
        tool_name = getattr(cls, "__name__", repr(cls))
        
        # Validate arguments
        validated_args = validate_arguments(tool_name, original_execute, kwargs)
        
        # Execute the tool
        result = original_execute(self, **validated_args)
        
        # Validate result
        return validate_result(tool_name, original_execute, result)
    
    cls.execute = execute_with_validation
    return cls


class ValidatedTool(BaseModel):
    """
    Base class for tools with built-in validation.
    
    Example:
        class AddTool(ValidatedTool):
            class Arguments(BaseModel):
                x: int
                y: int
                
            class Result(BaseModel):
                sum: int
                
            def execute(self, x: int, y: int) -> Result:
                return self.Result(sum=x + y)
    """
    class Arguments(BaseModel):
        """Base arguments model to be overridden by subclasses."""
        pass
    
    class Result(BaseModel):
        """Base result model to be overridden by subclasses."""
        pass
    
    def execute(self, **kwargs) -> Any:
        """
        Execute the tool with validated arguments.
        
        Args:
            **kwargs: Arguments to validate against Arguments model.
            
        Returns:
            Validated result according to Result model.
            
        Raises:
            ToolValidationError: If validation fails.
        """
        try:
            # Validate arguments
            validated_args = self.Arguments(**kwargs)
            
            # Execute implementation
            result = self._execute(**validated_args.dict())
            
            # Validate result if it's not already a Result instance
            if not isinstance(result, self.Result):
                result = self.Result(**result if isinstance(result, dict) else {"value": result})
                
            return result
            
        except ValidationError as e:
            raise ToolValidationError(self.__class__.__name__, e.errors())
    
    def _execute(self, **kwargs) -> Any:
        """
        Implementation method to be overridden by subclasses.
        
        Args:
            **kwargs: Validated arguments.
            
        Returns:
            Result that will be validated against Result model.
        """
        raise NotImplementedError("Subclasses must implement _execute")