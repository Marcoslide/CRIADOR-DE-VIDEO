"""Testes reais de `docker compose config` — client-side, não precisa do daemon rodando,
só do binário `docker` no PATH (chamado de verdade via subprocess, nada de mock). Pulados
se `docker` não existir (ex.: máquina de dev sem Docker); nos runners do CI (ubuntu-latest)
o binário sempre existe, então lá isso roda de verdade, não é pulado.

Cobre o bug corrigido nesta rodada: `docker compose up --build` (dev, sem .env) falhava
porque as guardas ${VAR:?...} do arquivo base disparavam durante a interpolação do PRÓPRIO
arquivo base — que acontece antes do merge com docker-compose.override.yml. As guardas
foram movidas para docker-compose.prod.yml; os testes abaixo confirmam as duas pontas:
dev funciona sem nada configurado, e produção continua recusando subir sem credencial real.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="binário docker não disponível neste ambiente"
)


def _config(
    *compose_files: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """`docker compose config` isolado: não herda variáveis do shell chamador e não lê um
    .env real que porventura exista na raiz do repo (--env-file /dev/null)."""
    args = ["docker", "compose", "--env-file", "/dev/null"]
    for f in compose_files:
        args += ["-f", f]
    args += ["config", "--format", "json"]

    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    if extra_env:
        env.update(extra_env)

    return subprocess.run(args, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=30)


def test_dev_compose_resolves_without_any_env_file_or_vars():
    result = _config("docker-compose.yml", "docker-compose.override.yml")
    assert result.returncode == 0, result.stderr

    postgres_env = json.loads(result.stdout)["services"]["postgres"]["environment"]
    assert postgres_env["POSTGRES_USER"] == "dhf"
    assert postgres_env["POSTGRES_PASSWORD"] == "dhf"
    assert postgres_env["POSTGRES_DB"] == "dhf"


def test_prod_overlay_still_refuses_to_start_without_real_credentials():
    """A guarda ${VAR:?...} só mudou de arquivo (base -> overlay de produção) — produção
    continua recusando subir com credencial ausente."""
    result = _config("docker-compose.yml", "docker-compose.prod.yml")
    assert result.returncode != 0
    assert "required variable" in result.stderr


def test_prod_overlay_works_with_real_credentials_and_keeps_db_ports_unpublished():
    result = _config(
        "docker-compose.yml",
        "docker-compose.prod.yml",
        extra_env={
            "POSTGRES_USER": "produser",
            "POSTGRES_PASSWORD": "prodpass123",
            "POSTGRES_DB": "proddb",
            "VITE_API_URL": "https://api.example.com",
        },
    )
    assert result.returncode == 0, result.stderr

    services = json.loads(result.stdout)["services"]
    assert services["postgres"]["environment"]["POSTGRES_PASSWORD"] == "prodpass123"
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert services["api"]["ports"][0]["host_ip"] == "127.0.0.1"
