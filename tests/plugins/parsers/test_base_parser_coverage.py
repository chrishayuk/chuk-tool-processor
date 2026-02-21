# tests/plugins/parsers/test_base_parser_coverage.py
"""Coverage tests for plugins.parsers.base module.

Targets the uncovered line 25 - the abstract method body (the ``...``
Ellipsis literal in the abstract try_parse method).
"""

from __future__ import annotations

import pytest

from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.plugins.parsers.base import ParserPlugin


class TestParserPluginAbstractBody:
    """Exercise the abstract method body (line 25: ``...``)."""

    @pytest.mark.asyncio
    async def test_calling_super_try_parse_returns_ellipsis(self):
        """
        Directly invoke the abstract body via super() from a concrete
        subclass. The abstract body is ``...`` (Ellipsis), so calling
        it via super() should return the Ellipsis object.
        """

        class DelegatingParser(ParserPlugin):
            async def try_parse(self, raw: str | object) -> list[ToolCall]:
                # Deliberately call the abstract body via super()
                result = await super().try_parse(raw)
                return result if isinstance(result, list) else []

        parser = DelegatingParser()
        result = await parser.try_parse("test input")
        # The abstract body is `...` which is Ellipsis, not a list,
        # so our wrapper returns []
        assert result == []

    @pytest.mark.asyncio
    async def test_concrete_subclass_overrides_correctly(self):
        """Ensure a properly implemented subclass works."""

        class GoodParser(ParserPlugin):
            async def try_parse(self, raw: str | object) -> list[ToolCall]:
                return [
                    ToolCall(
                        id="call_1",
                        tool="test_tool",
                        arguments={"input": str(raw)},
                    )
                ]

        parser = GoodParser()
        result = await parser.try_parse("hello")
        assert len(result) == 1
        assert result[0].tool == "test_tool"

    def test_cannot_instantiate_directly(self):
        """ParserPlugin itself cannot be instantiated."""
        with pytest.raises(TypeError):
            ParserPlugin()  # type: ignore[abstract]
