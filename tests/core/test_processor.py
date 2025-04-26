import asyncio
import pytest
from datetime import datetime, timezone

import chuk_tool_processor.core.processor as processor_module
from chuk_tool_processor.core.processor import ToolProcessor, default_processor
from chuk_tool_processor.models.tool_call import ToolCall
from chuk_tool_processor.models.tool_result import ToolResult
from chuk_tool_processor.plugins.discovery import plugin_registry


class DummyParser:
    """Parser that returns a fixed ToolCall when seeing 'dummy' in text"""
    def try_parse(self, raw: str):
        if 'dummy' in raw:
            return [ToolCall(tool='t1', arguments={'x': 1})]
        return []


class DummyExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, calls, timeout=None):
        # record calls and return ToolResult for each
        self.calls.append((calls, timeout))
        results = []
        for call in calls:
            res = ToolResult(
                tool=call.tool,
                result={'args': call.arguments},
                error=None,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                machine='test',
                pid=0,
                cached=False
            )
            results.append(res)
        return results


@pytest.fixture(autouse=True)
def clear_parsers(monkeypatch):
    # Replace existing parsers with only DummyParser
    monkeypatch.setattr(plugin_registry, 'list_plugins', lambda category=None: {'parser': ['Dummy']} if category is None else ['Dummy'])
    monkeypatch.setattr(plugin_registry, 'get_plugin', lambda category, name: DummyParser() if name == 'Dummy' else None)
    yield


@pytest.fixture
def processor():
    # Create a ToolProcessor with dummy executor
    tp = ToolProcessor(enable_caching=False, enable_rate_limiting=False, enable_retries=False)
    # Replace executor
    dummy_exec = DummyExecutor()
    tp.executor = dummy_exec
    return tp


@pytest.mark.asyncio
async def test_process_text_no_calls(processor):
    # Text without 'dummy' should yield empty list
    results = await processor.process_text("no calls here")
    assert results == []


@pytest.mark.asyncio
async def test_process_text_single_call(processor):
    text = "this text has dummy"
    results = await processor.process_text(text, timeout=5.0)
    # Should call executor with one call and propagate timeout
    assert len(processor.executor.calls) == 1
    calls, used_timeout = processor.executor.calls[0]
    assert used_timeout == 5.0
    assert isinstance(calls[0], ToolCall)
    # Check result content
    assert len(results) == 1
    res = results[0]
    assert res.tool == 't1'
    assert res.result == {'args': {'x': 1}}


@pytest.mark.asyncio
async def test_duplicate_calls_removed(processor):
    # If parser returns duplicates, only one should be executed
    class DupParser:
        def try_parse(self, raw):
            return [ToolCall(tool='t2', arguments={'y': 2}), ToolCall(tool='t2', arguments={'y': 2})]
    # Monkeypatch parsers
    processor.parsers = [DupParser()]
    results = await processor.process_text("any text")
    # Executor should be called once with a single unique call
    assert len(processor.executor.calls) == 1
    calls, _ = processor.executor.calls[0]
    assert len(calls) == 1
    assert calls[0].tool == 't2'


@pytest.mark.asyncio
async def test_unknown_tool_logging(monkeypatch, caplog):
    # Parser returns a tool not in registry
    class UnknownParser:
        def try_parse(self, raw):
            return [ToolCall(tool='unknown', arguments={})]
    p = ToolProcessor(enable_caching=False, enable_rate_limiting=False, enable_retries=False)
    # stub parsers and registry.get_tool
    p.parsers = [UnknownParser()]
    monkeypatch.setattr(p.registry, 'get_tool', lambda name: None)
    # Replace executor to no-op
    p.executor = DummyExecutor()
    caplog.set_level('WARNING')
    results = await p.process_text("trigger unknown")
    # Should warn about unknown tool
    assert any("Unknown tools: ['unknown']" in rec.message for rec in caplog.records)
    # Still returns a result list of length 1
    assert len(results) == 1


def test_default_process_text_wrapper(monkeypatch):
    # Ensure default_processor delegates
    called = {}
    async def fake(text, timeout=None, use_cache=None, request_id=None):
        called['args'] = (text, timeout, use_cache, request_id)
        return []
    monkeypatch.setattr(default_processor, 'process_text', fake)
    # Run wrapper
    coro = processor_module.process_text('abc', timeout=1.2, use_cache=False, request_id='rid')
    results = asyncio.get_event_loop().run_until_complete(coro)
    assert called['args'] == ('abc', 1.2, False, 'rid')
    assert results == []
