from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from api.llm import get_llm

logger = logging.getLogger(__name__)

AgentType = Literal["research", "image", "video", "tool"]
StepStatus = Literal["pending", "running", "done", "error"]

_PLANNER_SYSTEM_PROMPT = """\
You are a planning agent. Given the user's request, produce a structured plan \
with 1-8 steps that will be executed by specialised sub-agents.

Available agents:
- research: web search, page extraction, cited synthesis
- image: prompt refinement and image generation
- video: script refinement and async video generation
- tool: general-purpose tool / MCP tool execution

Rules:
- Each step must have a clear, single goal.
- deps lists 0-based indices of steps that must complete before this step.
- Prefer fewer steps. Only add a step when it produces a distinct artifact or \
observation.
- Always cite sources for factual claims (global rule).
"""


class Step(BaseModel):
    """A single executable step in the plan."""

    agent: AgentType = Field(description="Which sub-agent executes this step.")
    goal: str = Field(description="What this step must accomplish.")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Key/value inputs passed to the agent.",
    )
    deps: list[int] = Field(
        default_factory=list,
        description="0-based indices of steps this step depends on.",
    )
    status: StepStatus = Field(default="pending")


class Plan(BaseModel):
    """Ordered list of steps that fulfil the user's goal."""

    goal: str = Field(description="Restatement of the user's overall goal.")
    steps: list[Step] = Field(
        description="Ordered execution steps (1-8).",
        min_length=1,
        max_length=8,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlannerError(Exception):
    """Raised when the planner fails to produce a valid plan after all retries."""


async def run_planner(user_message: str, max_retries: int = 3) -> Plan:
    """Call the planner LLM and return a validated Plan.

    Retries up to *max_retries* times on structured-output failures.

    Raises:
        PlannerError: when all retries are exhausted.
    """
    llm = get_llm("planner")
    structured = llm.with_structured_output(Plan)

    messages = [
        SystemMessage(content=_PLANNER_SYSTEM_PROMPT),
        {"role": "user", "content": user_message},
    ]

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            plan: Plan = await structured.ainvoke(messages)
            logger.debug(
                "Planner produced plan with %d steps (attempt %d)", len(plan.steps), attempt
            )
            return plan
        except Exception as exc:
            last_exc = exc
            logger.warning("Planner attempt %d/%d failed: %s", attempt, max_retries, exc)

    raise PlannerError(f"Planner failed after {max_retries} attempts: {last_exc}") from last_exc
