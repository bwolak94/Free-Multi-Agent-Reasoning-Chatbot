from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    index: int
    url: str
    title: str
    snippet: str


class ResearchOutput(BaseModel):
    """Final output of the Research Agent."""

    answer: str = Field(description="Synthesized answer with inline citation markers.")
    citations: list[Citation] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, description="All fetched source URLs.")


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    score: float = 0.0


class FetchedPage(BaseModel):
    url: str
    title: str
    content: str
    fetch_ok: bool = True
