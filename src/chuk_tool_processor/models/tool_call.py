# chuk_tool_processor/models/tool_call.py
"""
Model representing a tool call with arguments.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    """
    Represents a call to a tool with arguments.

    Attributes:
        id: Unique identifier for the tool call
        tool: Name of the tool to call
        namespace: Namespace the tool belongs to
        arguments: Arguments to pass to the tool
        idempotency_key: Optional key for deduplicating duplicate calls (auto-generated)
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the tool call")
    tool: str = Field(..., min_length=1, description="Name of the tool to call; must be non-empty")
    namespace: str = Field(default="default", description="Namespace the tool belongs to")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the tool")
    _idempotency_key: str | None = None  # Cached value, computed lazily

    def get_idempotency_key(self) -> str:
        """
        Get or compute idempotency key lazily.

        PERFORMANCE: Only computed when explicitly needed, avoiding overhead
        in hot paths where deduplication isn't required.
        """
        if self._idempotency_key is None:
            self._idempotency_key = self._compute_idempotency_key()
        return self._idempotency_key

    def _compute_idempotency_key(self) -> str:
        """
        Compute a stable idempotency key from tool name, namespace, and arguments.

        Uses SHA256 hash of the sorted JSON representation.
        Returns first 16 characters of the hex digest for brevity.
        """
        # Create a stable representation
        payload = {
            "tool": self.tool,
            "namespace": self.namespace,
            "arguments": self.arguments,
        }
        # Sort keys for stability
        json_str = json.dumps(payload, sort_keys=True, default=str)
        # Hash it
        hash_obj = hashlib.sha256(json_str.encode(), usedforsecurity=False)
        return hash_obj.hexdigest()[:16]  # Use first 16 chars for brevity

    async def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary for serialization."""
        return {"id": self.id, "tool": self.tool, "namespace": self.namespace, "arguments": self.arguments}

    @classmethod
    async def from_dict(cls, data: dict[str, Any]) -> ToolCall:
        """Create a ToolCall from a dictionary."""
        return cls(**data)

    def __str__(self) -> str:
        """String representation of the tool call."""
        args_str = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"ToolCall({self.tool}, {args_str})"
