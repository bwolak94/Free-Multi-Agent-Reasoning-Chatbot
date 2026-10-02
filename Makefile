.PHONY: help dev lint type-check test eval build deploy logs clean

# Default target
help:
	@echo ""
	@echo "Free Multi-Agent Reasoning Chatbot"
	@echo "==================================="
	@echo ""
	@echo "Development:"
	@echo "  make dev           Start API + Worker (hot reload)"
	@echo "  make infra         Start Postgres, Redis, SearXNG, Langfuse"
	@echo "  make migrate       Run Alembic migrations"
	@echo "  make logs          Tail Docker Compose logs"
	@echo ""
	@echo "Code quality:"
	@echo "  make lint          ruff format + lint check"
	@echo "  make lint-fix      ruff format + lint with auto-fix"
	@echo "  make type-check    mypy strict type check"
	@echo "  make check         lint + type-check (run before PR)"
	@echo ""
	@echo "Testing:"
	@echo "  make test          pytest unit + integration (no live API)"
	@echo "  make test-cov      pytest with coverage report"
	@echo "  make eval          full eval suite"
	@echo ""
	@echo "Deployment:"
	@echo "  make build         Build Docker images"
	@echo "  make deploy        Pull + rebuild + restart (production)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean         Remove __pycache__, .pytest_cache, etc."
	@echo ""

# =============================================================================
# Development
# =============================================================================

infra:
	docker compose up -d postgres redis searxng langfuse

dev: infra
	uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
	uv run arq workers.main.WorkerSettings

migrate:
	uv run alembic upgrade head

logs:
	docker compose logs -f

# =============================================================================
# Code quality
# =============================================================================

lint:
	uv run ruff format --check .
	uv run ruff check .

lint-fix:
	uv run ruff format .
	uv run ruff check --fix .

type-check:
	uv run mypy .

check: lint type-check

# =============================================================================
# Testing
# =============================================================================

test:
	uv run pytest tests/ -v --tb=short

test-cov:
	uv run pytest tests/ -v --tb=short --cov=. --cov-report=term-missing --cov-report=html

eval:
	uv run pytest tests/ -v --tb=short -m "eval"

# =============================================================================
# Docker / Deployment
# =============================================================================

build:
	docker compose build

deploy:
	git pull origin main
	docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
	docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api uv run alembic upgrade head
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --wait api worker
	docker image prune -f
	@echo "Deploy complete."

# =============================================================================
# Maintenance
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	@echo "Clean complete."
