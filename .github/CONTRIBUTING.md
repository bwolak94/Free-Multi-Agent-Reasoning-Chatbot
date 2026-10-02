# Contributing Guide

Thank you for contributing. This document covers the development workflow, branch strategy, commit conventions, and pull request process.

---

## Development Setup

```bash
git clone https://github.com/your-org/free-multi-agent-reasoning-chatbot.git
cd free-multi-agent-reasoning-chatbot

# Install Python deps
uv sync

# Copy and configure environment
cp .env.example .env

# Start infrastructure
docker compose up -d postgres redis searxng langfuse

# Run migrations
uv run alembic upgrade head

# Start dev server
make dev
```

### Verify setup

```bash
make lint        # ruff + mypy — must pass
make test        # pytest — must pass
curl http://localhost:8000/health  # must return {"status":"ok"}
```

---

## Branch Strategy

We use **trunk-based development** with short-lived feature branches.

### Branch naming

```
<type>/<scope>

task/T{nn}-{slug}      # Planned task from docs/tasks/
feat/{slug}            # New feature not in task list
fix/{slug}             # Bug fix
chore/{slug}           # Tooling, deps, config
docs/{slug}            # Documentation only
refactor/{slug}        # Refactoring without behaviour change
```

**Examples:**
```
task/T01-project-scaffold
task/T08-hitl-interrupt-resume
fix/planner-retry-on-bad-json
chore/upgrade-langgraph-0.3
docs/update-architecture-diagram
```

### Rules

- Branch from `main`. Never from another feature branch.
- Keep branches short-lived — merge within days, not weeks.
- Delete branch after merge.
- One task per branch.

---

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<scope>): <short description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When |
|---|---|
| `feat` | New feature or agent capability |
| `fix` | Bug fix |
| `refactor` | Refactoring — no behaviour change |
| `test` | Adding or updating tests |
| `docs` | Documentation only |
| `chore` | Build, deps, tooling, CI |
| `perf` | Performance improvement |
| `security` | Security fix |

### Examples

```
feat(planner): add structured output retry with exponential backoff

fix(hitl): persist interrupt state across API restart

test(research-agent): add recorded fixtures for SearXNG fallback

chore(deps): upgrade langgraph to 0.3.1

docs(workflows): add HITL sequence diagram
```

### Rules

- Subject line: imperative mood, lowercase, no period, max 72 chars.
- Reference task: `Closes T08`, `Part of T15` in the footer.
- Never commit directly to `main`.

---

## Pull Request Process

### Before opening a PR

```bash
make lint        # must pass — ruff + mypy
make test        # must pass — all tests green
make eval        # run eval suite (optional but recommended)
```

### PR requirements

- Title follows Conventional Commits format.
- Description fills in the PR template completely.
- At least **1 approval** required (from CODEOWNERS for the changed area).
- All CI checks green: `ci / lint`, `ci / type-check`, `ci / test`.
- Branch is up to date with `main` before merge.

### Merge strategy

- **Squash and merge** for feature branches (clean history on `main`).
- **Merge commit** for release branches only.
- Never force-push to `main`.

### Branch protection on `main`

- Require PR before merging.
- Require status checks: `lint`, `type-check`, `test`.
- Require up-to-date branch before merge.
- Dismiss stale reviews on push.

---

## Adding a New Agent

1. Create `agents/<name>/` directory with `__init__.py` and `graph.py`.
2. Define agent subgraph: `build_graph() -> StateGraph`.
3. Register in `config/agents.yaml`: name, capabilities, tools.
4. Add agent to supervisor dispatch table in `agents/supervisor/node.py`.
5. Write unit tests with `FakeLLM` in `tests/unit/agents/`.
6. Add integration test with recorded fixture in `tests/integration/`.

---

## Adding a New Tool

```python
# tools/my_tool.py
from tools.base import tool
from pydantic import BaseModel

class MyInput(BaseModel):
    query: str

@tool(risk="low", timeout=10, tags=["web"])
async def my_tool(input: MyInput) -> dict:
    """One-line description used in tool registry."""
    ...
```

Auto-discovered from `tools/` on startup. Test with `GET /tools`.

---

## Adding a Policy Rule

Edit `config/rules/default.yaml` (or create a new file in `config/rules/`):

```yaml
policy_rules:
  - id: my-rule
    when: { tool: "my_tool" }
    action: require_approval
```

Hot-reload with `POST /admin/reload`. Rules are deterministic — no LLM involved.

---

## Code Standards

- **Python:** typed (mypy strict), formatted and linted with ruff.
- **No hardcoded secrets:** use `pydantic-settings` + env vars.
- **Async throughout:** all I/O must be `async/await`.
- **Tests required:** every new node/tool/agent needs a unit test.
- **No `print()`:** use `structlog.get_logger()`.
