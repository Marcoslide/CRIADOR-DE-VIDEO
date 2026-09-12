"""apps/api não é instalado como pacote no venv (tool.uv.package = false — é uma
aplicação, não uma lib importável de outros serviços). Para os testes de integração
conseguirem `from app.main import app`, adicionamos apps/api ao sys.path aqui.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP contra a app ASGI real (sem subir um servidor de verdade) — usado por
    todo teste marcado requires_services que fala com a API."""
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _dispose_db_engine_per_test():
    """pytest-asyncio cria um event loop novo por teste; o AsyncEngine é cacheado
    (lru_cache) e fica preso ao loop em que nasceu. Sem isso, o segundo teste tenta
    reusar conexões de um loop já fechado (RuntimeWarning: coroutine never awaited)."""
    yield
    from dhf_shared.db import get_engine, get_sessionmaker

    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
