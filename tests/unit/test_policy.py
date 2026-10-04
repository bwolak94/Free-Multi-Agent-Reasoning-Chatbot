from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import pytest

from agents.policy import PolicyEngine, PolicyResult, get_policy_engine, policy_guard_node

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RULES_YAML = """\
prompt_rules:
  - scope: global
    text: "Always cite sources."
  - scope: agent:image
    text: "Default 16:9."
policy_rules:
  - id: approve-video
    when: { tool: "video.generate" }
    action: require_approval
  - id: block-domains
    when: { tool: "web.fetch", arg: "url", matches: '(facebook|tiktok)\\.com' }
    action: deny
  - id: step-limit
    when: { plan_steps_gt: 3 }
    action: require_approval
"""


@pytest.fixture
def engine(tmp_path: Path) -> PolicyEngine:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(_RULES_YAML)
    e = PolicyEngine(rules_path=rules_file)
    e.load()
    return e


@pytest.fixture(autouse=True)
def reset_engine() -> None:
    """Ensure the global engine singleton is reset between tests."""
    import agents.policy as mod

    mod._engine = None
    yield
    mod._engine = None


# ---------------------------------------------------------------------------
# PolicyEngine.load
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_reads_prompt_rules(engine: PolicyEngine) -> None:
    assert engine.get_prompt_rules("global") == ["Always cite sources."]


@pytest.mark.unit
def test_load_reads_scoped_prompt_rules(engine: PolicyEngine) -> None:
    assert engine.get_prompt_rules("agent:image") == ["Default 16:9."]


@pytest.mark.unit
def test_load_missing_file_logs_warning(tmp_path: Path) -> None:
    e = PolicyEngine(rules_path=tmp_path / "nonexistent.yaml")
    e.load()  # should not raise
    assert e.get_prompt_rules("global") == []


@pytest.mark.unit
def test_load_empty_yaml(tmp_path: Path) -> None:
    (tmp_path / "empty.yaml").write_text("")
    e = PolicyEngine(rules_path=tmp_path / "empty.yaml")
    e.load()
    assert e.get_prompt_rules("global") == []


# ---------------------------------------------------------------------------
# PolicyEngine.evaluate_tool_call
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exact_tool_match_require_approval(engine: PolicyEngine) -> None:
    result = engine.evaluate_tool_call("video.generate", {})
    assert result.action == "require_approval"
    assert result.rule_id == "approve-video"


@pytest.mark.unit
def test_arg_regex_match_deny(engine: PolicyEngine) -> None:
    result = engine.evaluate_tool_call("web.fetch", {"url": "https://facebook.com/page"})
    assert result.action == "deny"
    assert result.rule_id == "block-domains"


@pytest.mark.unit
def test_arg_regex_no_match_allow(engine: PolicyEngine) -> None:
    result = engine.evaluate_tool_call("web.fetch", {"url": "https://example.com"})
    assert result.action == "allow"
    assert result.rule_id is None


@pytest.mark.unit
def test_unknown_tool_allow(engine: PolicyEngine) -> None:
    result = engine.evaluate_tool_call("web.search", {"query": "hello"})
    assert result.action == "allow"


@pytest.mark.unit
def test_plan_steps_rule_skipped_in_tool_eval(engine: PolicyEngine) -> None:
    # The step-limit rule has plan_steps_gt — must not match tool calls
    result = engine.evaluate_tool_call("any.tool", {})
    assert result.action == "allow"


# ---------------------------------------------------------------------------
# PolicyEngine.evaluate_plan_steps
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_steps_over_limit(engine: PolicyEngine) -> None:
    result = engine.evaluate_plan_steps(5)
    assert result.action == "require_approval"
    assert result.rule_id == "step-limit"


@pytest.mark.unit
def test_plan_steps_at_limit_allow(engine: PolicyEngine) -> None:
    result = engine.evaluate_plan_steps(3)
    assert result.action == "allow"


@pytest.mark.unit
def test_plan_steps_under_limit_allow(engine: PolicyEngine) -> None:
    result = engine.evaluate_plan_steps(1)
    assert result.action == "allow"


# ---------------------------------------------------------------------------
# PolicyEngine.reload
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reload_clears_and_re_reads(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(_RULES_YAML)
    e = PolicyEngine(rules_path=rules_file)
    e.load()
    assert e.get_prompt_rules("global") == ["Always cite sources."]

    # Overwrite file with new content
    rules_file.write_text(
        "prompt_rules:\n  - scope: global\n    text: 'Updated.'\npolicy_rules: []\n"
    )
    e.reload()
    assert e.get_prompt_rules("global") == ["Updated."]


# ---------------------------------------------------------------------------
# policy_guard_node
# ---------------------------------------------------------------------------


def _make_engine(action: str, rule_id: str = "test-rule") -> PolicyEngine:
    mock_engine = PolicyEngine.__new__(PolicyEngine)
    mock_engine._prompt_rules = []
    mock_engine._policy_rules = []

    def fake_evaluate(_tool_name: str, _args: object) -> PolicyResult:
        return PolicyResult(action=action, rule_id=rule_id, reason="test")  # type: ignore[arg-type]

    mock_engine.evaluate_tool_call = fake_evaluate  # type: ignore[method-assign]
    return mock_engine


@pytest.mark.unit
def test_guard_no_pending_tool_passthrough() -> None:
    state = {"pending_tool": None, "observations": []}
    with patch("agents.policy.get_policy_engine", return_value=_make_engine("allow")):
        cmd = policy_guard_node(state)  # type: ignore[arg-type]
    assert cmd.goto == "supervisor"


@pytest.mark.unit
def test_guard_allow_routes_to_tool_executor() -> None:
    state = {"pending_tool": {"name": "web.search", "args": {}}, "observations": []}
    with patch("agents.policy.get_policy_engine", return_value=_make_engine("allow")):
        cmd = policy_guard_node(state)  # type: ignore[arg-type]
    assert cmd.goto == "tool_executor"


@pytest.mark.unit
def test_guard_deny_routes_to_supervisor_with_observation() -> None:
    state = {"pending_tool": {"name": "web.fetch", "args": {}}, "observations": []}
    with patch("agents.policy.get_policy_engine", return_value=_make_engine("deny")):
        cmd = policy_guard_node(state)  # type: ignore[arg-type]
    assert cmd.goto == "supervisor"
    assert any("[POLICY DENIED]" in o for o in cmd.update["observations"])
    assert cmd.update["pending_tool"] is None


@pytest.mark.unit
def test_guard_require_approval_routes_to_hitl_tool() -> None:
    state = {
        "pending_tool": {"name": "video.generate", "args": {}},
        "observations": [],
    }
    with patch("agents.policy.get_policy_engine", return_value=_make_engine("require_approval")):
        cmd = policy_guard_node(state)  # type: ignore[arg-type]
    assert cmd.goto == "hitl_tool"


# ---------------------------------------------------------------------------
# get_policy_engine singleton
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_policy_engine_returns_singleton() -> None:
    e1 = get_policy_engine()
    e2 = get_policy_engine()
    assert e1 is e2
