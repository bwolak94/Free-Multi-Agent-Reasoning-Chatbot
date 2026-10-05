from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage

from api.llm import get_llm
from api.settings import settings
from api.worker_client import get_arq_pool

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

_REFINE_SYSTEM = (
    "You are a prompt engineer specialising in text-to-image generation. "
    "Given a user goal, output ONLY an enhanced image generation prompt — no explanation. "
    "Add style, lighting, and composition details. Default aspect ratio: 16:9 (1280x720)."
)


async def refine_image_prompt(goal: str) -> str:
    """Use the fast LLM to enhance a raw goal into a detailed image prompt."""
    llm = get_llm("fast")
    messages = [
        SystemMessage(content=_REFINE_SYSTEM),
        HumanMessage(content=f"Goal: {goal}\n\nEnhanced prompt:"),
    ]
    response = await llm.ainvoke(messages)
    return str(response.content).strip()


async def run_image_agent(state: GraphState) -> Any:
    """LangGraph node — full image-agent pipeline.

    Steps
    -----
    1. Refine the step goal into a detailed image prompt.
    2. Enqueue an ``ImageGenerationJob`` via arq.
    3. Await the arq job result (polls Redis; timeout from settings).
    4. Return Command(goto="supervisor") with updated state.
    """
    from langgraph.types import Command

    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))
    step = steps[idx] if 0 <= idx < len(steps) else {}
    goal: str = step.get("goal", "")
    inputs: dict[str, Any] = dict(step.get("inputs", {}))

    width = int(inputs.get("width", settings.image_default_width))
    height = int(inputs.get("height", settings.image_default_height))

    observations = list(state.get("observations") or [])
    artifacts = list(state.get("artifacts") or [])

    # Step 1: Refine prompt
    try:
        refined = await refine_image_prompt(goal)
    except Exception as exc:
        logger.warning("Prompt refinement failed, using raw goal: %s", exc)
        refined = goal

    # Step 2: Enqueue job
    job_id = str(uuid.uuid4())
    try:
        pool = await get_arq_pool()
        arq_job = await pool.enqueue_job(
            "run_image_job", job_id=job_id, prompt=refined, width=width, height=height
        )
    except Exception as exc:
        observations.append(f"Image generation failed: could not enqueue job — {exc}")
        arq_job = None

    # Step 3: Await result
    if arq_job is not None:
        try:
            result_dict: dict[str, Any] = await arq_job.result(
                timeout=settings.hf_inference_timeout + 30
            )
            artifacts.append(result_dict)
            observations.append(f"Image generated: {result_dict.get('url', '')}")
        except Exception as exc:
            observations.append(f"Image generation failed: {exc}")

    # Step 4: Mark step done
    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done"}

    return Command(
        goto="supervisor",
        update={"plan": steps, "artifacts": artifacts, "observations": observations},
    )
