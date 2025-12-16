# tests/models/test_sandbox_policy.py
"""
Tests for SandboxPolicy and PolicyRegistry.
"""

import pytest

from chuk_tool_processor.models.sandbox_policy import (
    MCP_POLICY,
    PERMISSIVE_POLICY,
    STANDARD_POLICY,
    STRICT_POLICY,
    CapabilityGrant,
    FilesystemPolicy,
    IsolationLevel,
    NetworkPolicy,
    PathRule,
    PolicyRegistry,
    ResourceLimit,
    SandboxPolicy,
    _min_none_float,
    _min_none_int,
    create_default_registry,
)


# --------------------------------------------------------------------------- #
# ResourceLimit Tests
# --------------------------------------------------------------------------- #
class TestResourceLimit:
    """Tests for ResourceLimit model."""

    def test_basic_limit(self):
        """Test creating basic resource limit."""
        limit = ResourceLimit(
            cpu_seconds=30,
            memory_mb=512,
        )
        assert limit.cpu_seconds == 30
        assert limit.memory_mb == 512

    def test_all_fields(self):
        """Test all limit fields."""
        limit = ResourceLimit(
            cpu_seconds=30.5,
            cpu_percent=80,
            memory_mb=1024,
            memory_percent=50,
            output_bytes=1024 * 1024,
            open_files=100,
            wall_time_seconds=60.0,
            max_processes=10,
        )
        assert limit.cpu_percent == 80
        assert limit.memory_percent == 50
        assert limit.output_bytes == 1024 * 1024
        assert limit.open_files == 100
        assert limit.wall_time_seconds == 60.0
        assert limit.max_processes == 10

    def test_merge_with_both_set(self):
        """Test merging limits when both have values."""
        limit1 = ResourceLimit(cpu_seconds=30, memory_mb=512)
        limit2 = ResourceLimit(cpu_seconds=20, memory_mb=1024)

        merged = limit1.merge_with(limit2)

        assert merged.cpu_seconds == 20  # Takes minimum
        assert merged.memory_mb == 512  # Takes minimum

    def test_merge_with_one_none(self):
        """Test merging when one limit has None."""
        limit1 = ResourceLimit(cpu_seconds=30)
        limit2 = ResourceLimit(memory_mb=512)

        merged = limit1.merge_with(limit2)

        assert merged.cpu_seconds == 30
        assert merged.memory_mb == 512

    def test_merge_all_fields(self):
        """Test merging all fields."""
        limit1 = ResourceLimit(
            cpu_seconds=30,
            cpu_percent=80,
            memory_mb=1024,
            memory_percent=60,
            output_bytes=2048,
            open_files=200,
            wall_time_seconds=120,
            max_processes=20,
        )
        limit2 = ResourceLimit(
            cpu_seconds=60,
            cpu_percent=50,
            memory_mb=512,
            memory_percent=40,
            output_bytes=1024,
            open_files=100,
            wall_time_seconds=60,
            max_processes=10,
        )

        merged = limit1.merge_with(limit2)

        # All should be minimum values
        assert merged.cpu_seconds == 30
        assert merged.cpu_percent == 50
        assert merged.memory_mb == 512
        assert merged.memory_percent == 40
        assert merged.output_bytes == 1024
        assert merged.open_files == 100
        assert merged.wall_time_seconds == 60
        assert merged.max_processes == 10


class TestMinNoneFunctions:
    """Tests for helper functions."""

    def test_min_none_int_both_set(self):
        """Test _min_none_int with both values set."""
        assert _min_none_int(10, 20) == 10
        assert _min_none_int(20, 10) == 10

    def test_min_none_int_first_none(self):
        """Test _min_none_int with first value None."""
        assert _min_none_int(None, 20) == 20

    def test_min_none_int_second_none(self):
        """Test _min_none_int with second value None."""
        assert _min_none_int(10, None) == 10

    def test_min_none_float_both_set(self):
        """Test _min_none_float with both values set."""
        assert _min_none_float(10.5, 20.5) == 10.5
        assert _min_none_float(20.5, 10.5) == 10.5

    def test_min_none_float_first_none(self):
        """Test _min_none_float with first value None."""
        assert _min_none_float(None, 20.5) == 20.5

    def test_min_none_float_second_none(self):
        """Test _min_none_float with second value None."""
        assert _min_none_float(10.5, None) == 10.5


# --------------------------------------------------------------------------- #
# PathRule Tests
# --------------------------------------------------------------------------- #
class TestPathRule:
    """Tests for PathRule model."""

    def test_basic_path_rule(self):
        """Test creating basic path rule."""
        rule = PathRule(pattern="/tmp/*", access="write")
        assert rule.pattern == "/tmp/*"
        assert rule.access == "write"

    def test_default_access(self):
        """Test default access level."""
        rule = PathRule(pattern="/var/*")
        assert rule.access == "read"


# --------------------------------------------------------------------------- #
# SandboxPolicy Tests
# --------------------------------------------------------------------------- #
class TestSandboxPolicy:
    """Tests for SandboxPolicy model."""

    def test_basic_policy(self):
        """Test creating basic policy."""
        policy = SandboxPolicy()
        assert policy.name == "default"
        assert policy.isolation == IsolationLevel.PROCESS
        assert policy.network == NetworkPolicy.DENY
        assert policy.filesystem == FilesystemPolicy.READ_ONLY

    def test_policy_with_all_fields(self):
        """Test policy with all fields set."""
        policy = SandboxPolicy(
            name="test-policy",
            description="Test description",
            priority=50,
            isolation=IsolationLevel.CONTAINER,
            network=NetworkPolicy.LOCALHOST,
            filesystem=FilesystemPolicy.TEMP_ONLY,
            allowed_hosts=["localhost"],
            blocked_hosts=["evil.com"],
            capabilities={CapabilityGrant.SPAWN_SUBPROCESS},
            tool_patterns=["test.*"],
            namespace_patterns=["my_namespace"],
            exclude_patterns=["test.excluded"],
        )
        assert policy.name == "test-policy"
        assert policy.description == "Test description"
        assert policy.priority == 50

    def test_validate_empty_pattern_fails(self):
        """Test that empty patterns are rejected."""
        with pytest.raises(ValueError, match="Empty pattern"):
            SandboxPolicy(tool_patterns=["valid", ""])

    def test_matches_basic_tool(self):
        """Test matching basic tool name."""
        policy = SandboxPolicy(tool_patterns=["solver.*"])
        assert policy.matches("solver.run") is True
        assert policy.matches("other.run") is False

    def test_matches_with_namespace(self):
        """Test matching with namespace."""
        policy = SandboxPolicy(
            tool_patterns=["compute.*"],
            namespace_patterns=["math"],
        )
        assert policy.matches("compute.add", "math") is True
        assert policy.matches("compute.add", "other") is False

    def test_matches_with_full_name(self):
        """Test matching with full namespaced name."""
        policy = SandboxPolicy(tool_patterns=["math.*"])
        assert policy.matches("add", "math") is True

    def test_matches_with_exclusion(self):
        """Test matching with exclusion patterns."""
        policy = SandboxPolicy(
            tool_patterns=["*"],
            exclude_patterns=["internal.*"],
        )
        assert policy.matches("public.tool") is True
        assert policy.matches("internal.tool") is False

    def test_matches_excludes_full_name(self):
        """Test matching exclusion with full namespaced name."""
        policy = SandboxPolicy(
            tool_patterns=["*"],
            exclude_patterns=["admin.*"],
        )
        assert policy.matches("tool", "admin") is False

    def test_is_restrictive_network_deny(self):
        """Test is_restrictive with network deny."""
        policy = SandboxPolicy(network=NetworkPolicy.DENY)
        assert policy.is_restrictive is True

    def test_is_restrictive_filesystem_deny(self):
        """Test is_restrictive with filesystem deny."""
        policy = SandboxPolicy(
            network=NetworkPolicy.ALLOW,
            filesystem=FilesystemPolicy.DENY,
        )
        assert policy.is_restrictive is True

    def test_is_restrictive_false(self):
        """Test is_restrictive when not restrictive."""
        policy = SandboxPolicy(
            network=NetworkPolicy.ALLOW,
            filesystem=FilesystemPolicy.READ_ONLY,
        )
        assert policy.is_restrictive is False

    def test_allows_network(self):
        """Test allows_network property."""
        deny_policy = SandboxPolicy(network=NetworkPolicy.DENY)
        assert deny_policy.allows_network is False

        allow_policy = SandboxPolicy(network=NetworkPolicy.ALLOW)
        assert allow_policy.allows_network is True

    def test_allows_write(self):
        """Test allows_write property."""
        readonly_policy = SandboxPolicy(filesystem=FilesystemPolicy.READ_ONLY)
        assert readonly_policy.allows_write is False

        temponly_policy = SandboxPolicy(filesystem=FilesystemPolicy.TEMP_ONLY)
        assert temponly_policy.allows_write is True

        readwrite_policy = SandboxPolicy(filesystem=FilesystemPolicy.READ_WRITE)
        assert readwrite_policy.allows_write is True

    def test_is_isolated(self):
        """Test is_isolated property."""
        none_policy = SandboxPolicy(isolation=IsolationLevel.NONE)
        assert none_policy.is_isolated is False

        thread_policy = SandboxPolicy(isolation=IsolationLevel.THREAD)
        assert thread_policy.is_isolated is False

        process_policy = SandboxPolicy(isolation=IsolationLevel.PROCESS)
        assert process_policy.is_isolated is True

        container_policy = SandboxPolicy(isolation=IsolationLevel.CONTAINER)
        assert container_policy.is_isolated is True

        wasm_policy = SandboxPolicy(isolation=IsolationLevel.WASM)
        assert wasm_policy.is_isolated is True

    def test_has_capability(self):
        """Test has_capability method."""
        policy = SandboxPolicy(capabilities={CapabilityGrant.SPAWN_SUBPROCESS, CapabilityGrant.GPU})
        assert policy.has_capability(CapabilityGrant.SPAWN_SUBPROCESS) is True
        assert policy.has_capability(CapabilityGrant.GPU) is True
        assert policy.has_capability(CapabilityGrant.STDIN) is False

    def test_to_dict(self):
        """Test to_dict export."""
        policy = SandboxPolicy(name="test")
        d = policy.to_dict()
        assert d["name"] == "test"
        assert "isolation" in d

    def test_to_matrix_row(self):
        """Test to_matrix_row export."""
        policy = SandboxPolicy(
            name="test",
            limits=ResourceLimit(cpu_seconds=30, memory_mb=512),
            tool_patterns=["a.*", "b.*", "c.*", "d.*"],
        )
        row = policy.to_matrix_row()

        assert row["name"] == "test"
        assert row["isolation"] == "process"
        assert row["network"] == "deny"
        assert row["filesystem"] == "read_only"
        assert "30" in row["cpu_limit"]  # "30s" or "30.0s"
        assert "512" in row["mem_limit"]  # "512MB"
        # Should only show first 3 patterns
        assert "a.*" in row["patterns"]

    def test_to_matrix_row_unlimited(self):
        """Test to_matrix_row with no limits."""
        policy = SandboxPolicy(name="test")
        row = policy.to_matrix_row()

        assert row["cpu_limit"] == "∞"
        assert row["mem_limit"] == "∞"


# --------------------------------------------------------------------------- #
# PolicyRegistry Tests
# --------------------------------------------------------------------------- #
class TestPolicyRegistry:
    """Tests for PolicyRegistry model."""

    def test_basic_registry(self):
        """Test creating basic registry."""
        registry = PolicyRegistry()
        assert registry.policies == []
        assert registry.default_policy is not None

    def test_add_policy(self):
        """Test adding a policy."""
        registry = PolicyRegistry()
        policy = SandboxPolicy(name="test", priority=10)
        registry.add_policy(policy)

        assert len(registry.policies) == 1
        assert registry.policies[0].name == "test"

    def test_add_policy_sorts_by_priority(self):
        """Test that policies are sorted by priority."""
        registry = PolicyRegistry()
        policy1 = SandboxPolicy(name="low", priority=10)
        policy2 = SandboxPolicy(name="high", priority=100)
        policy3 = SandboxPolicy(name="med", priority=50)

        registry.add_policy(policy1)
        registry.add_policy(policy2)
        registry.add_policy(policy3)

        assert registry.policies[0].name == "high"
        assert registry.policies[1].name == "med"
        assert registry.policies[2].name == "low"

    def test_remove_policy(self):
        """Test removing a policy."""
        registry = PolicyRegistry()
        policy = SandboxPolicy(name="test")
        registry.add_policy(policy)

        assert registry.remove_policy("test") is True
        assert len(registry.policies) == 0

    def test_remove_policy_not_found(self):
        """Test removing non-existent policy."""
        registry = PolicyRegistry()
        assert registry.remove_policy("nonexistent") is False

    def test_get_policy_matches(self):
        """Test getting matching policy."""
        policy = SandboxPolicy(
            name="solver",
            tool_patterns=["solver.*"],
        )
        registry = PolicyRegistry(policies=[policy])

        result = registry.get_policy("solver.run")
        assert result.name == "solver"

    def test_get_policy_returns_default(self):
        """Test getting default policy when no match."""
        registry = PolicyRegistry()
        result = registry.get_policy("unknown.tool")
        assert result.name == "default"

    def test_get_all_matching(self):
        """Test getting all matching policies."""
        policy1 = SandboxPolicy(name="p1", tool_patterns=["*"])
        policy2 = SandboxPolicy(name="p2", tool_patterns=["test.*"])
        registry = PolicyRegistry(policies=[policy1, policy2])

        matches = registry.get_all_matching("test.tool")
        assert len(matches) == 2

    def test_to_matrix(self):
        """Test to_matrix export."""
        policy = SandboxPolicy(name="test")
        registry = PolicyRegistry(policies=[policy])

        matrix = registry.to_matrix()
        # Should include policy + default
        assert len(matrix) == 2
        assert matrix[0]["name"] == "test"
        assert matrix[1]["name"] == "default"


# --------------------------------------------------------------------------- #
# Preset Policies Tests
# --------------------------------------------------------------------------- #
class TestPresetPolicies:
    """Tests for preset policies."""

    def test_strict_policy(self):
        """Test STRICT_POLICY settings."""
        assert STRICT_POLICY.name == "strict"
        assert STRICT_POLICY.isolation == IsolationLevel.CONTAINER
        assert STRICT_POLICY.network == NetworkPolicy.DENY
        assert STRICT_POLICY.filesystem == FilesystemPolicy.DENY
        assert STRICT_POLICY.matches("eval.code") is True

    def test_standard_policy(self):
        """Test STANDARD_POLICY settings."""
        assert STANDARD_POLICY.name == "standard"
        assert STANDARD_POLICY.isolation == IsolationLevel.PROCESS
        assert STANDARD_POLICY.matches("compute.task") is True

    def test_permissive_policy(self):
        """Test PERMISSIVE_POLICY settings."""
        assert PERMISSIVE_POLICY.name == "permissive"
        assert PERMISSIVE_POLICY.isolation == IsolationLevel.NONE
        assert PERMISSIVE_POLICY.network == NetworkPolicy.ALLOW
        assert PERMISSIVE_POLICY.matches("internal.tool") is True

    def test_mcp_policy(self):
        """Test MCP_POLICY settings."""
        assert MCP_POLICY.name == "mcp"
        assert MCP_POLICY.isolation == IsolationLevel.NONE
        assert MCP_POLICY.network == NetworkPolicy.ALLOW
        assert MCP_POLICY.filesystem == FilesystemPolicy.DENY
        assert MCP_POLICY.matches("mcp.server") is True

    def test_create_default_registry(self):
        """Test create_default_registry function."""
        registry = create_default_registry()

        # Should include all preset policies
        assert len(registry.policies) == 4

        # Check priority order
        assert registry.policies[0].name == "strict"  # Highest priority

        # Test some lookups
        assert registry.get_policy("eval.code").name == "strict"
        assert registry.get_policy("compute.task").name == "standard"
        assert registry.get_policy("internal.tool").name == "permissive"
        assert registry.get_policy("mcp.server").name == "mcp"
        assert registry.get_policy("unknown.tool").name == "default"


# --------------------------------------------------------------------------- #
# Enum Tests
# --------------------------------------------------------------------------- #
class TestEnums:
    """Tests for enum values."""

    def test_isolation_level_values(self):
        """Test IsolationLevel enum values."""
        assert IsolationLevel.NONE.value == "none"
        assert IsolationLevel.THREAD.value == "thread"
        assert IsolationLevel.PROCESS.value == "process"
        assert IsolationLevel.CONTAINER.value == "container"
        assert IsolationLevel.WASM.value == "wasm"

    def test_network_policy_values(self):
        """Test NetworkPolicy enum values."""
        assert NetworkPolicy.DENY.value == "deny"
        assert NetworkPolicy.LOCALHOST.value == "localhost"
        assert NetworkPolicy.PRIVATE.value == "private"
        assert NetworkPolicy.ALLOW.value == "allow"

    def test_filesystem_policy_values(self):
        """Test FilesystemPolicy enum values."""
        assert FilesystemPolicy.DENY.value == "deny"
        assert FilesystemPolicy.READ_ONLY.value == "read_only"
        assert FilesystemPolicy.TEMP_ONLY.value == "temp_only"
        assert FilesystemPolicy.READ_WRITE.value == "read_write"

    def test_capability_grant_values(self):
        """Test CapabilityGrant enum values."""
        assert CapabilityGrant.SPAWN_SUBPROCESS.value == "spawn_subprocess"
        assert CapabilityGrant.SPAWN_THREADS.value == "spawn_threads"
        assert CapabilityGrant.GPU.value == "gpu"
