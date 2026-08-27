"""Scout's web_search tool — Fase 2.

Tavily over a raw search-engine scrape because it's built for exactly
this (LLM-agent-facing, returns clean snippets instead of HTML to
parse) and has a usable free tier. Swapping providers later is a
one-file change since nothing outside this module imports `tavily`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.tools.errors import ToolNotConfiguredError


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _require_key() -> str:
    key = get_settings().tavily_api_key
    if not key:
        raise ToolNotConfiguredError(
            "No TAVILY_API_KEY configured — Scout's web_search tool is inert until "
            "Fase 2 budget lands. See README."
        )
    return key


async def web_search(query: str, *, max_results: int = 5) -> list[SearchResult]:
    api_key = _require_key()

    # Imported lazily so the tavily-python package is only required once a
    # key actually exists to use it — mirrors the rest of this codebase's
    # "no dependency does anything until it's configured" pattern.
    from tavily import AsyncTavilyClient

    client = AsyncTavilyClient(api_key=api_key)
    response = await client.search(query, max_results=max_results)
    return [
        SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", ""))
        for r in response.get("results", [])
    ]
