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
packages/shared  config, logging, db, Celery, sanitização de erros (compartilhado)
packages/schemas contratos Pydantic compartilhados (StorageProvider, health, ...)
services/storage GoogleDriveStorageProvider real
workers/job_worker  worker Celery de jobs gerais
migrations        Alembic
infra/docker       Dockerfiles + nginx.conf (produção)
docker-compose.yml           base (segura, sem porta de banco publicada, sem senha padrão)
docker-compose.override.yml  conveniências de dev (auto-carregado por `docker compose up`)
docker-compose.prod.yml      overlay de produção (uso explícito com -f)
```

A árvore completa (incluindo o que ainda não existe fisicamente — `core/`, `services/`,
`engines/`, etc.) está documentada em `docs/ARCHITECTURE.md` §2.

## Rodando localmente com Docker Compose (dev)

```bash
cp .env.example .env
docker compose up --build
```

`docker compose` carrega `docker-compose.yml` (base) + `docker-compose.override.yml`
(conveniências de dev) automaticamente — não precisa passar `-f`.

- Web: http://localhost:5173 (servidor de dev do Vite)
- API: http://localhost:8000 (docs em `/docs`)
- Health checks: `/health`, `/health/ready`, `/health/worker`, `/storage/status`
- PostgreSQL/Redis só ficam acessíveis em `127.0.0.1` (não na rede) — convenientes para
  `psql`/`redis-cli` locais, não expostos para fora da máquina.

## Rodando em produção

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
export VITE_API_URL=https://api.seudominio.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**Nunca** copie `.env.example` para o `.env` de produção — ele só tem credenciais de
desenvolvimento (ver aviso no topo do próprio arquivo). Escreva um `.env` de produção à
mão (ou injete via secret manager) com segredos reais.

Diferenças do overlay de produção (`docker-compose.prod.yml`):
- PostgreSQL e Redis **não publicam porta nenhuma** — só alcançáveis pela rede interna do
  Compose;
- `POSTGRES_USER`/`PASSWORD`/`DB` são obrigatórios (o compose recusa subir sem eles —
  `${VAR:?...}`), sem valor padrão;
- `web` serve um build estático via nginx (não o servidor de desenvolvimento do Vite);
- todos os serviços reiniciam sozinhos (`restart: unless-stopped`).

## Rodando sem Docker (dev)

Requer PostgreSQL e Redis rodando localmente (ou via `docker compose up postgres redis`).

```bash
# Backend
uv sync --all-packages
uv run --project apps/api alembic -c migrations/alembic.ini upgrade head
uv run --directory apps/api uvicorn app.main:app --reload
uv run --directory workers/job_worker celery -A worker.celery_app worker --loglevel=INFO

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
