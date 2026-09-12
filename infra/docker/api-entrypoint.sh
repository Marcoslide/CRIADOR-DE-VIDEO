#!/bin/sh
# Aplica migrations antes de subir a API. Adequado para um único nó/uma única réplica
# (V1, seção 5 do prompt-mestre) — se algum dia houver múltiplas réplicas de api, migrar
# isso para um job de deploy separado.
set -e

echo "[api-entrypoint] aplicando migrations..."
alembic -c /workspace/migrations/alembic.ini upgrade head

echo "[api-entrypoint] iniciando uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
