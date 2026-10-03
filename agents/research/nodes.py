from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage

from agents.research.models import Citation, ResearchOutput, SearchResult
from agents.research.tools import fetch_pages_parallel, web_search
from api.llm import get_llm
from api.settings import settings

logger = logging.getLogger(__name__)

_REFINE_PROMPT = """\
You are a search query specialist. Given the research goal below, produce 1-3
concise, distinct web search queries that together cover the topic.
Return ONLY the queries as a JSON array of strings, e.g. ["query1", "query2"].
Always cite sources for factual claims.
"""

_SYNTHESIZE_PROMPT = """\
You are a research analyst. Using ONLY the sources provided, write a clear,
accurate answer to the research goal. Insert inline citation markers like [1],
[2] etc. that reference the numbered source list.
Always cite sources for factual claims.
"""

_VERIFY_PROMPT = """\
You are a fact-checker. Review the answer below and flag any claim that is not
supported by the provided sources. If everything is consistent, respond with
"VERIFIED". Otherwise list the unsupported claims.
"""


async def refine_query_node(state: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the step goal into 1-3 targeted search queries."""
    goal: str = state.get("goal", "")
    llm = get_llm("fast")

    messages = [
        SystemMessage(content=_REFINE_PROMPT),
        {"role": "user", "content": f"Research goal: {goal}"},
    ]
    try:
        response = await llm.ainvoke(messages)
        raw: str = response.content if hasattr(response, "content") else str(response)

        import json

        start, end = raw.find("["), raw.rfind("]") + 1
        queries: list[str] = json.loads(raw[start:end]) if start >= 0 else [goal]
    except Exception as exc:
        logger.warning("Query refinement failed: %s — using raw goal", exc)
        queries = [goal]

    return {"queries": queries[:3]}


async def web_search_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run all refined queries through web_search and merge results."""
    queries: list[str] = state.get("queries", [state.get("goal", "")])
    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []

    for query in queries:
        results = await web_search(query, max_results=settings.research_max_results)
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)

    return {"search_results": [r.model_dump() for r in all_results]}


async def fetch_pages_node(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch top N search result pages in parallel."""
    results: list[dict[str, Any]] = state.get("search_results", [])
    top_urls = [r["url"] for r in results[: settings.research_max_results] if r.get("url")]

    pages = await fetch_pages_parallel(top_urls)
    return {"fetched_pages": [p.model_dump() for p in pages]}


def rank_sources_node(state: dict[str, Any]) -> dict[str, Any]:
    """Score and deduplicate fetched pages; keep those with useful content."""
    search_results: list[dict[str, Any]] = state.get("search_results", [])
    fetched: list[dict[str, Any]] = state.get("fetched_pages", [])

    score_map = {r["url"]: r.get("score", 0.0) for r in search_results}

    ranked = sorted(
        [p for p in fetched if p.get("fetch_ok") and len(p.get("content", "")) > 100],
        key=lambda p: score_map.get(p["url"], 0.0),
        reverse=True,
    )
    return {"ranked_sources": ranked[: settings.research_max_results]}


async def synthesize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Produce a cited answer from the ranked sources."""
    goal: str = state.get("goal", "")
    sources: list[dict[str, Any]] = state.get("ranked_sources", [])

    source_block = "\n\n".join(
        f"[{i + 1}] {s['url']}\n{s['content'][:1000]}" for i, s in enumerate(sources)
    )

    messages = [
        SystemMessage(content=_SYNTHESIZE_PROMPT),
        {
            "role": "user",
            "content": f"Goal: {goal}\n\nSources:\n{source_block}",
        },
    ]
    llm = get_llm("fast")
    try:
        response = await llm.ainvoke(messages)
        answer: str = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("Synthesize failed: %s", exc)
        answer = f"Could not synthesize answer: {exc}"

    citations = [
        Citation(
            index=i + 1, url=s["url"], title=s.get("title", s["url"]), snippet=s["content"][:200]
        )
        for i, s in enumerate(sources)
    ]
    return {"answer": answer, "citations": [c.model_dump() for c in citations]}


async def verify_node(state: dict[str, Any]) -> dict[str, Any]:
    """Optional fact-check pass — skipped if no sources or disabled."""
    answer: str = state.get("answer", "")
    sources: list[dict[str, Any]] = state.get("ranked_sources", [])
    if not sources or not answer:
        return {}

    source_block = "\n\n".join(f"[{i + 1}] {s['content'][:500]}" for i, s in enumerate(sources))
    messages = [
        SystemMessage(content=_VERIFY_PROMPT),
        {"role": "user", "content": f"Answer:\n{answer}\n\nSources:\n{source_block}"},
    ]
    llm = get_llm("fast")
    try:
        response = await llm.ainvoke(messages)
        verdict: str = response.content if hasattr(response, "content") else str(response)
        logger.debug("Verify verdict: %s", verdict[:200])
    except Exception as exc:
        logger.warning("Verify node failed: %s", exc)

    return {}


def build_research_output(state: dict[str, Any]) -> ResearchOutput:
    """Assemble final ResearchOutput from subgraph state."""
    citations = [Citation(**c) for c in state.get("citations", [])]
    sources = [s["url"] for s in state.get("ranked_sources", [])]
    return ResearchOutput(
        answer=state.get("answer", ""),
        citations=citations,
        sources=sources,
    )


def _build_observation(output: ResearchOutput) -> str:
    cit_lines = "\n".join(f"  [{c.index}] {c.url} — {c.snippet[:120]}" for c in output.citations)
    return f"Research answer:\n{output.answer}\n\nCitations:\n{cit_lines}"


async def run_research_agent(goal: str) -> tuple[ResearchOutput, str]:
    """Run the full research pipeline and return (output, observation)."""
    state: dict[str, Any] = {"goal": goal}
    state.update(await refine_query_node(state))
    state.update(await web_search_node(state))
    state.update(await fetch_pages_node(state))
    state.update(rank_sources_node(state))
    state.update(await synthesize_node(state))
    await verify_node(state)

    output = build_research_output(state)
    observation = _build_observation(output)
    return output, observation
