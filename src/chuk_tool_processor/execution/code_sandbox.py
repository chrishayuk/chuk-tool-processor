# chuk_tool_processor/execution/code_sandbox.py
"""
Safe Python code execution sandbox with tool access.

Enables programmatic tool orchestration by executing Python code that can call
registered tools. Provides security controls and resource limits.
"""

from __future__ import annotations

import asyncio
import sys
from io import StringIO
from typing import Any

from chuk_tool_processor.registry import get_default_registry
from chuk_tool_processor.registry.interface import ToolRegistryInterface


class CodeExecutionError(Exception):
    """Raised when code execution fails."""

    pass


class CodeSandbox:
    """
    Safe Python code execution environment with tool access.

    Allows executing Python code that can call registered tools, enabling
    programmatic tool orchestration for any LLM (not just those with built-in
    code execution like Claude).

    Example:
        ```python
        from chuk_tool_processor.execution.code_sandbox import CodeSandbox

        sandbox = CodeSandbox()

        code = '''
        # Call tools in a loop
        total = 0
        for i in range(1, 6):
            result = await add(a=str(total), b=str(i))
            total = int(result.content[0]['text'])
        return total
        '''

        result = await sandbox.execute(code)
        print(result)  # Output from the code
        ```

    Security:
        - Restricted builtins (no file I/O, imports, etc.)
        - Resource limits (configurable timeout)
        - Tool allowlist (only registered tools accessible)
        - Isolated execution environment
    """

    def __init__(
        self,
        registry: ToolRegistryInterface | None = None,
        timeout: float = 30.0,
        allowed_builtins: set[str] | None = None,
    ):
        """
        Initialize code sandbox.

        Args:
            registry: Tool registry to use (default: global registry)
            timeout: Maximum execution time in seconds
            allowed_builtins: Set of allowed builtin functions
        """
        self.registry = registry
        self.timeout = timeout
        self.allowed_builtins = allowed_builtins or {
            # Type constructors
            "int",
            "float",
            "str",
            "bool",
            "list",
            "dict",
            "tuple",
            "set",
            # Utility functions
            "len",
            "range",
            "enumerate",
            "zip",
            "sorted",
            "reversed",
            "sum",
            "min",
            "max",
            "abs",
            "round",
            "any",
            "all",
            # String operations
            "print",
            "format",
            # Data inspection
            "type",
            "isinstance",
            "hasattr",
            "getattr",
            # Exception handling
            "Exception",
            "ValueError",
            "TypeError",
            "KeyError",
            "IndexError",
            "AttributeError",
            "NameError",
        }

    async def execute(
        self,
        code: str,
        namespace: str | None = None,
        initial_vars: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute Python code with access to registered tools.

        Args:
            code: Python code to execute
            namespace: Namespace to filter tools (None = all namespaces)
            initial_vars: Initial variables to make available in code

        Returns:
            Result of code execution (value of last expression or return statement)

        Raises:
            CodeExecutionError: If execution fails or times out
        """
        # Get registry
        if self.registry is None:
            self.registry = await get_default_registry()

        # Build safe globals
        safe_globals = await self._build_safe_globals(namespace, initial_vars or {})

        # Capture stdout
        stdout_capture = StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture

        try:
            # Execute with timeout
            async def _run_code():
                # Create local scope for execution
                local_scope: dict[str, Any] = {}

                # Wrap code in function if it uses await or return
                needs_wrapping = "await " in code or "return " in code

                if needs_wrapping:
                    # Wrap in async function if uses await, sync function otherwise
                    if "await " in code:
                        wrapped_code = "async def __sandbox_main__():\n"
                    else:
                        wrapped_code = "def __sandbox_main__():\n"

                    for line in code.split("\n"):
                        wrapped_code += f"    {line}\n"

                    # Compile and execute wrapper
                    try:
                        exec(compile(wrapped_code, "<sandbox>", "exec"), safe_globals, local_scope)  # nosec B102 - Intentional code execution in controlled sandbox with restricted builtins
                    except SyntaxError as e:
                        raise CodeExecutionError(f"Syntax error in code: {e}")

                    # Call the function (await if async)
                    if "await " in code:
                        result = await local_scope["__sandbox_main__"]()
                    else:
                        result = local_scope["__sandbox_main__"]()
                    return result
                else:
                    # Execute synchronous code directly
                    try:
                        compiled = compile(code, "<sandbox>", "exec")
                        exec(compiled, safe_globals, local_scope)  # nosec B102 - Intentional code execution in controlled sandbox with restricted builtins
                    except SyntaxError as e:
                        raise CodeExecutionError(f"Syntax error in code: {e}")

                    # Return the last assigned value
                    return local_scope.get("__result__")

            try:
                result = await asyncio.wait_for(_run_code(), timeout=self.timeout)
            except TimeoutError:
                raise CodeExecutionError(f"Code execution timed out after {self.timeout}s")
            except Exception as e:
                raise CodeExecutionError(f"Code execution failed: {e}")

            return result

        finally:
            # Restore stdout
            sys.stdout = old_stdout
            output = stdout_capture.getvalue()
            if output:
                print(output, end="")

    async def _build_safe_globals(self, namespace: str | None, initial_vars: dict[str, Any]) -> dict[str, Any]:
        """
        Build safe global scope with tool access.

        Args:
            namespace: Namespace to filter tools
            initial_vars: Initial variables

        Returns:
            Dict of safe globals including tool functions
        """
        # Get actual builtins module
        import builtins as builtin_module

        # Start with allowed builtins
        safe_builtins = {}
        for name in self.allowed_builtins:
            if hasattr(builtin_module, name):
                safe_builtins[name] = getattr(builtin_module, name)

        safe_globals: dict[str, Any] = {
            "__builtins__": safe_builtins,
        }

        # Add initial variables
        safe_globals.update(initial_vars)

        # Add tool functions
        if self.registry:
            tools = await self.registry.list_tools(namespace=namespace)

            for tool_info in tools:
                # Get the tool instance
                tool = await self.registry.get_tool(tool_info.name, tool_info.namespace)

                if tool is None:
                    continue

                # Create async wrapper function with proper closure
                def make_tool_wrapper(tool_obj):
                    async def wrapper(**kwargs):
                        return await tool_obj.execute(**kwargs)

                    return wrapper

                # Add to globals
                tool_func = make_tool_wrapper(tool)
                tool_func.__name__ = tool_info.name
                safe_globals[tool_info.name] = tool_func

        return safe_globals
