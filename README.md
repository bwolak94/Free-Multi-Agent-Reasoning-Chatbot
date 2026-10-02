# Free Multi-Agent Reasoning Chatbot

[![CI](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/ci.yml)
[![Deploy](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/deploy.yml/badge.svg)](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/deploy.yml)
[![Security](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/security.yml/badge.svg)](https://github.com/your-org/free-multi-agent-reasoning-chatbot/actions/workflows/security.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A self-hostable, zero-cost multi-agent reasoning chatbot with **human-in-the-loop (HITL)** approval flows, specialist agents (research, image, video, tools), MCP extensibility, and durable resumable threads.

Runs on free LLM tiers (Groq, Gemini, OpenRouter, Cerebras) behind a fallback-aware gateway. Deployed on AWS EC2 `t3.medium` via Docker Compose for ~$32/month.

---

## Architecture

```
Client (Next.js)
    │ HTTPS + SSE
FastAPI ──► LangGraph Runtime ──► LiteLLM Gateway
                │                        │
                │                ┌───────┴──────────────┐
                │            Groq / Cerebras /        Gemini /
                │            OpenRouter :free          free tier
                │
        ┌───────┼────────────┐
        │       │            │
     Postgres  Redis        S3
  (checkpoints) (queue)  (artifacts)
        │
    ┌───┴──────────────────────────────────┐
    │              Agent Graph             │
    │  Router → Planner → Supervisor       │
    │     ↓ HITL#1                         │
    │  Research / Image / Video / Tool     │
    │     ↓ HITL#2 (high-risk tools)       │
    │  Reflector → Synthesizer             │
    │     ↓ HITL#3 (optional review)       │
    └──────────────────────────────────────┘
```

Full architecture diagram: [`docs/tech-stack.md`](docs/tech-stack.md)
Agent workflows: [`docs/workflows.md`](docs/workflows.md)
Key features: [`docs/key-features.md`](docs/key-features.md)
Product requirements: [`docs/prd.md`](docs/prd.md)

---

## Key Features

| Feature | Description |
|---|---|
| Multi-step reasoning | Plan → Execute → Reflect with user-approvable plans |
| Specialist agents | Research (search + citations), Image gen, Video gen, Tool execution |
| Human-in-the-loop | Approve / edit / reject at plan, tool-call, and output level |
| $0 LLM cost | Groq, Cerebras, Gemini free tier, OpenRouter :free with auto-fallback |
| MCP extensibility | Plug in any MCP server via `config/mcp.yaml`, no code changes |
| Durable threads | Threads survive restarts; HITL interrupts persist indefinitely |
| Policy engine | Deterministic YAML rules — deny, require approval, output filters |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI, sse-starlette, Pydantic v2 |
| Orchestration | LangGraph (interrupt/resume, subgraphs, Postgres checkpointer) |
| LLM gateway | LiteLLM (fallback chains, rate-limit handling) |
| LLMs | Groq · Cerebras · Gemini free · OpenRouter :free |
| Image gen | Pollinations API · HF Inference (no GPU required) |
| Video gen | HF Spaces via gradio_client (async, best-effort) |
| Queue | Redis + arq |
| Persistence | PostgreSQL 16 |
| Artifacts | AWS S3 (7-day TTL) |
| Observability | Langfuse (self-hosted) · OpenTelemetry · structlog |
| Frontend | Next.js 14 (App Router, TypeScript, Tailwind) |
| Deployment | Docker Compose on AWS EC2 `t3.medium` |

---

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (package manager)
- Docker + Docker Compose plugin
- API keys: Groq, Gemini, OpenRouter, HuggingFace (all free)

---

## Quick Start (Local Dev)

```bash
# 1. Clone and install
git clone https://github.com/your-org/free-multi-agent-reasoning-chatbot.git
cd free-multi-agent-reasoning-chatbot
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env — add your free API keys (Groq, Gemini, OpenRouter, HF_TOKEN)

# 3. Start infrastructure (Postgres, Redis, SearXNG, Langfuse)
docker compose up -d postgres redis searxng langfuse

# 4. Run migrations
uv run alembic upgrade head

# 5. Start API + Worker
make dev
```

API available at `http://localhost:8000`
Langfuse traces at `http://localhost:3000`

### Run tests

```bash
make test          # unit + integration (recorded fixtures, no live API calls)
make lint          # ruff + mypy
make eval          # full eval suite
```

---

## Environment Variables

Copy `.env.example` to `.env`. Required variables:

| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — free | Yes |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) — free | Yes |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) — free tier | Yes |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) — free | Yes |
| `DATABASE_URL` | Postgres connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `AWS_S3_BUCKET` | S3 bucket name for artifacts | Yes |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project public key | Optional |
| `LANGFUSE_SECRET_KEY` | Langfuse project secret key | Optional |
| `TAVILY_API_KEY` | Tavily search fallback — free tier | Optional |
| `USE_LOCAL_FS` | `true` to use local FS instead of S3 (dev) | Optional |
| `USE_SQLITE` | `true` to use SQLite instead of Postgres (dev) | Optional |

---

## Deployment (AWS EC2)

Full guide: [`docs/tasks/T23-aws-infrastructure.md`](docs/tasks/T23-aws-infrastructure.md)

```bash
# On EC2 (Ubuntu 22.04, t3.medium)
git clone https://github.com/your-org/free-multi-agent-reasoning-chatbot.git
cd free-multi-agent-reasoning-chatbot
cp .env.example .env.prod
# Fill in .env.prod with production values

make deploy   # pulls, builds, and starts all containers
```

**Cost:** ~$32/month (EC2 `t3.medium` + S3). LLM inference: $0.

CI/CD: GitHub Actions automatically deploys `main` to EC2 on every merge. See [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

---

## Project Structure

```
.
├── api/                    # FastAPI application
│   ├── main.py             # App entrypoint, routers
│   ├── llm.py              # LiteLLM gateway factory
│   ├── checkpointer.py     # Postgres/SQLite checkpointer
│   └── routers/            # threads, artifacts, tools, admin
├── agents/                 # LangGraph agent subgraphs
│   ├── graph.py            # Main graph assembly
│   ├── state.py            # GraphState TypedDict
│   ├── planner/
│   ├── supervisor/
│   ├── research/
│   ├── image/
│   ├── video/
│   ├── tool/
│   ├── reflector/
│   └── synthesizer/
├── tools/                  # Custom @tool implementations
├── workers/                # arq job definitions
├── config/                 # YAML configuration
│   ├── litellm_config.yaml
│   ├── agents.yaml
│   ├── mcp.yaml
│   └── rules/
│       └── default.yaml
├── tests/                  # pytest test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/           # Recorded LLM/HTTP fixtures
├── ui/                     # Next.js frontend
├── docs/                   # Architecture, PRD, task specs
│   ├── prd.md
│   ├── tech-stack.md
│   ├── workflows.md
│   ├── key-features.md
│   └── tasks/
├── nginx/                  # nginx reverse proxy config
├── docker-compose.yml      # Development
├── docker-compose.prod.yml # Production overrides
├── Makefile
└── pyproject.toml
```

---

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for:
- Branch naming and commit conventions
- Pull request process and required checks
- Running tests locally
- Adding new agents and tools

---

## Roadmap

See [Milestones](https://github.com/your-org/free-multi-agent-reasoning-chatbot/milestones) and [`docs/tasks/README.md`](docs/tasks/README.md).

| Milestone | Status |
|---|---|
| M1 — FastAPI + LangGraph skeleton + SSE | Planned |
| M2 — Planner + Supervisor + Research + HITL | Planned |
| M3 — Tool Registry + MCP + Tool Agent | Planned |
| M4 — Policy Engine + Hot Reload | Planned |
| M5 — Worker + Image Agent + S3 | Planned |
| M6 — Video Agent + Reflector + Synthesizer | Planned |
| M7 — Observability + Eval Suite + React UI | Planned |

---

## Security

See [SECURITY.md](.github/SECURITY.md) for the vulnerability disclosure policy.

---

## License

[MIT](./LICENSE) © Bartosz Wolak
