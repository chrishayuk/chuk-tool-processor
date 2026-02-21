# tests/models/test_tool_spec_coverage.py
"""Coverage tests for ToolSpec export methods and edge cases.

Targets the uncovered export methods: to_openai, to_anthropic, to_mcp,
to_json_schema, to_dict, and edge cases around examples/icon/returns/
allowed_callers fields.
"""

from __future__ import annotations

from chuk_tool_processor.models.tool_spec import ToolCapability, ToolSpec


def _make_spec(**overrides) -> ToolSpec:
    """Helper to create a ToolSpec with sensible defaults."""
    defaults = {
        "name": "test_tool",
        "description": "A test tool for unit tests",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    defaults.update(overrides)
    return ToolSpec(**defaults)


# ------------------------------------------------------------------ #
# to_openai (to_openai)
# ------------------------------------------------------------------ #
class TestToOpenAI:
    """Tests for ToolSpec.to_openai() export."""

    def test_basic_export(self):
        spec = _make_spec()
        result = spec.to_openai()
        assert result["type"] == "function"
        assert result["function"]["name"] == "test_tool"
        assert result["function"]["description"] == "A test tool for unit tests"
        assert result["function"]["parameters"] == spec.parameters

    def test_without_examples(self):
        spec = _make_spec(examples=[])
        result = spec.to_openai()
        assert "examples" not in result["function"]

    def test_with_examples(self):
        examples = [{"input": {"query": "hello"}, "output": "world"}]
        spec = _make_spec(examples=examples)
        result = spec.to_openai()
        assert result["function"]["examples"] == examples


# ------------------------------------------------------------------ #
# to_anthropic
# ------------------------------------------------------------------ #
class TestToAnthropic:
    """Tests for ToolSpec.to_anthropic() export."""

    def test_basic_export(self):
        spec = _make_spec()
        result = spec.to_anthropic()
        assert result["name"] == "test_tool"
        assert result["description"] == "A test tool for unit tests"
        assert result["input_schema"] == spec.parameters

    def test_without_optional_fields(self):
        spec = _make_spec(examples=[], allowed_callers=None)
        result = spec.to_anthropic()
        assert "allowed_callers" not in result
        assert "examples" not in result

    def test_with_allowed_callers(self):
        spec = _make_spec(allowed_callers=["claude", "programmatic"])
        result = spec.to_anthropic()
        assert result["allowed_callers"] == ["claude", "programmatic"]

    def test_with_examples(self):
        examples = [{"input": {"query": "test"}, "output": "result"}]
        spec = _make_spec(examples=examples)
        result = spec.to_anthropic()
        assert result["examples"] == examples


# ------------------------------------------------------------------ #
# to_mcp
# ------------------------------------------------------------------ #
class TestToMCP:
    """Tests for ToolSpec.to_mcp() export."""

    def test_basic_export(self):
        spec = _make_spec()
        result = spec.to_mcp()
        assert result["name"] == "test_tool"
        assert result["description"] == "A test tool for unit tests"
        assert result["inputSchema"] == spec.parameters

    def test_without_optional_fields(self):
        spec = _make_spec(returns=None, examples=[], icon=None)
        result = spec.to_mcp()
        assert "outputSchema" not in result
        assert "examples" not in result
        assert "icon" not in result

    def test_with_returns(self):
        returns_schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        spec = _make_spec(returns=returns_schema)
        result = spec.to_mcp()
        assert result["outputSchema"] == returns_schema

    def test_with_examples(self):
        examples = [{"input": {"query": "test"}, "output": "result"}]
        spec = _make_spec(examples=examples)
        result = spec.to_mcp()
        assert result["examples"] == examples

    def test_with_icon(self):
        spec = _make_spec(icon="https://example.com/icon.png")
        result = spec.to_mcp()
        assert result["icon"] == "https://example.com/icon.png"

    def test_all_optional_fields(self):
        returns_schema = {"type": "string"}
        examples = [{"input": {}, "output": "ok"}]
        spec = _make_spec(
            returns=returns_schema,
            examples=examples,
            icon="data:image/png;base64,abc",
        )
        result = spec.to_mcp()
        assert result["outputSchema"] == returns_schema
        assert result["examples"] == examples
        assert result["icon"] == "data:image/png;base64,abc"


# ------------------------------------------------------------------ #
# to_json_schema
# ------------------------------------------------------------------ #
class TestToJsonSchema:
    """Tests for ToolSpec.to_json_schema() export."""

    def test_returns_parameters(self):
        spec = _make_spec()
        assert spec.to_json_schema() is spec.parameters


# ------------------------------------------------------------------ #
# to_dict
# ------------------------------------------------------------------ #
class TestToDict:
    """Tests for ToolSpec.to_dict() export."""

    def test_basic_export(self):
        spec = _make_spec()
        d = spec.to_dict()
        assert d["name"] == "test_tool"
        assert d["description"] == "A test tool for unit tests"
        assert "parameters" in d

    def test_excludes_none_values(self):
        spec = _make_spec(returns=None, author=None, license=None)
        d = spec.to_dict()
        assert "returns" not in d
        assert "author" not in d
        assert "license" not in d

    def test_includes_non_none_values(self):
        spec = _make_spec(
            version="2.0.0",
            author="tester",
            license="MIT",
            tags=["search"],
        )
        d = spec.to_dict()
        assert d["version"] == "2.0.0"
        assert d["author"] == "tester"
        assert d["license"] == "MIT"
        assert d["tags"] == ["search"]

    def test_roundtrip_consistency(self):
        """to_dict output can recreate the spec (minus None fields)."""
        spec = _make_spec(
            capabilities=[ToolCapability.CACHEABLE],
            tags=["util"],
            version="1.2.3",
        )
        d = spec.to_dict()
        reconstructed = ToolSpec(**d)
        assert reconstructed.name == spec.name
        assert reconstructed.version == spec.version
        assert reconstructed.capabilities == spec.capabilities


# ------------------------------------------------------------------ #
# Contract-based properties (lines 138-186)
# ------------------------------------------------------------------ #
class TestContractProperties:
    """Tests for contract-based property methods on ToolSpec."""

    def test_is_deterministic_no_contract(self):
        spec = _make_spec(contract=None)
        assert spec.is_deterministic is False

    def test_is_deterministic_pure(self):
        from chuk_tool_processor.models.tool_contract import (
            Determinism,
            ToolContract,
        )

        contract = ToolContract(determinism=Determinism.PURE)
        spec = _make_spec(contract=contract)
        assert spec.is_deterministic is True

    def test_is_deterministic_impure(self):
        from chuk_tool_processor.models.tool_contract import (
            Determinism,
            ToolContract,
        )

        contract = ToolContract(determinism=Determinism.IMPURE)
        spec = _make_spec(contract=contract)
        assert spec.is_deterministic is False

    def test_is_safe_to_retry_idempotent_capability(self):
        spec = _make_spec(capabilities=[ToolCapability.IDEMPOTENT])
        assert spec.is_safe_to_retry is True

    def test_is_safe_to_retry_from_contract(self):
        from chuk_tool_processor.models.tool_contract import (
            Determinism,
            SideEffectClass,
            ToolContract,
        )

        # A contract with NONE side effects is safe to retry
        contract = ToolContract(
            determinism=Determinism.PURE,
            side_effects=SideEffectClass.NONE,
        )
        spec = _make_spec(contract=contract)
        assert spec.is_safe_to_retry is True

    def test_is_safe_to_retry_false(self):
        spec = _make_spec(capabilities=[], contract=None)
        assert spec.is_safe_to_retry is False

    def test_cost_hint_no_contract(self):
        spec = _make_spec(contract=None)
        assert spec.cost_hint == 1

    def test_cost_hint_from_contract(self):
        from chuk_tool_processor.models.tool_contract import ToolContract

        contract = ToolContract(cost_hint=42)
        spec = _make_spec(contract=contract)
        assert spec.cost_hint == 42

    def test_validate_arguments_no_contract(self):
        spec = _make_spec(contract=None)
        assert spec.validate_arguments({"x": 1}) == []

    def test_validate_arguments_with_contract_violation(self):
        from chuk_tool_processor.models.tool_contract import ToolContract

        contract = ToolContract(requires=["n > 0"])
        spec = _make_spec(contract=contract)
        result = spec.validate_arguments({"n": -1})
        assert len(result) >= 1
        assert any("n > 0" in msg for msg in result)

    def test_validate_arguments_no_violations(self):
        from chuk_tool_processor.models.tool_contract import ToolContract

        contract = ToolContract(requires=["n > 0"])
        spec = _make_spec(contract=contract)
        result = spec.validate_arguments({"n": 5})
        assert result == []

    def test_validate_result_no_contract(self):
        spec = _make_spec(contract=None)
        assert spec.validate_result({"x": 1}, 42) == []

    def test_validate_result_with_contract_violation(self):
        from chuk_tool_processor.models.tool_contract import ToolContract

        contract = ToolContract(ensures=["result >= 0"])
        spec = _make_spec(contract=contract)
        result = spec.validate_result({"x": 1}, -5)
        assert len(result) >= 1
        assert any("result >= 0" in msg for msg in result)

    def test_validate_result_no_violations(self):
        from chuk_tool_processor.models.tool_contract import ToolContract

        contract = ToolContract(ensures=["result >= 0"])
        spec = _make_spec(contract=contract)
        result = spec.validate_result({"x": 1}, 10)
        assert result == []


# ------------------------------------------------------------------ #
# Capability checks (lines 118-132)
# ------------------------------------------------------------------ #
class TestCapabilityChecks:
    """Tests for capability helper methods."""

    def test_has_capability_true(self):
        spec = _make_spec(capabilities=[ToolCapability.STREAMING])
        assert spec.has_capability(ToolCapability.STREAMING) is True

    def test_has_capability_false(self):
        spec = _make_spec(capabilities=[])
        assert spec.has_capability(ToolCapability.STREAMING) is False

    def test_is_streaming(self):
        spec = _make_spec(capabilities=[ToolCapability.STREAMING])
        assert spec.is_streaming() is True

    def test_is_not_streaming(self):
        spec = _make_spec(capabilities=[])
        assert spec.is_streaming() is False

    def test_is_idempotent(self):
        spec = _make_spec(capabilities=[ToolCapability.IDEMPOTENT])
        assert spec.is_idempotent() is True

    def test_is_cacheable(self):
        spec = _make_spec(capabilities=[ToolCapability.CACHEABLE])
        assert spec.is_cacheable() is True

    def test_is_not_cacheable(self):
        spec = _make_spec(capabilities=[])
        assert spec.is_cacheable() is False
