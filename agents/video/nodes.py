from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from api.llm import get_llm
from api.settings import settings
from api.worker_client import get_arq_pool

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

_VIDEO_JOB_TIMEOUT = 600  # 10 minutes

_REFINE_SYSTEM = (
    "You are a video director. Given a user goal, write a concise, vivid video generation "
    "prompt — no longer than 2 sentences. Focus on visual details, camera movement, and mood. "
    "Target duration: 10 seconds max. Output ONLY the refined prompt, no explanation."
)


async def _refine_video_script(goal: str) -> str:
    """Use the fast LLM to turn a raw goal into a video generation prompt."""
    llm = get_llm("fast")
    messages = [
        SystemMessage(content=_REFINE_SYSTEM),
        HumanMessage(content=f"Goal: {goal}\n\nRefined prompt:"),
    ]
    try:
        response = await llm.ainvoke(messages)
        return str(response.content).strip()
    except Exception as exc:
        logger.warning("Video script refinement failed, using raw goal: %s", exc)
        return goal


async def run_video_agent(state: GraphState) -> Any:
    """LangGraph node — full video-agent pipeline with HITL #2.

    Flow
    ----
    1. Refine the step goal into a video generation prompt.
    2. Optionally generate a keyframe image (if step inputs request it).
    3. Interrupt (HITL #2) — always required before video generation.
    4. After approval: enqueue VideoGenerationJob via arq.
    5. Await job result and return Command(goto="supervisor").
    """
    from langgraph.types import Command

    idx = state.get("current_step", 0)
    steps = list(state.get("plan", []))
    step = steps[idx] if 0 <= idx < len(steps) else {}
    goal: str = step.get("goal", "")
    inputs: dict[str, Any] = dict(step.get("inputs", {}))

    duration_s: int = min(int(inputs.get("duration_s", 10)), 10)
    want_keyframe: bool = bool(inputs.get("keyframe", False))

    observations = list(state.get("observations") or [])
    artifacts = list(state.get("artifacts") or [])

    # Step 1: Refine script
    refined_prompt = await _refine_video_script(goal)
    logger.debug("Video agent: refined_prompt=%r duration_s=%d", refined_prompt, duration_s)

    # Step 2: Optional keyframe via Image Agent
    keyframe_url: str | None = None
    if want_keyframe:
        keyframe_url = await _generate_keyframe(refined_prompt, observations, artifacts)

    # Step 3: HITL #2 — always required for video generation
    resume: dict[str, Any] = interrupt(
        {
            "subject": "tool",
            "data": {
                "tool_name": "_video_job",
                "args": {
                    "prompt": refined_prompt,
                    "duration_s": duration_s,
                    "keyframe_url": keyframe_url,
                },
            },
        }
    )

    action = resume.get("action", "approve")
    logger.debug("Video HITL resume: action=%s", action)

    if action == "reject":
        reason = resume.get("reason", "Video generation rejected by user")
        observations.append(f"[REJECTED] {reason}")
        if 0 <= idx < len(steps):
            steps[idx] = {**steps[idx], "status": "done"}
        return Command(
            goto="supervisor",
            update={"plan": steps, "observations": observations, "artifacts": artifacts},
        )

    if action == "edit":
        edited_args: dict[str, Any] = resume.get("tool_args", {})
        refined_prompt = edited_args.get("prompt", refined_prompt)
        duration_s = min(int(edited_args.get("duration_s", duration_s)), 10)
        keyframe_url = edited_args.get("keyframe_url", keyframe_url)

    # Step 4: Enqueue arq job
    job_id = str(uuid.uuid4())
    try:
        pool = await get_arq_pool()
        arq_job = await pool.enqueue_job(
            "run_video_job",
            job_id=job_id,
            prompt=refined_prompt,
            duration_s=duration_s,
            keyframe_url=keyframe_url,
        )
    except Exception as exc:
        observations.append(f"Video generation failed: could not enqueue job — {exc}")
        arq_job = None

    # Step 5: Await result
    if arq_job is not None:
        try:
            result_dict: dict[str, Any] = await arq_job.result(timeout=_VIDEO_JOB_TIMEOUT)
            artifacts.append(result_dict)
            observations.append(f"Video generated: {result_dict.get('url', '')}")
        except Exception as exc:
            observations.append(f"Video generation failed: {exc}")

    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done"}

    return Command(
        goto="supervisor",
        update={"plan": steps, "artifacts": artifacts, "observations": observations},
    )


async def _generate_keyframe(
    prompt: str,
    observations: list[str],
    artifacts: list[dict[str, Any]],
) -> str | None:
    """Call Image Agent to generate a keyframe; return artifact URL or None."""
    from agents.image.backends import PollinationsBackend

    try:
        backend = PollinationsBackend()
        image_bytes = await backend.generate(
            prompt, settings.image_default_width, settings.image_default_height
        )
        import uuid as _uuid
        from pathlib import Path

        artifact_id = str(_uuid.uuid4())
        path = Path(settings.artifacts_local_path) / f"{artifact_id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        url = f"/artifacts/{artifact_id}"
        artifacts.append({"artifact_id": artifact_id, "url": url, "artifact_type": "image"})
        observations.append(f"Keyframe generated: {url}")
        logger.debug("Keyframe generated: %s", url)
        return url
    except Exception as exc:
        logger.warning("Keyframe generation failed (continuing without): %s", exc)
        return None
