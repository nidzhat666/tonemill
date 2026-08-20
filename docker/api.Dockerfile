# Tonemill API — FastAPI, installed with uv.
FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/src ./src
RUN uv sync --frozen --no-dev

# uv run re-syncs the venv against the full lockfile (dev group included) by default on
# every invocation, undoing the --no-dev build above and re-downloading it at every
# container start. UV_NO_SYNC pins runtime `uv run` to the already-built venv as-is.
ENV UV_NO_SYNC=1

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "tonemill.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
