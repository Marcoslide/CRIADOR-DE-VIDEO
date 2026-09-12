# Imagem do job_worker (Celery). Build a partir da raiz do monorepo:
#   docker build -f infra/docker/worker.Dockerfile -t dhf-job-worker .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY packages/shared packages/shared
COPY workers/job_worker workers/job_worker

RUN uv sync --frozen --no-dev --package dhf-job-worker

ENV PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace/workers/job_worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]
