"""Unit‑tests for ToolProcessor – regression for unhashable arguments                                 

Run with::

    pytest -q tests/test_processor.py
"""
import asyncio
from datetime import datetime, timezone

import pytest

import chuk_tool_processor.core.processor as processor_module
from chuk_tool_processor.core.processor import ToolProcessor, default_processor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.plugins.discovery import plugin_registry


# ---------------------------------------------------------------------------
# Dummy helpers                                                               
# ---------------------------------------------------------------------------
class DummyParser:
    """Parser that yields one call when it sees the token *dummy* in the text."""

    def try_parse(self, raw: str):
        if "dummy" in raw:
            return [ToolCall(tool="t1", arguments={"x": 1})]
        return []


class DummyExecutor:
    """Captures execute() invocations and fabricates matching ToolResults."""

    def __init__(self):
        self.calls = []  # list[(calls, timeout)] – every execute() invocation

    async def execute(self, calls, timeout=None):  # noqa: D401
        self.calls.append((calls, timeout))
        results = []
        for call in calls:
            results.append(
                ToolResult(
                    tool=call.tool,
                    result={"args": call.arguments},
                    error=None,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    machine="test",
                    pid=0,
                    cached=False,
                )
            )
        return results


# ---------------------------------------------------------------------------
# Fixtures                                                                     
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clear_parsers(monkeypatch):
    """Swap in a single DummyParser so real plugins aren’t hit."""

    monkeypatch.setattr(
        plugin_registry,
        "list_plugins",
        lambda category=None: {"parser": ["Dummy"]} if category is None else ["Dummy"],
    )
    monkeypatch.setattr(
        plugin_registry,
        "get_plugin",
        lambda category, name: DummyParser() if name == "Dummy" else None,
    )
    yield


@pytest.fixture
def processor():
    """Minimal ToolProcessor wired with DummyExecutor (no cache/rate‑limit/retry)."""

    tp = ToolProcessor(enable_caching=False, enable_rate_limiting=False, enable_retries=False)
    tp.executor = DummyExecutor()  # type: ignore[attr-defined]
    return tp


# ---------------------------------------------------------------------------
# Regression: unhashable list in arguments                                      
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unhashable_arguments_processed(processor):
    """Processor should handle list-valued arguments without crashing."""
    
    class ListArgParser:
        def try_parse(self, raw: str):
            if "listargs" in raw:
                return [ToolCall(tool="tlist", arguments={"hosts": ["a", "b"]})]
            return []

    # Swap parsers to emit the problematic call
    processor.parsers = [ListArgParser()]

    # Prior to the fix this raised `TypeError: unhashable type: 'list'`
    results = await processor.process_text("contains listargs")

    # After the fix it should simply return one successful result
    assert len(results) == 1
    assert results[0].tool == "tlist"

# ---------------------------------------------------------------------------
# Modern behaviour (post‑fix)                                                 
# ---------------------------------------------------------------------------                                                                        
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_process_text_no_calls(processor):
    """Text without the trigger token should yield an empty result list."""

    results = await processor.process_text("no calls here")
    assert results == []


@pytest.mark.asyncio
async def test_process_text_single_call(processor):
    text = "this text has dummy"
    results = await processor.process_text(text, timeout=5.0)

    # executor was invoked once and got the explicit timeout
    assert len(processor.executor.calls) == 1  # type: ignore[attr-defined]
    calls, used_timeout = processor.executor.calls[0]  # type: ignore[attr-defined]
    assert used_timeout == 5.0
    assert isinstance(calls[0], ToolCall)

    # processor returned exactly one ToolResult with the expected payload
    assert len(results) == 1
    res = results[0]
    assert res.tool == "t1"
    assert res.result == {"args": {"x": 1}}


@pytest.mark.asyncio
async def test_duplicate_calls_removed(processor):
    """Two identical calls must collapse to one after de‑duplication."""

    class DupParser:
        def try_parse(self, raw):
            return [
                ToolCall(tool="t2", arguments={"y": 2}),
                ToolCall(tool="t2", arguments={"y": 2}),
            ]

    processor.parsers = [DupParser()]
    results = await processor.process_text("any text")

    # executor received only one unique call
    assert len(processor.executor.calls) == 1  # type: ignore[attr-defined]
    calls, _ = processor.executor.calls[0]  # type: ignore[attr-defined]
    assert len(calls) == 1
    assert calls[0].tool == "t2"

    # and the processor returned one result entry
    assert len(results) == 1


@pytest.mark.asyncio
async def test_unknown_tool_logging(monkeypatch, caplog):
    """Unknown tools should generate a warning but still return a result stub."""

    class UnknownParser:
        def try_parse(self, raw):
            return [ToolCall(tool="unknown", arguments={})]

    tp = ToolProcessor(enable_caching=False, enable_rate_limiting=False, enable_retries=False)
    tp.parsers = [UnknownParser()]
    tp.executor = DummyExecutor()  # type: ignore[attr-defined]

    # Pretend the registry doesn’t have this tool
    monkeypatch.setattr(tp.registry, "get_tool", lambda name: None)

    caplog.set_level("WARNING")
    results = await tp.process_text("trigger unknown")

    assert any("Unknown tools: ['unknown']" in rec.message for rec in caplog.records)
    assert len(results) == 1


def test_default_process_text_wrapper(monkeypatch):
    """The public wrapper should forward its arguments untouched."""

    called: dict = {}

    async def fake(text, timeout=None, use_cache=None, request_id=None):  # noqa: D401
        called["args"] = (text, timeout, use_cache, request_id)
        return []

    monkeypatch.setattr(default_processor, "process_text", fake)

    coro = processor_module.process_text("abc", timeout=1.2, use_cache=False, request_id="rid")
    results = asyncio.get_event_loop().run_until_complete(coro)

    assert called["args"] == ("abc", 1.2, False, "rid")
    assert results == []
