from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.types import interrupt

from api.llm import get_llm

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

_SYNTHESIZE_SYSTEM = """\
You are a helpful assistant summarising the results of a multi-step reasoning pipeline.

Using ONLY the observations and artifact URLs provided, write a clear, complete answer
to the user's original request. Include inline references where applicable.
If there are image or video artifacts, reference them by their URLs.
Be concise but thorough. Do not hallucinate — only use what the observations contain.
"""


async def synthesizer_node(state: GraphState) -> dict[str, Any]:
    """LLM node — combines all observations + artifacts into a final answer.

    If ``hitl_config.review_output`` is True, pauses via HITL #3 (interrupt)
    before streaming the answer. The user can accept or request a revision.

    Resume payload
    --------------
    ``{"action": "accept"}``                      → stream as-is
    ``{"action": "revise", "instructions": ""}``  → re-run synthesizer with extra context
    """
    messages = list(state.get("messages", []))
    observations: list[str] = state.get("observations") or []
    artifacts: list[dict[str, Any]] = state.get("artifacts") or []
    hitl_cfg: dict[str, Any] = state.get("hitl_config") or {}

    # Build synthesis prompt
    user_goal = _extract_user_goal(messages)
    obs_block = "\n".join(f"- {o}" for o in observations) if observations else "(none)"
    art_block = (
        "\n".join(f"- [{a.get('artifact_type', 'file')}] {a.get('url', '')}" for a in artifacts)
        if artifacts
        else "(none)"
    )

    synthesis_messages = [
        SystemMessage(content=_SYNTHESIZE_SYSTEM),
        {
            "role": "user",
            "content": (
                f"Original request: {user_goal}\n\n"
                f"Observations:\n{obs_block}\n\n"
                f"Artifacts:\n{art_block}"
            ),
        },
    ]

    llm = get_llm("fast")
    try:
        response = await llm.ainvoke(synthesis_messages)
        answer: str = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.warning("Synthesizer LLM failed: %s", exc)
        answer = f"Task completed. Observations:\n{obs_block}"

    # HITL #3 — optional output review
    if hitl_cfg.get("review_output"):
        resume: dict[str, Any] = interrupt({"subject": "output", "data": {"answer": answer}})
        action = resume.get("action", "accept")
        logger.debug("HITL output resume: action=%s", action)

        if action == "revise":
            instructions: str = resume.get("instructions", "")
            synthesis_messages.append({"role": "assistant", "content": answer})
            synthesis_messages.append({"role": "user", "content": f"Please revise: {instructions}"})
            try:
                revised = await llm.ainvoke(synthesis_messages)
                answer = revised.content if hasattr(revised, "content") else str(revised)
            except Exception as exc:
                logger.warning("Synthesizer revision failed: %s", exc)

    final_message = AIMessage(content=answer)
    return {"messages": [final_message]}


def _extract_user_goal(messages: list[Any]) -> str:
    """Return the last HumanMessage content as the user goal."""
    from langchain_core.messages import HumanMessage

    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return "(no user message)"
