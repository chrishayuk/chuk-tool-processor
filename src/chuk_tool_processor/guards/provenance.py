# chuk_tool_processor/guards/provenance.py
"""Provenance guard for tracking and attributing tool outputs.

Ensures tool outputs are attributable and safe to reuse.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from pydantic import BaseModel, Field

from chuk_tool_processor.guards.base import BaseGuard, GuardResult
from chuk_tool_processor.guards.models import EnforcementLevel


class ProvenanceRecord(BaseModel):
    """Record of a tool output's provenance."""

    reference_id: str
    tool_name: str
    args_hash: str
    timestamp_ms: int
    parent_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvenanceConfig(BaseModel):
    """Configuration for ProvenanceGuard."""

    require_attribution: bool = Field(
        default=True,
        description="Require all values to have provenance",
    )
    track_lineage: bool = Field(
        default=True,
        description="Track lineage of derived values",
    )
    max_unattributed_uses: int = Field(
        default=0,
        description="Maximum uses of unattributed values (0 = block)",
    )
    max_history_size: int = Field(
        default=10_000,
        description="Maximum provenance records to keep",
    )
    reference_arg_names: set[str] = Field(
        default_factory=lambda: {
            "_ref",
            "_reference",
            "_provenance",
            "_source",
        },
        description="Argument names that may contain references",
    )
    enforcement_level: EnforcementLevel = Field(
        default=EnforcementLevel.WARN,
        description="Enforcement level for attribution violations",
    )


class ProvenanceGuard(BaseGuard):
    """Guard that tracks provenance of tool outputs.

    Features:
    - Generates stable reference IDs for outputs
    - Tracks provenance metadata (tool, args, time)
    - Validates references in arguments
    - Lineage tracking for derived values
    """

    def __init__(self, config: ProvenanceConfig | None = None) -> None:
        self.config = config or ProvenanceConfig()
        self._records: dict[str, ProvenanceRecord] = {}
        self._unattributed_uses: dict[str, int] = {}

    def check(
        self,
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, Any],
    ) -> GuardResult:
        """Check if arguments contain valid provenance references."""
        if not self.config.require_attribution:
            return self.allow()

        # Find references in arguments
        refs = self._extract_references(arguments)

        # Validate all references
        invalid_refs = [ref for ref in refs if not self.check_reference(ref)]

        if invalid_refs:
            # Track unattributed uses
            for ref in invalid_refs:
                self._unattributed_uses[ref] = self._unattributed_uses.get(ref, 0) + 1

            # Check if within tolerance
            max_uses = max(self._unattributed_uses.get(ref, 0) for ref in invalid_refs)
            if max_uses > self.config.max_unattributed_uses:
                message = f"Invalid provenance references: {', '.join(invalid_refs[:3])}"
                if len(invalid_refs) > 3:
                    message += f" (+{len(invalid_refs) - 3} more)"

                return self._enforcement_result(message, invalid_refs)

        return self.allow()

    def check_output(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> GuardResult:
        """Record provenance for tool output."""
        # Generate and store provenance record
        ref_id = self.record_output(tool_name, arguments, result)

        return self.allow(reason=f"Provenance recorded: {ref_id}")

    def record_output(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,  # noqa: ARG002
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record tool output and return reference ID."""
        args_hash = self._hash_arguments(arguments)
        timestamp_ms = self._now_ms()

        # Generate reference ID
        ref_id = self._generate_reference_id(tool_name, args_hash, timestamp_ms)

        # Find parent references in arguments
        parent_refs = self._extract_references(arguments) if self.config.track_lineage else []

        # Create record
        record = ProvenanceRecord(
            reference_id=ref_id,
            tool_name=tool_name,
            args_hash=args_hash,
            timestamp_ms=timestamp_ms,
            parent_refs=parent_refs,
            metadata=metadata or {},
        )

        # Store with size limit
        self._records[ref_id] = record
        self._enforce_history_limit()

        return ref_id

    def check_reference(self, ref_id: str) -> bool:
        """Check if a reference ID is valid."""
        return ref_id in self._records

    def get_provenance(self, ref_id: str) -> ProvenanceRecord | None:
        """Get provenance record for a reference ID."""
        return self._records.get(ref_id)

    def get_lineage(self, ref_id: str) -> list[ProvenanceRecord]:
        """Get full lineage chain for a reference ID."""
        lineage: list[ProvenanceRecord] = []
        visited: set[str] = set()

        def trace(current_ref: str) -> None:
            if current_ref in visited:
                return
            visited.add(current_ref)

            record = self._records.get(current_ref)
            if record:
                lineage.append(record)
                for parent_ref in record.parent_refs:
                    trace(parent_ref)

        trace(ref_id)
        return lineage

    def get_all_records(self) -> list[ProvenanceRecord]:
        """Get all provenance records."""
        return list(self._records.values())

    def reset(self) -> None:
        """Reset all provenance records."""
        self._records.clear()
        self._unattributed_uses.clear()

    def _extract_references(self, arguments: dict[str, Any]) -> list[str]:
        """Extract reference IDs from arguments."""
        refs: list[str] = []

        def scan(value: Any, key: str = "") -> None:
            if isinstance(value, str):
                # Check if key suggests this is a reference
                if key.lower() in self.config.reference_arg_names or self._looks_like_reference(value):
                    refs.append(value)

            elif isinstance(value, dict):
                for k, v in value.items():
                    scan(v, k)

            elif isinstance(value, list):
                for item in value:
                    scan(item, key)

        scan(arguments)
        return refs

    def _looks_like_reference(self, value: str) -> bool:
        """Check if a string looks like a reference ID."""
        # Our format: tool_name:hash:timestamp
        parts = value.split(":")
        if len(parts) != 3:
            return False

        # Check hash part is hex
        try:
            int(parts[1], 16)
            int(parts[2])
            return True
        except ValueError:
            return False

    def _generate_reference_id(
        self,
        tool_name: str,
        args_hash: str,
        timestamp_ms: int,
    ) -> str:
        """Generate a stable reference ID."""
        return f"{tool_name}:{args_hash}:{timestamp_ms}"

    def _hash_arguments(self, arguments: dict[str, Any]) -> str:
        """Create stable hash of arguments."""
        # Exclude reference arguments from hash
        filtered = {k: v for k, v in arguments.items() if k.lower() not in self.config.reference_arg_names}
        content = str(sorted(filtered.items()))
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def _enforce_history_limit(self) -> None:
        """Ensure history doesn't exceed max size."""
        if len(self._records) <= self.config.max_history_size:
            return

        # Remove oldest records
        sorted_records = sorted(
            self._records.items(),
            key=lambda x: x[1].timestamp_ms,
        )
        to_remove = len(self._records) - self.config.max_history_size
        for ref_id, _ in sorted_records[:to_remove]:
            del self._records[ref_id]

    def _enforcement_result(
        self,
        message: str,
        invalid_refs: list[str],
    ) -> GuardResult:
        """Create enforcement result based on config."""
        if self.config.enforcement_level == EnforcementLevel.WARN:
            return self.warn(
                reason=message,
                invalid_refs=invalid_refs,
            )

        return self.block(
            reason=message,
            invalid_refs=invalid_refs,
        )

    def _now_ms(self) -> int:
        """Get current time in milliseconds."""
        return int(time.time() * 1000)
