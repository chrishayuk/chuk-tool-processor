# tests/guards/test_provenance.py
"""Tests for ProvenanceGuard."""

import pytest

from chuk_tool_processor.guards.base import GuardVerdict
from chuk_tool_processor.guards.models import EnforcementLevel
from chuk_tool_processor.guards.provenance import (
    ProvenanceConfig,
    ProvenanceGuard,
)


class TestProvenanceGuard:
    """Tests for ProvenanceGuard."""

    @pytest.fixture
    def guard(self) -> ProvenanceGuard:
        """Default guard."""
        return ProvenanceGuard(
            config=ProvenanceConfig(
                require_attribution=True,
                track_lineage=True,
            )
        )

    def test_record_output_creates_reference(self, guard: ProvenanceGuard):
        """Test recording output creates a reference ID."""
        ref_id = guard.record_output("tool", {"arg": "value"}, {"result": "data"})

        assert ref_id is not None
        assert "tool:" in ref_id
        assert guard.check_reference(ref_id)

    def test_reference_format(self, guard: ProvenanceGuard):
        """Test reference ID format is tool:hash:timestamp."""
        ref_id = guard.record_output("my_tool", {"x": 1}, "result")

        parts = ref_id.split(":")
        assert len(parts) == 3
        assert parts[0] == "my_tool"
        # Hash should be hex
        int(parts[1], 16)
        # Timestamp should be int
        int(parts[2])

    def test_get_provenance(self, guard: ProvenanceGuard):
        """Test retrieving provenance record."""
        ref_id = guard.record_output("tool", {"arg": "value"}, "result")

        record = guard.get_provenance(ref_id)
        assert record is not None
        assert record.tool_name == "tool"
        assert record.reference_id == ref_id

    def test_invalid_reference_returns_none(self, guard: ProvenanceGuard):
        """Test invalid reference returns None."""
        record = guard.get_provenance("invalid:ref:123")
        assert record is None

    def test_check_reference_validity(self, guard: ProvenanceGuard):
        """Test checking reference validity."""
        ref_id = guard.record_output("tool", {}, "result")

        assert guard.check_reference(ref_id)
        assert not guard.check_reference("fake:ref:123")

    def test_check_allows_valid_reference(self, guard: ProvenanceGuard):
        """Test check allows valid references in arguments."""
        # Create a valid reference
        ref_id = guard.record_output("tool", {}, "result")

        # Use the reference in arguments
        result = guard.check("another_tool", {"_ref": ref_id})
        assert result.allowed

    def test_check_warns_invalid_reference(self, guard: ProvenanceGuard):
        """Test check warns on invalid references."""
        result = guard.check("tool", {"_ref": "invalid:abc123def456:1234567890123"})
        # With max_unattributed_uses=0, should block/warn
        assert result.verdict in (GuardVerdict.WARN, GuardVerdict.BLOCK)

    def test_check_without_attribution_required(self):
        """Test check passes when attribution not required."""
        guard = ProvenanceGuard(config=ProvenanceConfig(require_attribution=False))
        result = guard.check("tool", {"_ref": "invalid:ref:123"})
        assert result.allowed

    def test_lineage_tracking(self, guard: ProvenanceGuard):
        """Test lineage tracking for derived values."""
        # Create parent
        parent_ref = guard.record_output("parent_tool", {"x": 1}, "parent_result")

        # Create child that depends on parent
        child_ref = guard.record_output("child_tool", {"_ref": parent_ref}, "child_result")

        # Get lineage
        lineage = guard.get_lineage(child_ref)
        assert len(lineage) == 2
        ref_ids = [r.reference_id for r in lineage]
        assert child_ref in ref_ids
        assert parent_ref in ref_ids

    def test_lineage_chain(self, guard: ProvenanceGuard):
        """Test multi-level lineage chain."""
        ref1 = guard.record_output("tool1", {}, "result1")
        ref2 = guard.record_output("tool2", {"_ref": ref1}, "result2")
        ref3 = guard.record_output("tool3", {"_ref": ref2}, "result3")

        lineage = guard.get_lineage(ref3)
        assert len(lineage) == 3

    def test_lineage_circular_reference_handled(self, guard: ProvenanceGuard):
        """Test lineage handles circular references gracefully."""
        # Create initial ref
        ref1 = guard.record_output("tool1", {}, "result1")

        # Manually create circular reference (shouldn't happen normally)
        record1 = guard._records[ref1]
        record1.parent_refs.append(ref1)  # Self-reference

        # Should not infinite loop
        lineage = guard.get_lineage(ref1)
        assert len(lineage) == 1

    def test_check_output_records_provenance(self, guard: ProvenanceGuard):
        """Test check_output records provenance."""
        result = guard.check_output("tool", {"arg": "value"}, "result")

        assert result.allowed
        assert "Provenance recorded" in result.reason

    def test_history_limit_enforced(self):
        """Test history limit is enforced."""
        guard = ProvenanceGuard(config=ProvenanceConfig(max_history_size=3))

        guard.record_output("tool1", {"a": 1}, "r1")
        guard.record_output("tool2", {"b": 2}, "r2")
        guard.record_output("tool3", {"c": 3}, "r3")
        guard.record_output("tool4", {"d": 4}, "r4")

        # Should only have 3 records (oldest removed)
        assert len(guard.get_all_records()) == 3

    def test_reset_clears_all(self, guard: ProvenanceGuard):
        """Test reset clears all records."""
        guard.record_output("tool", {}, "result")
        guard.reset()

        assert len(guard.get_all_records()) == 0

    def test_reference_arg_names_configurable(self):
        """Test custom reference argument names."""
        guard = ProvenanceGuard(
            config=ProvenanceConfig(
                reference_arg_names={"custom_ref", "source_id"},
            )
        )

        ref_id = guard.record_output("tool", {}, "result")

        # Should detect custom ref name
        result = guard.check("tool", {"custom_ref": ref_id})
        assert result.allowed

    def test_enforcement_level_block(self):
        """Test block enforcement level."""
        guard = ProvenanceGuard(
            config=ProvenanceConfig(
                enforcement_level=EnforcementLevel.BLOCK,
                max_unattributed_uses=0,
            )
        )

        result = guard.check("tool", {"_ref": "invalid:abc123def456:1234567890123"})
        assert result.verdict == GuardVerdict.BLOCK

    def test_max_unattributed_uses(self):
        """Test max unattributed uses tolerance."""
        guard = ProvenanceGuard(
            config=ProvenanceConfig(
                enforcement_level=EnforcementLevel.BLOCK,
                max_unattributed_uses=2,
            )
        )

        invalid_ref = "invalid:abc123def456:1234567890123"

        # First use - should allow (under threshold)
        result = guard.check("tool", {"_ref": invalid_ref})
        assert result.allowed

        # Second use - should allow
        result = guard.check("tool", {"_ref": invalid_ref})
        assert result.allowed

        # Third use - should block (exceeds threshold)
        result = guard.check("tool", {"_ref": invalid_ref})
        assert result.blocked

    def test_metadata_stored(self, guard: ProvenanceGuard):
        """Test metadata is stored with record."""
        ref_id = guard.record_output(
            "tool",
            {},
            "result",
            metadata={"user": "alice", "version": "1.0"},
        )

        record = guard.get_provenance(ref_id)
        assert record is not None
        assert record.metadata["user"] == "alice"

    def test_args_hash_excludes_references(self, guard: ProvenanceGuard):
        """Test args hash excludes reference arguments."""
        # Same base args should produce same hash
        ref1 = guard.record_output("tool", {"x": 1}, "result1")
        ref2 = guard.record_output("tool", {"x": 1, "_ref": "something"}, "result2")

        record1 = guard.get_provenance(ref1)
        record2 = guard.get_provenance(ref2)

        assert record1 is not None
        assert record2 is not None
        assert record1.args_hash == record2.args_hash

    def test_nested_reference_extraction(self, guard: ProvenanceGuard):
        """Test references extracted from nested structures."""
        ref_id = guard.record_output("tool", {}, "result")

        # Reference in nested dict
        result = guard.check("tool", {"config": {"nested": {"_ref": ref_id}}})
        assert result.allowed

    def test_looks_like_reference_validation(self, guard: ProvenanceGuard):
        """Test reference format validation."""
        # Valid format detected
        assert guard._looks_like_reference("tool:abc123def456:1234567890")

        # Invalid formats
        assert not guard._looks_like_reference("not-a-reference")
        assert not guard._looks_like_reference("too:many:colons:here")
        assert not guard._looks_like_reference("tool:nothex:123")
