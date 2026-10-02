## Summary

<!-- 1–3 sentences: what does this PR do and why? -->

Closes <!-- T-number or issue -->

---

## Type of change

- [ ] `feat` — new feature or agent capability
- [ ] `fix` — bug fix
- [ ] `refactor` — no behaviour change
- [ ] `test` — tests only
- [ ] `docs` — documentation only
- [ ] `chore` — build, deps, tooling, CI
- [ ] `security` — security fix

---

## Changes

<!-- Bullet list of what changed. Be specific. -->

-
-

---

## How to test

<!-- Steps a reviewer can follow to verify the change locally. -->

```bash

```

---

## Checklist

### Code quality
- [ ] `make lint` passes (ruff + mypy)
- [ ] `make test` passes — all tests green
- [ ] No secrets, hardcoded keys, or `.env` values committed
- [ ] No `print()` — uses `structlog` logger

### For new agents / tools
- [ ] Unit test with `FakeLLM` added in `tests/unit/`
- [ ] Integration test with recorded fixture added in `tests/integration/`
- [ ] Tool registered in `ToolRegistry` and visible in `GET /tools`
- [ ] Prompt rules / policy rules updated if applicable

### For API changes
- [ ] New endpoint documented in `docs/key-features.md` or `docs/workflows.md`
- [ ] Pydantic request/response models defined and validated
- [ ] SSE event types updated if new event introduced

### For infrastructure changes
- [ ] `docker-compose.yml` and `docker-compose.prod.yml` in sync
- [ ] `.env.example` updated with any new required variables
- [ ] Migration created if schema changed (`uv run alembic revision --autogenerate`)

### Deployment impact
- [ ] No breaking changes to thread/checkpoint schema (or migration provided)
- [ ] No breaking changes to SSE event protocol (or UI updated in same PR)
- [ ] Deployment notes below (if any)

---

## Deployment notes

<!-- Any manual steps needed on deploy (migrations, config changes, etc.)? -->

None / <!-- describe if needed -->

---

## Screenshots / traces

<!-- For UI changes: before/after screenshots. For agent changes: Langfuse trace link. -->
