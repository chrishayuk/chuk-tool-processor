#!/usr/bin/env python3
# sample_tools/calculator_tool.py
"""
sample_tools/calculator_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A tiny four-function calculator that works with async callers.

It accepts the same argument schema your demo already sends:

    {"operation": "multiply", "a": 235.5, "b": 18.75}
"""
from __future__ import annotations

import asyncio
from typing import Dict

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry.decorators import register_tool


@register_tool(name="calculator")
class CalculatorTool(ValidatedTool):
    """Perform basic arithmetic."""

    # ── validated I/O schemas ─────────────────────────────────────
    class Arguments(ValidatedTool.Arguments):
        operation: str  # add | subtract | multiply | divide
        a: float
        b: float

    class Result(ValidatedTool.Result):
        result: float
        operation: str

    # ── internal calculation (blocking)────────────────────────────
    def _execute(self, operation: str, a: float, b: float) -> Dict:
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

        return {"result": result, "operation": operation}

    # ── sync entry-point (required by ValidatedTool) ───────────────
    def run(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        res  = self._execute(**args.model_dump())
        return self.Result(**res).model_dump()

    # ── async façade for “await tool(args)” style ──────────────────
    async def arun(self, **kwargs) -> Dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.run(**kwargs))

