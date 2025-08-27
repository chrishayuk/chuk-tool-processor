# tests/plugins/plugins/parser/test_base.py
"""Basic tests for the async-native *ParserPlugin* ABC."""

from __future__ import annotations

import inspect

import pytest

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def is_coroutine(fn) -> bool:
    """Return *True* if *fn* is an async coroutine function."""
    return inspect.iscoroutinefunction(fn)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_cannot_instantiate_abstract():
    """Subclass without *try_parse* must stay abstract."""
    with pytest.raises(TypeError):

        class Bad(ParserPlugin):
            pass

        Bad()  # noqa: B024 - we expect this to raise


@pytest.mark.asyncio
async def test_dummy_subclass_works():
    """A minimal, correct implementation should instantiate and run."""

    class Good(ParserPlugin):
        async def try_parse(self, raw) -> list[ToolCall]:  # type: ignore[override]
            # Just return empty list regardless of input
            return []

    g = Good()
    # ensure the overridden method is async
    assert is_coroutine(g.try_parse)

    # Call the coroutine and verify it returns an empty list
    result = await g.try_parse("whatever")
    assert result == []
