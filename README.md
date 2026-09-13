# Digital Human Video Factory

Plataforma própria para criação automatizada de vídeos com humanos digitais
fotorrealistas. Requisito P0: **realismo** — qualidade acima de velocidade, custo de GPU
e quantidade.

- Visão, fases e critérios de pronto: [`ROADMAP.md`](./ROADMAP.md)
- Arquitetura, schemas e decisões técnicas: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)

Status atual: **Fase 1 (Foundation) e Fase 2 (Storage/Google Drive) concluídas.** OAuth
`drive.file`, root criada pelo app, árvore 18/18 e contrato de arquivos foram validados no
Drive real. Fase 3 (Avatar Registry) em fundação:
CRUD real com máquina de estados, persistindo no PostgreSQL. Regra **zero fake** em vigor
em todo o sistema: nenhuma integração aparece como conectada sem ter sido checada de
verdade nesta requisição (`docs/ARCHITECTURE.md` §5) — o Dashboard mostra
`NOT_CONFIGURED`/`NOT_INSTALLED` honestamente para tudo que ainda não existe.

## Stack

Python 3.11 + FastAPI · React + TypeScript + Vite · PostgreSQL 16 · Redis 7 · Celery ·
Docker Compose. Gerenciamento de dependências Python via [`uv`](https://docs.astral.sh/uv/)
(workspace).

## Pré-requisitos

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (gerencia o Python 3.11
  do workspace sozinho — não precisa instalar Python à parte)
- Node.js 22+ e npm (frontend)
- Docker + Docker Compose v2, **ou** PostgreSQL 16 e Redis 7 instalados localmente (ver
  "Rodando sem Docker" abaixo)

## Estrutura

```
apps/web         React — dashboard e telas
apps/api         FastAPI — API HTTP principal
packages/shared  config, logging, db, Celery, sanitização de erros (compartilhado)
packages/schemas contratos Pydantic compartilhados (StorageProvider, health, status, jobs, ...)
services/storage GoogleDriveStorageProvider real
core/avatars     Avatar Registry — CRUD + máquina de estados (Fase 3, fundação)
workers/job_worker  worker Celery de jobs gerais
migrations        Alembic
infra/docker       Dockerfiles + nginx.conf (produção)
docker-compose.yml           base (segura, sem porta de banco publicada, sem senha padrão)
docker-compose.override.yml  conveniências de dev (auto-carregado por `docker compose up`)
docker-compose.prod.yml      overlay de produção (uso explícito com -f)
```

A árvore completa (incluindo o que ainda não existe fisicamente — `engines/`, etc.) está
documentada em `docs/ARCHITECTURE.md` §2.

## Rodando localmente com Docker Compose (dev)

```bash
cp .env.example .env
docker compose up --build
```

`docker compose` carrega `docker-compose.yml` (base) + `docker-compose.override.yml`
(conveniências de dev) automaticamente — não precisa passar `-f`.

- Web: http://localhost:5173 (servidor de dev do Vite)
- API: http://localhost:8000 (docs interativos em `/docs`)
- PostgreSQL/Redis só ficam acessíveis em `127.0.0.1` (não na rede) — convenientes para
  `psql`/`redis-cli` locais, não expostos para fora da máquina.

Ver a lista completa de URLs úteis mais abaixo.

**Parar:**

```bash
docker compose down          # para os containers, mantém os dados (volumes)
docker compose down -v       # para e apaga também os dados do Postgres/Redis
```

**Logs:**

```bash
docker compose logs -f              # todos os serviços
docker compose logs -f api worker   # só API + worker
```

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
- a API liga somente em `127.0.0.1:${API_PORT:-8000}`. Como esta fundação ainda não tem
  autenticação própria, exponha-a apenas por um reverse proxy TLS com autenticação e
  firewall; nunca publique a porta 8000 diretamente na internet;
- `POSTGRES_USER`/`PASSWORD`/`DB` e `VITE_API_URL` são obrigatórios (o compose recusa
  subir sem eles — `${VAR:?...}`), sem valor padrão;
- `web` serve um build estático via nginx (não o servidor de desenvolvimento do Vite);
- todos os serviços reiniciam sozinhos (`restart: unless-stopped`).

**Parar:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`.

## Rodando sem Docker (dev)

Requer PostgreSQL e Redis rodando localmente (ou via `docker compose up postgres redis`)
e as variáveis de `.env` apontando para eles.

```bash
# Backend
cp .env.example .env
uv sync --all-packages
uv run alembic -c migrations/alembic.ini upgrade head
uv run --directory apps/api uvicorn app.main:app --reload
uv run --directory workers/job_worker celery -A worker.celery_app worker --loglevel=INFO
```

```bash
# Frontend (outro terminal)
cd apps/web
npm install
cp .env.example .env
npm run dev
```

`apps/api` e `workers/job_worker` não são pacotes instaláveis (`tool.uv.package = false`
— são aplicações, não libs importadas por outro serviço), por isso rodam via
`uv run --directory <pasta>` em vez de `--project` (que só mudaria a resolução de
dependências, não o diretório de execução do processo).

**Parar:** `Ctrl+C` em cada processo (API, worker, `npm run dev`). Para checar o que
ainda está rodando: `pgrep -af "uvicorn|celery|vite"`.

**Logs:** cada processo imprime logs estruturados (JSON) direto no terminal em que foi
iniciado — não há arquivo de log próprio nesta fase.

## URLs e endpoints

Com o backend no ar (Docker ou nativo):

| URL | O que é |
|---|---|
| `GET /docs` | Swagger UI (todos os endpoints, interativo) |
| `GET /health` | Liveness — só confirma que o processo da API está de pé |
| `GET /health/ready` | Readiness — checa PostgreSQL e Redis de verdade |
| `GET /health/worker` | Round-trip real via Celery/Redis até o worker e de volta |
| `GET /storage/status` | Status real da integração com Google Drive |
| `GET /status/system` | Status agregado (API/Postgres/Redis/worker/storage/GPU/OpenAI/Unreal/Audio2Face/MetaHuman) — o que o Dashboard consome |
| `POST /jobs/diagnostic` → `GET /jobs/diagnostic/{id}` | Prova de ponta a ponta API → Redis → Worker |
| `POST /avatars`, `GET /avatars`, `GET /avatars/{id}`, `PATCH /avatars/{id}`, `DELETE /avatars/{id}` | Avatar Registry (CRUD + máquina de estados; PATCH/DELETE exigem versão esperada) |

No frontend (http://localhost:5173): `/` é o Dashboard (status real de todos os
componentes) e `/avatars` é o Avatar Registry. As demais entradas do menu ainda mostram
"NOT CONFIGURED / no roadmap" honestamente — ver `apps/web/src/nav.ts` para a fase de cada
uma.

## Migrations

```bash
uv run alembic -c migrations/alembic.ini upgrade head     # aplicar
uv run alembic -c migrations/alembic.ini current           # ver a revisão atual
uv run alembic -c migrations/alembic.ini history            # ver o histórico
```

Migrations deste projeto são escritas à mão (não autogeradas) — ver `migrations/env.py`
para como cada modelo de domínio precisa ser importado ali para entrar em
`Base.metadata`.

## Testes

```bash
uv run pytest                                        # tudo, incluindo os que precisam de Postgres/Redis/worker reais
uv run pytest -m "not requires_services and not integration"   # só unitários (sem serviços externos)
uv run pytest -m requires_services                    # só os que precisam de Postgres/Redis/worker reais
```

Sem mocks nos testes de integração: eles sobem contra PostgreSQL/Redis/worker de verdade
(mesmas variáveis de `.env`) e confirmam que os dados realmente persistem — inclusive
após descartar e recriar todo o pool de conexões, equivalente à fronteira de persistência
de um restart (`tests/api/test_avatars.py`). Os testes de
`tests/storage/test_google_drive_integration.py` (marcados `integration`) precisam de uma
credencial OAuth User ou Service Account real e ficam `SKIPPED` sem ela — isso é esperado,
não é falha. Quando habilitados, cobrem o contrato completo e uma retomada real de upload
após falha de transporte injetada localmente.

Outras checagens que o CI roda (ver `.github/workflows/ci.yml`) e que valem rodar antes de
subir uma mudança:

```bash
uv run ruff check .           # lint
uv run ruff format --check .  # formatação
cd apps/web && npm run typecheck && npm run build
docker compose config --quiet  # valida o YAML sem precisar buildar nenhuma imagem
gitleaks detect --source . --redact --verbose   # varredura de segredos (precisa do binário gitleaks)
```

## Troubleshooting

**`docker compose build` falha baixando `ghcr.io/astral-sh/uv` (403/timeout).**
Ambiente com proxy/firewall que não libera registries de container (comum em sandboxes
restritos). Não é um problema do projeto — ou libere `ghcr.io`/Docker Hub na rede, ou rode
sem Docker (seção "Rodando sem Docker" acima), que não depende de nenhum registry.

**Porta já em uso (5173, 8000, 5432, 6379).**
Outro processo (ou uma sessão anterior) ainda está de pé. `docker compose down` se for
container; nativamente, `pgrep -af "uvicorn|celery|vite"` e `kill <pid>`.

**`/health/ready` reporta `postgres`/`redis` com `status: "error"`.**
A API não fingirá que está tudo bem — o `detail` sanitizado só diz "não foi possível
conectar"; o erro completo (host/porta) vai para o log estruturado da API. Confira se
`POSTGRES_HOST`/`PORT` e `REDIS_HOST`/`PORT` do `.env` batem com onde o Postgres/Redis
realmente estão escutando.

**`/health/worker` fica `timeout` ou nunca fica `connected`.**
O worker Celery não está rodando, ou está apontando para um Redis diferente do da API.
Confirme que `uv run --directory workers/job_worker celery -A worker.celery_app worker
--loglevel=INFO` está de pé e usando o mesmo `.env`.

**Erro de CORS no console do navegador.**
`API_CORS_ORIGINS` no `.env` da API precisa incluir a origem real do frontend (por
padrão `["http://localhost:5173"]`).

**Alembic reclama de revisão desconhecida / tabela já existe.**
Compare `alembic current` com `alembic history`. Este projeto não autogera migrations —
se você criou uma tabela nova à mão no banco por engano, o caminho seguro é dropar o
banco de dev e rodar `upgrade head` de novo, não editar a migration já aplicada.

**`POST /avatars` retorna 409.**
Não é bug — slug já em uso (unicidade real, checada no banco) ou transição de status
inválida (a máquina de estados do Avatar Registry é linear, sem pular etapas — ver
`core/avatars/dhf_avatars/schemas.py`).

**Storage/OpenAI/GPU/Unreal aparecem como `NOT_CONFIGURED`/`NOT_INSTALLED`.**
Esperado sem credencial/hardware configurado — é a regra zero fake em ação. O Storage
também pode aparecer como `DEGRADED` quando a cota Google está esgotada. Ver
`docs/STORAGE_GOOGLE_DRIVE.md`.

## Convenção de trabalho

Este projeto é construído fase a fase (ver `ROADMAP.md`), card por card. Nenhuma
funcionalidade é considerada "pronta" só por ter código escrito — ver a Definition of Done
de cada fase. Regra **zero fake**: nenhum status de integração externa é exibido como
conectado/funcionando sem estar de fato testado (`docs/ARCHITECTURE.md` §5).
