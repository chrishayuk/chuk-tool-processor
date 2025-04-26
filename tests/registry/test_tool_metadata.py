# tests/tool_processor/registry/test_tool_metadata.py
import pytest
from pydantic import ValidationError

from chuk_tool_processor.registry.metadata import ToolMetadata


def test_defaults_and_str():
    tm = ToolMetadata(name="my_tool")
    assert tm.name == "my_tool"
    assert tm.namespace == "default"
    assert tm.description is None
    assert tm.version == "1.0.0"
    assert tm.is_async is False
    assert tm.argument_schema is None
    assert tm.result_schema is None
    assert tm.requires_auth is False
    assert isinstance(tm.tags, set) and len(tm.tags) == 0
    assert str(tm) == "default.my_tool (v1.0.0)"


def test_custom_values_and_tags_independence():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    tm1 = ToolMetadata(
        name="foo",
        namespace="ns",
        description="desc",
        version="2.3.4",
        is_async=True,
        argument_schema=schema,
        result_schema={"type": "string"},
        requires_auth=True,
        tags={"a", "b"},
    )
    tm2 = ToolMetadata(name="bar")

    assert tm1.tags == {"a", "b"}
    tm1.tags.add("c")
    assert tm1.tags == {"a", "b", "c"}
    assert tm2.tags == set()


def test_missing_name_raises():
    with pytest.raises(ValidationError) as excinfo:
        ToolMetadata()
    assert "Field required" in str(excinfo.value)


def test_invalid_name_type_raises():
    with pytest.raises(ValidationError):
        ToolMetadata(name=123)  # name must be str


def test_is_async_coerced_to_bool():
    tm1 = ToolMetadata(name="t1", is_async="yes")
    assert tm1.is_async is True
    tm2 = ToolMetadata(name="t2", is_async=0)
    assert tm2.is_async is False


def test_tags_coerced_to_set():
    tm = ToolMetadata(name="t", tags=["a", "b", "a"])
    assert isinstance(tm.tags, set)
    assert tm.tags == {"a", "b"}


def test_partial_override_defaults():
    tm = ToolMetadata(name="t", namespace="custom_ns")
    assert tm.namespace == "custom_ns"
    assert tm.version == "1.0.0"


def test_str_reflects_overrides():
    tm = ToolMetadata(name="name", namespace="my_ns", version="9.9.9")
    assert str(tm) == "my_ns.name (v9.9.9)"
