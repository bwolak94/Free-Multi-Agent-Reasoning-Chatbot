# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Added
- M1: FastAPI app with SSE streaming, LiteLLM gateway (Groq / Gemini / OpenRouter / Cerebras fallback), Postgres checkpointer, LangGraph skeleton
- M2: Planner, deterministic Supervisor, HITL interrupt/resume (plan + tool call), Research Agent (SearXNG + Tavily fallback)
- M3: Tool Registry, MCP loader, Tool Agent
- M4: Policy Engine (YAML rules) with hot reload
- M5: Redis/arq worker, Image Agent (Pollinations + HF Inference), Cloudflare R2 artifact storage
- M6: Video Agent (HF Spaces), Reflector, Synthesizer, HITL #3
- M7: Langfuse observability, eval suite (FakeLLM), Next.js chat UI, Hetzner infrastructure

### Fixed
- Deploy workflow: lowercase GHCR image names, `packages: write` / `issues: write` permissions, server deploy gated on `DEPLOY_*` secrets
- Security workflow, Dependabot and CODEOWNERS paths (`ui/` → `frontend/`, correct GitHub handle)
- `make infra` service name (`langfuse-server`)

### Docs
- README rewritten with Mermaid diagrams (architecture, agent graph, HITL sequence, deploy pipeline); MIT LICENSE added

---

## [0.1.0] — 2026-10-02

### Added
- Initial project documentation:
  - `docs/prd.md` — Product Requirements Document
  - `docs/tech-stack.md` — Architecture diagram and stack decisions
  - `docs/workflows.md` — Agent graph and HITL flow diagrams
  - `docs/key-features.md` — Feature specification
  - `docs/tasks/` — 23 implementation tasks with agent assignments
- GitHub project structure (CONTRIBUTING, SECURITY, PR template, issue templates)
- GitHub Actions workflows: CI (lint + test + build), Deploy, Security (Trivy + Gitleaks + CodeQL)
- Branch strategy and commit conventions documented

[Unreleased]: https://github.com/bwolak94/Free-Multi-Agent-Reasoning-Chatbot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bwolak94/Free-Multi-Agent-Reasoning-Chatbot/releases/tag/v0.1.0
