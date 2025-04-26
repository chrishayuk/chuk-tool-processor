# tests/tool_processor/models/test_tool_result.py
import pytest
from pydantic import ValidationError

from chuk_tool_processor.models.tool_result import ToolResult


def test_tool_result_defaults():
    # Provide only required fields
    res = ToolResult(tool='t1', result={'data': 42})
    assert res.tool == 't1'
    assert res.result == {'data': 42}
    assert res.error is None


def test_tool_result_with_error():
    # Provide explicit error
    res = ToolResult(tool='t2', result=None, error='failure')
    assert res.tool == 't2'
    assert res.result is None
    assert res.error == 'failure'

@pytest.mark.parametrize('invalid_tool', [None, 123, '', [], {}])
def test_invalid_tool_field(invalid_tool):
    # tool must be non-empty string
    with pytest.raises(ValidationError):
        ToolResult(tool=invalid_tool, result=123)

@pytest.mark.parametrize('invalid_error', [123, [], {}, object()])
def test_invalid_error_field(invalid_error):
    # error must be Optional[str]
    with pytest.raises(ValidationError):
        ToolResult(tool='t', result='ok', error=invalid_error)

@pytest.mark.parametrize('invalid_result', [pytest.mark.skip, object()])
def test_invalid_result_field(invalid_result):
    # result can be any type, so no validation error
    # Using a dummy object should work
    dummy = invalid_result
    res = ToolResult(tool='t3', result=dummy)
    assert res.result is dummy


def test_extra_fields_ignored():
    # Unexpected extra fields should be ignored
    res = ToolResult(tool='t4', result=123, extra='ignore')  # type: ignore
    assert res.tool == 't4'
    assert not hasattr(res, 'extra')

