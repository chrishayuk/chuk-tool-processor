# tests/guards/test_models.py
"""Tests for guards models."""

from chuk_tool_processor.guards.models import EnforcementLevel, ToolClassification


class TestEnforcementLevel:
    """Tests for EnforcementLevel enum."""

    def test_enforcement_levels_exist(self):
        """Test all enforcement levels are defined."""
        assert EnforcementLevel.OFF == "off"
        assert EnforcementLevel.WARN == "warn"
        assert EnforcementLevel.BLOCK == "block"


class TestToolClassification:
    """Tests for ToolClassification methods."""

    def test_is_discovery_tool_simple_name(self):
        """Test discovery tool check with simple name."""
        assert ToolClassification.is_discovery_tool("list_tools")
        assert ToolClassification.is_discovery_tool("search_tools")
        assert not ToolClassification.is_discovery_tool("some_other_tool")

    def test_is_discovery_tool_namespaced(self):
        """Test discovery tool check with namespaced name (lines 78-79)."""
        assert ToolClassification.is_discovery_tool("namespace.list_tools")
        assert ToolClassification.is_discovery_tool("a.b.search_tools")
        assert not ToolClassification.is_discovery_tool("namespace.other")

    def test_is_idempotent_math_tool_simple_name(self):
        """Test idempotent math tool check with simple name."""
        assert ToolClassification.is_idempotent_math_tool("add")
        assert ToolClassification.is_idempotent_math_tool("sqrt")
        assert not ToolClassification.is_idempotent_math_tool("create_user")

    def test_is_idempotent_math_tool_namespaced(self):
        """Test idempotent math tool check with namespaced name (lines 84-85)."""
        assert ToolClassification.is_idempotent_math_tool("math.add")
        assert ToolClassification.is_idempotent_math_tool("ns.multiply")
        assert not ToolClassification.is_idempotent_math_tool("ns.other")

    def test_is_parameterized_tool_simple_name(self):
        """Test parameterized tool check with simple name."""
        assert ToolClassification.is_parameterized_tool("normal_cdf")
        assert ToolClassification.is_parameterized_tool("t_test")
        assert not ToolClassification.is_parameterized_tool("add")

    def test_is_parameterized_tool_namespaced(self):
        """Test parameterized tool check with namespaced name (lines 90-91)."""
        assert ToolClassification.is_parameterized_tool("stats.normal_cdf")
        assert ToolClassification.is_parameterized_tool("a.b.chi_square")
        assert not ToolClassification.is_parameterized_tool("ns.add")

    def test_classify_side_effect_read_only(self):
        """Test classify_side_effect returns read_only for read patterns."""
        assert ToolClassification.classify_side_effect("get_user") == "read_only"
        assert ToolClassification.classify_side_effect("list_items") == "read_only"
        assert ToolClassification.classify_side_effect("search_products") == "read_only"
        assert ToolClassification.classify_side_effect("fetch_data") == "read_only"

    def test_classify_side_effect_write(self):
        """Test classify_side_effect returns write for write patterns."""
        assert ToolClassification.classify_side_effect("create_user") == "write"
        assert ToolClassification.classify_side_effect("update_record") == "write"
        assert ToolClassification.classify_side_effect("save_file") == "write"

    def test_classify_side_effect_destructive(self):
        """Test classify_side_effect returns destructive for destructive patterns."""
        assert ToolClassification.classify_side_effect("delete_user") == "destructive"
        assert ToolClassification.classify_side_effect("remove_item") == "destructive"
        assert ToolClassification.classify_side_effect("drop_table") == "destructive"

    def test_classify_side_effect_default_to_write(self):
        """Test classify_side_effect defaults to write for unknown patterns (line 196)."""
        # A tool name that doesn't match any patterns
        assert ToolClassification.classify_side_effect("do_something") == "write"
        assert ToolClassification.classify_side_effect("execute_task") == "write"
        assert ToolClassification.classify_side_effect("run_job") == "write"

    def test_is_network_tool_simple(self):
        """Test is_network_tool with simple names."""
        assert ToolClassification.is_network_tool("http_get")
        assert ToolClassification.is_network_tool("fetch_url")
        assert ToolClassification.is_network_tool("api_call")
        assert not ToolClassification.is_network_tool("add_numbers")

    def test_is_network_tool_namespaced(self):
        """Test is_network_tool with namespaced names (lines 201-202)."""
        assert ToolClassification.is_network_tool("net.http_request")
        assert ToolClassification.is_network_tool("web.fetch_page")
        assert ToolClassification.is_network_tool("a.b.webhook_send")
        assert not ToolClassification.is_network_tool("math.add")

    def test_get_base_name_helper(self):
        """Test the _get_base_name helper method."""
        assert ToolClassification._get_base_name("simple") == "simple"
        assert ToolClassification._get_base_name("namespace.tool") == "tool"
        assert ToolClassification._get_base_name("a.b.c.deep") == "deep"
        assert ToolClassification._get_base_name("UPPERCASE") == "uppercase"
        assert ToolClassification._get_base_name("ns.MIXED") == "mixed"
