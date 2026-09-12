# Imagem da API (FastAPI). Build a partir da raiz do monorepo:
#   docker build -f infra/docker/api.Dockerfile -t dhf-api .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

# Só o necessário para resolver as dependências de dhf-api (e suas deps de workspace
# dhf-shared/dhf-schemas/dhf-storage/dhf-avatars) — não precisa de
# workers/job_worker nem do frontend aqui.
COPY pyproject.toml uv.lock ./
COPY packages/shared packages/shared
COPY packages/schemas packages/schemas
COPY services/storage services/storage
COPY core/avatars core/avatars
COPY apps/api apps/api
COPY migrations migrations
COPY infra/docker/api-entrypoint.sh infra/docker/api-entrypoint.sh

RUN uv sync --frozen --no-dev --package dhf-api && \
    chmod +x /workspace/infra/docker/api-entrypoint.sh

ENV PATH="/workspace/.venv/bin:$PATH"

EXPOSE 8000
WORKDIR /workspace/apps/api
ENTRYPOINT ["/workspace/infra/docker/api-entrypoint.sh"]
