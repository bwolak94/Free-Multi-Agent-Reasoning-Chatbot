from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

if TYPE_CHECKING:
    from agents.graph import GraphState

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent.parent / "rules" / "default.yaml"

PolicyAction = Literal["allow", "deny", "require_approval"]


@dataclass
class PromptRule:
    scope: str
    text: str


@dataclass
class PolicyCondition:
    tool: str | None = None
    arg: str | None = None
    matches: str | None = None
    plan_steps_gt: int | None = None


@dataclass
class PolicyRule:
    id: str
    when: PolicyCondition
    action: Literal["require_approval", "deny"]


@dataclass
class PolicyResult:
    action: PolicyAction
    rule_id: str | None = None
    reason: str | None = None


class PolicyEngine:
    """Loads YAML rule files and evaluates prompt/policy rules deterministically."""

    def __init__(self, rules_path: Path = _RULES_PATH) -> None:
        self._rules_path = rules_path
        self._prompt_rules: list[PromptRule] = []
        self._policy_rules: list[PolicyRule] = []

    def load(self) -> None:
        """Read rules from YAML. Missing file → warning only, no error."""
        try:
            raw = yaml.safe_load(self._rules_path.read_text()) or {}
        except Exception as exc:
            logger.warning("Failed to load rules from %s: %s", self._rules_path, exc)
            return

        self._prompt_rules = [
            PromptRule(scope=r["scope"], text=r["text"]) for r in raw.get("prompt_rules", [])
        ]
        self._policy_rules = [
            PolicyRule(
                id=r["id"],
                when=PolicyCondition(
                    tool=r["when"].get("tool"),
                    arg=r["when"].get("arg"),
                    matches=r["when"].get("matches"),
                    plan_steps_gt=r["when"].get("plan_steps_gt"),
                ),
                action=r["action"],
            )
            for r in raw.get("policy_rules", [])
        ]
        logger.info(
            "Policy engine loaded: %d prompt rules, %d policy rules",
            len(self._prompt_rules),
            len(self._policy_rules),
        )

    def reload(self) -> None:
        """Clear all rules and re-read from disk."""
        self._prompt_rules.clear()
        self._policy_rules.clear()
        self.load()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_prompt_rules(self, scope: str = "global") -> list[str]:
        """Return prompt rule texts matching ``scope``."""
        return [r.text for r in self._prompt_rules if r.scope == scope]

    def evaluate_tool_call(self, tool_name: str, args: dict[str, Any]) -> PolicyResult:
        """Evaluate policy rules against a tool call.

        Returns the first matching result; falls back to ``allow``.
        Plan-step rules (``plan_steps_gt``) are skipped here.
        """
        for rule in self._policy_rules:
            cond = rule.when
            if cond.plan_steps_gt is not None:
                continue  # plan-level rule — not applicable here

            if cond.tool is not None and cond.tool != tool_name:
                continue

            if cond.arg is not None and cond.matches is not None:
                arg_value = str(args.get(cond.arg, ""))
                if not re.search(cond.matches, arg_value):
                    continue

            return PolicyResult(
                action=rule.action,
                rule_id=rule.id,
                reason=f"Policy rule '{rule.id}' triggered.",
            )

        return PolicyResult(action="allow")

    def evaluate_plan_steps(self, step_count: int) -> PolicyResult:
        """Evaluate plan-level rules (``plan_steps_gt``)."""
        for rule in self._policy_rules:
            cond = rule.when
            if cond.plan_steps_gt is not None and step_count > cond.plan_steps_gt:
                return PolicyResult(
                    action=rule.action,
                    rule_id=rule.id,
                    reason=f"Plan has {step_count} steps (limit: {cond.plan_steps_gt}).",
                )
        return PolicyResult(action="allow")


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


def policy_guard_node(state: GraphState) -> Any:
    """LangGraph node — evaluates policy rules for ``pending_tool`` before execution.

    Routing:
    - No ``pending_tool``  → supervisor (passthrough)
    - ``deny``             → supervisor (rejection added to observations)
    - ``require_approval`` → hitl_tool
    - ``allow``            → tool_executor
    """
    from langgraph.types import Command

    pending: dict[str, Any] = state.get("pending_tool") or {}
    if not pending:
        return Command(goto="supervisor")

    tool_name: str = pending.get("name", "")
    args: dict[str, Any] = pending.get("args", {})

    result = get_policy_engine().evaluate_tool_call(tool_name, args)

    if result.action == "deny":
        observations = list(state.get("observations") or [])
        observations.append(f"[POLICY DENIED] {tool_name}: {result.reason}")
        return Command(
            goto="supervisor",
            update={"observations": observations, "pending_tool": None},
        )

    if result.action == "require_approval":
        return Command(goto="hitl_tool")

    # allow
    return Command(goto="tool_executor")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine
