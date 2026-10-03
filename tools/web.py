from __future__ import annotations

from typing import Any

from agents.research.tools import web_fetch as _web_fetch
from agents.research.tools import web_search as _web_search
from tools.base import tool


@tool(
    "web.search",
    description="Search the web via SearXNG (Tavily fallback)",
    risk="low",
    tags=["search"],
)
async def web_search_tool(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search the web and return a list of result dicts (url, title, snippet, score)."""
    results = await _web_search(query, max_results=max_results)
    return [r.model_dump() for r in results]


@tool(
    "web.fetch", description="Fetch and extract text content from a URL", risk="low", tags=["fetch"]
)
async def web_fetch_tool(url: str) -> dict[str, Any]:
    """Fetch a web page and return extracted text content."""
    page = await _web_fetch(url)
    return page.model_dump()
