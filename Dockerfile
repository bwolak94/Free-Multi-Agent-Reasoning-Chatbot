FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies first (layer cache)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY api/ ./api/
COPY agents/ ./agents/
COPY tools/ ./tools/
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
