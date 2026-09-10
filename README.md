# Digital Human Video Factory

Plataforma própria para criação automatizada de vídeos com humanos digitais
fotorrealistas. Requisito P0: **realismo** — qualidade acima de velocidade, custo de GPU
e quantidade.

- Visão, fases e critérios de pronto: [`ROADMAP.md`](./ROADMAP.md)
- Arquitetura, schemas e decisões técnicas: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)

Status atual: **Fase 1 — Foundation.**

## Stack

Python 3.11 + FastAPI · React + TypeScript + Vite · PostgreSQL 16 · Redis 7 · Celery ·
Docker Compose. Gerenciamento de dependências Python via [`uv`](https://docs.astral.sh/uv/)
(workspace).

## Estrutura

```
apps/web        React — dashboard e telas
apps/api        FastAPI — API HTTP principal
packages/shared  config, logging, db, Celery (compartilhado)
packages/schemas contratos Pydantic compartilhados
workers/job_worker  worker Celery de jobs gerais
migrations        Alembic
infra/docker       Dockerfiles
```

A árvore completa (incluindo o que ainda não existe fisicamente — `core/`, `services/`,
`engines/`, etc.) está documentada em `docs/ARCHITECTURE.md` §2.

## Rodando localmente com Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:5173
- API: http://localhost:8000 (docs em `/docs`)
- Health checks: `/health`, `/health/ready`, `/health/worker`

## Rodando sem Docker (dev)

Requer PostgreSQL e Redis rodando localmente (ou via `docker compose up postgres redis`).

```bash
# Backend
uv sync --all-packages
uv run --project apps/api alembic -c migrations/alembic.ini upgrade head
uv run --project apps/api uvicorn app.main:app --reload
uv run --project workers/job_worker celery -A worker.celery_app worker --loglevel=INFO

# Frontend
cd apps/web
npm install
cp .env.example .env
npm run dev
```

## Testes

```bash
uv run --group dev pytest
```

Requer PostgreSQL e Redis acessíveis (mesmas variáveis de `.env`).

## Convenção de trabalho

Este projeto é construído fase a fase (ver `ROADMAP.md`), card por card. Nenhuma
funcionalidade é considerada "pronta" só por ter código escrito — ver a Definition of Done
de cada fase. Regra **zero fake**: nenhum status de integração externa é exibido como
conectado/funcionando sem estar de fato testado (`docs/ARCHITECTURE.md` §5).
