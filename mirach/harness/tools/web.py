"""Web tools: web_search (DuckDuckGo, no key), web_fetch (URL → text)."""

from __future__ import annotations

import html
import html.parser
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mirach.harness.providers.base import ToolDef

_UA = "Mozilla/5.0 (compatible; Mirach/1.0)"
_FETCH_LIMIT = 32_000  # bytes — enough for most pages
_TIMEOUT = 15

WEB_SEARCH_DEF = ToolDef(
    name="web_search",
    description=(
        "Search the web using DuckDuckGo (no API key required). "
        "Returns a list of results with titles, URLs, and snippets."
    ),
    parameters={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 8, max 20).",
            },
        },
    },
)

WEB_FETCH_DEF = ToolDef(
    name="web_fetch",
    description=(
        "Fetch a URL and return its text content (HTML is stripped to plain text). "
        "Returns up to 32 KB."
    ),
    parameters={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string", "description": "URL to fetch."},
        },
    },
)


# ── implementations ───────────────────────────────────────────────────────────


def web_search(args: dict[str, Any]) -> str:
    query: str = args["query"]
    max_results: int = min(int(args.get("max_results", 8)), 20)

    # DuckDuckGo Instant Answer API — free, no key, JSON output
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
    )
    url = f"https://api.duckduckgo.com/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError) as exc:
        return f"[error] Search failed: {exc}"

    lines: list[str] = []

    # Instant answer (if any)
    if data.get("AbstractText"):
        lines.append(f"Summary: {data['AbstractText']}")
        if data.get("AbstractURL"):
            lines.append(f"Source: {data['AbstractURL']}")
        lines.append("")

    # Related topics
    topics = data.get("RelatedTopics", [])
    count = 0
    for item in topics:
        if count >= max_results:
            break
        if "Text" in item and "FirstURL" in item:
            lines.append(f"• {item['Text']}")
            lines.append(f"  {item['FirstURL']}")
            count += 1
        # nested topics
        for sub in item.get("Topics", []):
            if count >= max_results:
                break
            if "Text" in sub and "FirstURL" in sub:
                lines.append(f"• {sub['Text']}")
                lines.append(f"  {sub['FirstURL']}")
                count += 1

    if not lines:
        return f"No results found for: {query!r}"
    return "\n".join(lines)


def web_fetch(args: dict[str, Any]) -> str:
    url: str = args["url"]
    req = urllib.request.Request(url, headers={"User-Agent": _UA})

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            content_type: str = resp.headers.get("Content-Type", "")
            raw: bytes = resp.read(_FETCH_LIMIT)
    except (urllib.error.URLError, OSError) as exc:
        return f"[error] Fetch failed: {exc}"
    except urllib.error.HTTPError as exc:
        return f"[error] HTTP {exc.code}: {url}"

    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].strip().split(";")[0].strip()

    text = raw.decode(charset, errors="replace")

    if "html" in content_type.lower():
        text = _strip_html(text)

    truncated = len(raw) >= _FETCH_LIMIT
    result = text.strip()
    if truncated:
        result += f"\n[truncated at {_FETCH_LIMIT} bytes]"
    return result or "(empty page)"


# ── HTML stripper ─────────────────────────────────────────────────────────────


class _HTMLStripper(html.parser.HTMLParser):
    _SKIP_TAGS = {"script", "style", "head", "nav", "footer", "aside"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        # collapse whitespace
        import re

        return re.sub(r"\s+", " ", raw).strip()


def _strip_html(text: str) -> str:
    stripper = _HTMLStripper()
    try:
        stripper.feed(text)
    except Exception:  # noqa: BLE001
        return text
    return html.unescape(stripper.get_text())
