#!/usr/bin/env python3
# sample_tools/visit_url_tool.py
"""
VisitURL - sync **and** async.

• `run()`  - blocking httpx.Client (what ToolProcessor uses)
• `arun()` - non-blocking httpx.AsyncClient
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup     # pip install beautifulsoup4
from chuk_tool_processor.registry.decorators import register_tool
from chuk_tool_processor.models.validated_tool import ValidatedTool


# ── helpers ────────────────────────────────────────────────────────
def _unwrap_ddg(url: str) -> str:
    if "duckduckgo.com/l/" not in url:
        return url
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    return urllib.parse.unquote(qs.get("uddg", [""])[0]) or url


def _scrub_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = " ".join(soup.title.get_text(strip=True).split()) if soup.title else ""
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return title, text[:200]


# ── tool class ─────────────────────────────────────────────────────
@register_tool(name="visit_url")
class VisitURL(ValidatedTool):
    """Fetch a web page and return its title + snippet."""

    class Arguments(ValidatedTool.Arguments):
        url: str

    class Result(ValidatedTool.Result):
        title: str
        first_200_chars: str
        url: str
        status: int

    # -------- sync --------------------------------------------------
    def run(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        real = _unwrap_ddg(args.url)
        if not real.startswith(("http://", "https://")):
            real = "https://" + real

        try:
            with httpx.Client(timeout=15, follow_redirects=True) as http:
                rsp = http.get(real, headers={"User-Agent": "a2a_visit_url/2.1"})
            status = rsp.status_code
            html = rsp.text if status == 200 else ""
        except Exception as exc:          # network/TLS errors
            return self.Result(title=real, first_200_chars=f"Error: {exc}", url=real, status=0).model_dump()

        if status == 200:
            title, snip = _scrub_html(html)
            if not title:
                title = real
            preview = snip
        else:
            title = real
            preview = f"Failed to fetch (HTTP {status})"

        return self.Result(title=title, first_200_chars=preview, url=real, status=status).model_dump()

    # -------- async -------------------------------------------------
    async def arun(self, **kwargs) -> Dict:
        args = self.Arguments(**kwargs)
        real = _unwrap_ddg(args.url)
        if not real.startswith(("http://", "https://")):
            real = "https://" + real

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
                rsp = await http.get(real, headers={"User-Agent": "a2a_visit_url/2.1"})
            status = rsp.status_code
            html = rsp.text if status == 200 else ""
        except Exception as exc:
            return self.Result(title=real, first_200_chars=f"Error: {exc}", url=real, status=0).model_dump()

        if status == 200:
            title, snip = _scrub_html(html)
            if not title:
                title = real
            preview = snip
        else:
            title = real
            preview = f"Failed to fetch (HTTP {status})"

        return self.Result(title=title, first_200_chars=preview, url=real, status=status).model_dump()
