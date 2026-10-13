from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class StepEvent(BaseModel):
    type: Literal["step"] = "step"
    node: str
    status: Literal["started", "done", "error"]
    step_index: int | None = None


class InterruptEvent(BaseModel):
    type: Literal["interrupt"] = "interrupt"
    subject: Literal["plan", "tool"]
    data: dict[str, Any]


class ArtifactEvent(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact_id: str
    url: str
    artifact_type: str


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    job_id: str
    percent: int
    message: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    thread_id: str
    run_id: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


# ---------------------------------------------------------------------------
# Prompt library schemas
# ---------------------------------------------------------------------------


class PromptCreate(BaseModel):
    title: str
    content: str
    description: str | None = None
    tags: list[str] = []


class PromptUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class PromptResponse(BaseModel):
    id: str
    user_id: str
    title: str
    content: str
    description: str | None
    tags: list[str]
    use_count: int
    created_at: str
    updated_at: str
