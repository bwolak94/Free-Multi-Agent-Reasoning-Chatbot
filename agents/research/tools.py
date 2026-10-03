from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import trafilatura

from agents.research.models import FetchedPage, SearchResult
from api.settings import settings

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}


async def web_search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Search via SearXNG; fall back to Tavily on failure."""
    n = max_results or settings.research_max_results
    results = await _searxng_search(query, n)
    if not results and settings.tavily_api_key:
        logger.info("SearXNG unavailable, falling back to Tavily for query=%r", query)
        results = await _tavily_search(query, n)
    return results


async def _searxng_search(query: str, n: int) -> list[SearchResult]:
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing,duckduckgo",
        "language": "en",
        "safesearch": "0",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.research_fetch_timeout) as client:
            resp = await client.get(
                f"{settings.searxng_url}/search", params=params, headers=_HEADERS
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("SearXNG search failed: %s", exc)
        return []

    return [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            snippet=r.get("content", ""),
            score=float(r.get("score", 0)),
        )
        for r in data.get("results", [])[:n]
        if r.get("url")
    ]


async def _tavily_search(query: str, n: int) -> list[SearchResult]:
    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": n,
        "search_depth": "basic",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.research_fetch_timeout) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []

    return [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            snippet=r.get("content", ""),
            score=float(r.get("score", 0)),
        )
        for r in data.get("results", [])[:n]
        if r.get("url")
    ]


async def web_fetch(url: str) -> FetchedPage:
    """Fetch a page via Jina Reader; fall back to direct httpx fetch."""
    jina_url = f"{settings.jina_reader_url}/{url}"
    try:
        async with httpx.AsyncClient(timeout=settings.research_fetch_timeout) as client:
            resp = await client.get(jina_url, headers=_HEADERS)
            resp.raise_for_status()
            return FetchedPage(url=url, title=url, content=resp.text[:8000])
    except Exception:
        pass

    # Direct fetch + trafilatura extraction
    try:
        async with httpx.AsyncClient(timeout=settings.research_fetch_timeout) as client:
            resp = await client.get(url, headers=_HEADERS, follow_redirects=True)
            resp.raise_for_status()
        text = trafilatura.extract(resp.text) or resp.text[:4000]
        return FetchedPage(url=url, title=url, content=text[:8000])
    except Exception as exc:
        logger.warning("web_fetch failed for %s: %s", url, exc)
        return FetchedPage(url=url, title=url, content="", fetch_ok=False)


async def fetch_pages_parallel(urls: list[str]) -> list[FetchedPage]:
    """Fetch multiple pages in parallel, respecting per-page timeout."""
    tasks = [web_fetch(url) for url in urls]
    pages: list[FetchedPage] = await asyncio.gather(*tasks, return_exceptions=False)
    return pages
