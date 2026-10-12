from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langgraph.types import Command

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)


def reflector_node(state: GraphState) -> Command:  # type: ignore[type-arg]
    """Inspect plan state and decide next step — no LLM call unless inconclusive.

    Decision table
    --------------
    all steps done          → synthesizer
    any failed, under limit → supervisor (retry from current failed step)
    any failed, over limit  → synthesizer (partial results)
    steps still pending     → supervisor (continue execution)
    empty plan / error      → synthesizer
    """
    from api.settings import settings

    steps: list[dict[str, Any]] = list(state.get("plan", []))
    iterations: int = state.get("iterations", 0)
    max_iter: int = (
        state.get("hitl_config", {}).get("max_iterations", settings.max_iterations)
        if state.get("hitl_config")
        else settings.max_iterations
    )  # type: ignore[union-attr]

    if not steps:
        logger.debug("Reflector: empty plan → synthesizer")
        return Command(goto="synthesizer")

    statuses = [s.get("status") for s in steps]
    all_done = all(st == "done" for st in statuses)
    has_failed = any(st == "failed" for st in statuses)

    if all_done:
        logger.debug("Reflector: all steps done → synthesizer")
        return Command(goto="synthesizer")

    if has_failed:
        if iterations < max_iter:
            # Reset failed steps to pending and increment iteration counter
            recovered = [
                {**s, "status": "pending"} if s.get("status") == "failed" else s for s in steps
            ]
            logger.debug(
                "Reflector: failed steps found, iteration %d/%d → supervisor (retry)",
                iterations + 1,
                max_iter,
            )
            return Command(
                goto="supervisor",
                update={"plan": recovered, "iterations": iterations + 1},
            )
        else:
            logger.debug(
                "Reflector: iterations exceeded (%d/%d) → synthesizer (partial)",
                iterations,
                max_iter,
            )
            return Command(goto="synthesizer")

    # Steps still pending/running — continue
    logger.debug("Reflector: pending steps remain → supervisor")
    return Command(goto="supervisor")
