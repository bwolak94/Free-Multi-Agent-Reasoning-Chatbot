# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Planned (M1)
- FastAPI app with SSE streaming and health endpoint
- LangGraph skeleton with BaseState and Postgres checkpointer
- LiteLLM gateway with Groq / Gemini / OpenRouter fallback chain
- AWS EC2 infrastructure (Docker Compose, nginx, S3, IAM)
- Thread persistence and resume across restarts

### Planned (M2)
- Planner node with structured Plan output
- Deterministic Supervisor router
- HITL interrupt/resume at plan and tool-call level
- Research Agent (SearXNG + Jina Reader + citation synthesis)

### Planned (M3–M7)
- Tool Registry, @tool decorator, MCP loader
- Policy Engine (YAML rules, hot reload)
- Redis/arq worker, Image Agent (Pollinations + HF Inference)
- AWS S3 artifact storage
- Video Agent (HF Spaces), Reflector, Synthesizer, HITL #3
- Langfuse observability, eval suite, minimal Next.js UI

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
- GitHub Actions workflows: CI (lint + test + build), Deploy (EC2), Security (Trivy + Gitleaks + CodeQL)
- Branch strategy and commit conventions documented

[Unreleased]: https://github.com/your-org/free-multi-agent-reasoning-chatbot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/free-multi-agent-reasoning-chatbot/releases/tag/v0.1.0
