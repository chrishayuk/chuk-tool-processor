"""Basic tests for the *ParserPlugin* ABC."""

import pytest

from chuk_tool_processor.plugins.parsers.base import ParserPlugin


def test_cannot_instantiate_abstract():
    # Attempting to instantiate without implementing try_parse should fail
    with pytest.raises(TypeError):
        class Bad(ParserPlugin):
            pass
        Bad()


def test_dummy_subclass_works():
    class Good(ParserPlugin):
        def try_parse(self, raw):
            return []

    g = Good()
    assert g.try_parse("whatever") == []
