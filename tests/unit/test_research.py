from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.research.models import Citation, FetchedPage, ResearchOutput, SearchResult
from agents.research.nodes import (
    build_research_output,
    fetch_pages_node,
    rank_sources_node,
    refine_query_node,
    run_research_agent,
    synthesize_node,
    verify_node,
    web_search_node,
)
from agents.research.tools import web_fetch, web_search

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_research_output_model() -> None:
    out = ResearchOutput(
        answer="Test answer [1]",
        citations=[Citation(index=1, url="https://example.com", title="Example", snippet="snip")],
        sources=["https://example.com"],
    )
    assert out.answer == "Test answer [1]"
    assert len(out.citations) == 1
    assert out.citations[0].index == 1


@pytest.mark.unit
def test_search_result_model() -> None:
    r = SearchResult(url="https://example.com", title="Title", snippet="Snippet", score=0.9)
    assert r.score == 0.9


@pytest.mark.unit
def test_fetched_page_default_ok() -> None:
    p = FetchedPage(url="https://x.com", title="X", content="content")
    assert p.fetch_ok is True


# ---------------------------------------------------------------------------
# Tool tests (mocked HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_web_search_searxng_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"url": "https://a.com", "title": "A", "content": "desc A", "score": 0.9},
            {"url": "https://b.com", "title": "B", "content": "desc B", "score": 0.7},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client):
        results = await web_search("LangGraph", max_results=5)

    assert len(results) == 2
    assert results[0].url == "https://a.com"


@pytest.mark.unit
async def test_web_search_fallback_to_tavily() -> None:
    tavily_resp = MagicMock()
    tavily_resp.raise_for_status = MagicMock()
    tavily_resp.json.return_value = {
        "results": [{"url": "https://tavily.com/r", "title": "T", "content": "tc", "score": 0.5}]
    }

    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("SearXNG down"))
    mock_client.post = AsyncMock(return_value=tavily_resp)

    with (
        patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client),
        patch("agents.research.tools.settings") as mock_settings,
    ):
        mock_settings.research_max_results = 5
        mock_settings.research_fetch_timeout = 5
        mock_settings.searxng_url = "http://localhost:8080"
        mock_settings.tavily_api_key = "fake-key"
        results = await web_search("test")

    assert any(r.url == "https://tavily.com/r" for r in results)


@pytest.mark.unit
async def test_web_search_no_fallback_when_no_tavily_key() -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    import httpx

    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

    with (
        patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client),
        patch("agents.research.tools.settings") as mock_settings,
    ):
        mock_settings.research_max_results = 5
        mock_settings.research_fetch_timeout = 5
        mock_settings.searxng_url = "http://localhost:8080"
        mock_settings.tavily_api_key = ""
        results = await web_search("test")

    assert results == []


@pytest.mark.unit
async def test_web_fetch_jina_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = "Page content from Jina"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client):
        page = await web_fetch("https://example.com")

    assert page.fetch_ok is True
    assert "Jina" in page.content or "content" in page.content.lower()


@pytest.mark.unit
async def test_web_fetch_jina_fails_falls_back_to_direct() -> None:
    import httpx

    direct_resp = MagicMock()
    direct_resp.raise_for_status = MagicMock()
    direct_resp.text = "<html><body>Direct content</body></html>"

    call_count = 0

    async def mock_get(*_a: object, **_kw: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Jina down")
        return direct_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=mock_get)

    with (
        patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client),
        patch("agents.research.tools.trafilatura.extract", return_value="Direct content"),
    ):
        page = await web_fetch("https://example.com")

    assert page.fetch_ok is True


@pytest.mark.unit
async def test_web_fetch_both_fail_returns_empty() -> None:
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("all down"))

    with patch("agents.research.tools.httpx.AsyncClient", return_value=mock_client):
        page = await web_fetch("https://example.com")

    assert page.fetch_ok is False
    assert page.content == ""


# ---------------------------------------------------------------------------
# Node pipeline tests (mocked LLM + tools)
# ---------------------------------------------------------------------------


def _mock_llm_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = text
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    return llm


@pytest.mark.unit
async def test_refine_query_node_parses_json() -> None:
    with patch(
        "agents.research.nodes.get_llm", return_value=_mock_llm_response('["query A", "query B"]')
    ):
        result = await refine_query_node({"goal": "research LangGraph"})
    assert result["queries"] == ["query A", "query B"]


@pytest.mark.unit
async def test_refine_query_node_fallback_on_bad_json() -> None:
    with patch("agents.research.nodes.get_llm", return_value=_mock_llm_response("not json")):
        result = await refine_query_node({"goal": "my goal"})
    assert result["queries"] == ["my goal"]


@pytest.mark.unit
async def test_web_search_node_merges_queries() -> None:
    state = {"queries": ["q1", "q2"], "goal": "test"}
    results_q1 = [SearchResult(url="https://a.com", title="A", snippet="a")]
    results_q2 = [SearchResult(url="https://b.com", title="B", snippet="b")]

    with patch("agents.research.nodes.web_search", side_effect=[results_q1, results_q2]):
        result = await web_search_node(state)

    assert len(result["search_results"]) == 2
    urls = {r["url"] for r in result["search_results"]}
    assert urls == {"https://a.com", "https://b.com"}


@pytest.mark.unit
async def test_web_search_node_deduplicates() -> None:
    state = {"queries": ["q1", "q2"], "goal": "test"}
    dup = SearchResult(url="https://a.com", title="A", snippet="a")

    with patch("agents.research.nodes.web_search", side_effect=[[dup], [dup]]):
        result = await web_search_node(state)

    assert len(result["search_results"]) == 1


@pytest.mark.unit
async def test_fetch_pages_node() -> None:
    state = {
        "search_results": [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://b.com", "title": "B"},
        ]
    }
    pages = [
        FetchedPage(url="https://a.com", title="A", content="content A"),
        FetchedPage(url="https://b.com", title="B", content="content B"),
    ]
    with patch("agents.research.nodes.fetch_pages_parallel", AsyncMock(return_value=pages)):
        result = await fetch_pages_node(state)

    assert len(result["fetched_pages"]) == 2


@pytest.mark.unit
def test_rank_sources_filters_empty_content() -> None:
    state = {
        "search_results": [
            {"url": "https://a.com", "score": 0.9},
            {"url": "https://b.com", "score": 0.5},
        ],
        "fetched_pages": [
            {"url": "https://a.com", "content": "x" * 200, "fetch_ok": True},
            {"url": "https://b.com", "content": "", "fetch_ok": False},
        ],
    }
    result = rank_sources_node(state)
    assert len(result["ranked_sources"]) == 1
    assert result["ranked_sources"][0]["url"] == "https://a.com"


@pytest.mark.unit
async def test_synthesize_node_produces_answer() -> None:
    state = {
        "goal": "What is LangGraph?",
        "ranked_sources": [
            {"url": "https://a.com", "title": "A", "content": "LangGraph is a framework. " * 20}
        ],
    }
    with patch(
        "agents.research.nodes.get_llm",
        return_value=_mock_llm_response("LangGraph is a framework [1]."),
    ):
        result = await synthesize_node(state)

    assert "LangGraph" in result["answer"]
    assert len(result["citations"]) == 1


@pytest.mark.unit
async def test_verify_node_skips_when_no_sources() -> None:
    # Should not raise and return {}
    result = await verify_node({"answer": "something", "ranked_sources": []})
    assert result == {}


@pytest.mark.unit
async def test_build_research_output() -> None:
    state = {
        "answer": "Answer [1]",
        "citations": [{"index": 1, "url": "https://a.com", "title": "A", "snippet": "snip"}],
        "ranked_sources": [{"url": "https://a.com"}],
    }
    output = build_research_output(state)
    assert output.answer == "Answer [1]"
    assert len(output.citations) == 1
    assert "https://a.com" in output.sources


@pytest.mark.unit
async def test_run_research_agent_end_to_end() -> None:
    """Full pipeline with all external calls mocked."""
    search_results = [SearchResult(url="https://a.com", title="A", snippet="snip")]
    fetched = [FetchedPage(url="https://a.com", title="A", content="LangGraph content " * 30)]

    with (
        patch("agents.research.nodes.get_llm") as mock_get_llm,
        patch("agents.research.nodes.web_search", AsyncMock(return_value=search_results)),
        patch("agents.research.nodes.fetch_pages_parallel", AsyncMock(return_value=fetched)),
    ):
        mock_get_llm.return_value = _mock_llm_response('["query1"]\nAnswer with citation [1].')
        output, observation = await run_research_agent("What is LangGraph?")

    assert isinstance(output, ResearchOutput)
    assert len(observation) > 0
