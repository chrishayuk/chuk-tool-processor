#!/usr/bin/env python3
# sample_tools/search_tool.py
"""
sample_tools/search_tool.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

DuckDuckGo HTML search tool using the ValidatedTool contract.

• Queries the *html.duckduckgo.com* endpoint directly.
• Strips DDG redirect wrappers so callers get plain target URLs.
• Returns a structured `Result` model.

This version implements the blocking **_execute()** method required by
ValidatedTool; the base-class `run()` will take care of validation and
serialisation.  An async façade (`arun`) off-loads the blocking call to a
thread so the main event-loop is never blocked.
"""

from __future__ import annotations

import asyncio
import re
import time
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from chuk_tool_processor.models.validated_tool import ValidatedTool
from chuk_tool_processor.registry.decorators import register_tool

# ───────────────────────────── helpers ──────────────────────────────
_DDG_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {"User-Agent": "a2a_demo_search_tool/1.3 (+https://example.com)"}


def _clean_ddg_link(raw: str) -> str:
    """Return the direct target for DDG redirect URLs, else *raw*."""
    if not raw.startswith("//duckduckgo.com/l/"):
        return raw
    qs = parse_qs(urlparse(raw).query)
    return unquote(qs.get("uddg", [""])[0]) or raw


def _search_ddg_html(query: str, max_results: int) -> list[dict]:
    """Scrape DuckDuckGo HTML search results (blocking I/O)."""
    with httpx.Client(timeout=8, headers=_HEADERS, follow_redirects=True) as client:
        rsp = client.get(_DDG_URL, params={"q": query})
        rsp.raise_for_status()

    pattern = re.compile(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>'
        r"(?P<title>.*?)</a>",
        re.S,
    )

    hits: list[dict] = []
    for m in pattern.finditer(rsp.text):
        title = unescape(re.sub(r"<[^>]+>", "", m.group("title")))
        url = _clean_ddg_link(unescape(m.group("url")))
        hits.append({"title": title, "url": url})
        if len(hits) >= max_results:
            break
    return hits


# ───────────────────────────── tool class ───────────────────────────
@register_tool(name="search")
class SearchTool(ValidatedTool):
    """DuckDuckGo search — returns a list of result dicts."""

    # ----- validated schemas ----------------------------------------
    class Arguments(ValidatedTool.Arguments):
        query: str
        max_results: int = 5

    class Result(ValidatedTool.Result):
        results: list[dict]

    # ----- REQUIRED blocking implementation -------------------------
    def _execute(self, *, query: str, max_results: int) -> dict:
        """
        Blocking core that actually performs the search.

        Called by the base-class `run()` after argument validation.
        """
        time.sleep(0.4)  # small politeness delay
        hits = _search_ddg_html(query, max_results)
        return {"results": hits}

    # ----- OPTIONAL async façade ------------------------------------
    async def arun(self, **kwargs) -> dict:
        """
        Async wrapper around `_execute()` so callers can `await` the tool
        without blocking the event-loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._execute(**kwargs))
