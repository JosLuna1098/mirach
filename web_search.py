#!/usr/bin/env python3
"""DuckDuckGo web search — invoked by OpenCode via bash.

Usage: python3 web_search.py "search query"

Region and result count are configurable via env vars:
  - MIRACH_SEARCH_REGION (default: wt-wt)
  - MIRACH_SEARCH_MAX_RESULTS (default: 5)
"""
import os
import sys

from ddgs import DDGS

REGION = os.environ.get("MIRACH_SEARCH_REGION", "wt-wt")
MAX_RESULTS = int(os.environ.get("MIRACH_SEARCH_MAX_RESULTS", "5"))

if len(sys.argv) < 2:
    print("Usage: web_search.py 'query'", file=sys.stderr)
    sys.exit(1)

query = " ".join(sys.argv[1:])[:200]
try:
    with DDGS() as d:
        results = list(d.text(query, region=REGION, max_results=MAX_RESULTS))
except Exception as e:
    print(f"Search error: {e}", file=sys.stderr)
    sys.exit(1)

if not results:
    print("No results found.")
    sys.exit(0)

for r in results:
    print(f"- {r.get('title', '')}: {r.get('body', '')}")
