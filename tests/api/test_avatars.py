"""Testes de integração do Avatar Registry — fundação real (CRUD + máquina de estados),
seção 12 do prompt-mestre. Requerem PostgreSQL real e acessível (ver README.md "Rodando
sem Docker"). Sem mocks: cada teste cria linhas de verdade no banco e confirma que
persistem — inclusive através de um "restart" simulado do processo.
"""

import asyncio
import uuid

import httpx
import pytest

pytestmark = pytest.mark.requires_services


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def test_create_avatar_persists_in_postgres(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-criacao")
    response = await client.post(
        "/avatars", json={"name": "Avatar de Teste", "slug": slug, "metadata": {"origem": "pytest"}}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Avatar de Teste"
    assert body["slug"] == slug
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert body["metadata"] == {"origem": "pytest"}
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]


async def test_get_avatar_by_id(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-get")
    created = (
        await client.post("/avatars", json={"name": "Buscável", "slug": slug, "metadata": {}})
    ).json()

    response = await client.get(f"/avatars/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_get_nonexistent_avatar_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/avatars/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_avatars_includes_created_avatar(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-list")
    created = (
        await client.post("/avatars", json={"name": "Listável", "slug": slug, "metadata": {}})
    ).json()

    response = await client.get("/avatars")
    assert response.status_code == 200
    ids = {avatar["id"] for avatar in response.json()}
    assert created["id"] in ids


async def test_duplicate_slug_returns_409(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-duplicado")
    first = await client.post("/avatars", json={"name": "Primeiro", "slug": slug, "metadata": {}})
    assert first.status_code == 201

    second = await client.post("/avatars", json={"name": "Segundo", "slug": slug, "metadata": {}})
    assert second.status_code == 409


async def test_concurrent_duplicate_slug_returns_one_created_and_one_conflict(
    client: httpx.AsyncClient,
) -> None:
    slug = _unique_slug("teste-corrida-slug")
    responses = await asyncio.gather(
        client.post("/avatars", json={"name": "Concorrente A", "slug": slug, "metadata": {}}),
        client.post("/avatars", json={"name": "Concorrente B", "slug": slug, "metadata": {}}),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]


async def test_update_metadata_bumps_version(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-metadata")
    created = (
        await client.post("/avatars", json={"name": "Editável", "slug": slug, "metadata": {"v": 1}})
    ).json()
    assert created["version"] == 1

    response = await client.patch(
        f"/avatars/{created['id']}",
        json={"metadata": {"v": 2}, "expected_version": created["version"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["metadata"] == {"v": 2}


async def test_update_with_unchanged_metadata_does_not_bump_version(
    client: httpx.AsyncClient,
) -> None:
    """A versão só sobe quando algo de fato muda — evita ruído no histórico do avatar."""
    slug = _unique_slug("teste-metadata-igual")
    created = (
        await client.post("/avatars", json={"name": "Estável", "slug": slug, "metadata": {"v": 1}})
    ).json()

    response = await client.patch(
        f"/avatars/{created['id']}",
        json={"metadata": {"v": 1}, "expected_version": created["version"]},
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1


async def test_stale_update_returns_409_instead_of_overwriting(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-versao-obsoleta")
    created = (
        await client.post("/avatars", json={"name": "Original", "slug": slug, "metadata": {}})
    ).json()
    first = await client.patch(
        f"/avatars/{created['id']}",
        json={"name": "Primeira edição", "expected_version": created["version"]},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = await client.patch(
        f"/avatars/{created['id']}",
        json={"name": "Edição obsoleta", "expected_version": created["version"]},
    )
    assert stale.status_code == 409

    current = (await client.get(f"/avatars/{created['id']}")).json()
    assert current["name"] == "Primeira edição"
    assert current["version"] == 2


async def test_valid_status_transition_advances_one_step(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-status-valido")
    created = (
        await client.post("/avatars", json={"name": "Avançável", "slug": slug, "metadata": {}})
    ).json()
    assert created["status"] == "draft"

    response = await client.patch(
        f"/avatars/{created['id']}",
        json={"status": "identity_locked", "expected_version": created["version"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "identity_locked"
    assert body["version"] == 2


async def test_invalid_status_transition_returns_409(client: httpx.AsyncClient) -> None:
    """A máquina de estados é linear (seção 12 do prompt-mestre): nenhum salto de etapas
    é permitido nesta fundação."""
    slug = _unique_slug("teste-status-invalido")
    created = (
        await client.post("/avatars", json={"name": "Pulador", "slug": slug, "metadata": {}})
    ).json()

    response = await client.patch(
        f"/avatars/{created['id']}",
        json={"status": "production_ready", "expected_version": created["version"]},
    )
    assert response.status_code == 409


async def test_update_nonexistent_avatar_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.patch(
        f"/avatars/{uuid.uuid4()}", json={"name": "Fantasma", "expected_version": 1}
    )
    assert response.status_code == 404


async def test_delete_draft_avatar(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-delete")
    created = (
        await client.post("/avatars", json={"name": "Temporário", "slug": slug, "metadata": {}})
    ).json()

    deleted = await client.delete(
        f"/avatars/{created['id']}", params={"expected_version": created["version"]}
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/avatars/{created['id']}")).status_code == 404


async def test_delete_non_draft_avatar_is_blocked(client: httpx.AsyncClient) -> None:
    slug = _unique_slug("teste-delete-bloqueado")
    created = (
        await client.post("/avatars", json={"name": "Em uso", "slug": slug, "metadata": {}})
    ).json()
    advanced = (
        await client.patch(
            f"/avatars/{created['id']}",
            json={"status": "identity_locked", "expected_version": created["version"]},
        )
    ).json()

    response = await client.delete(
        f"/avatars/{created['id']}", params={"expected_version": advanced["version"]}
    )
    assert response.status_code == 409


async def test_avatar_survives_simulated_process_restart(client: httpx.AsyncClient) -> None:
    """Prova exigida pela missão: 'reinicie API -> dado continua existindo'. Sem um
    processo uvicorn de verdade para matar neste teste, simulamos o efeito que importa —
    descartamos o engine/sessionmaker assíncrono cacheado (lru_cache) e deixamos a próxima
    requisição recriar o pool do zero, exatamente como acontece a cada restart real do
    processo — e confirmamos que os dados gravados antes continuam lá."""
    from dhf_shared.db import get_engine, get_sessionmaker

    slug = _unique_slug("teste-restart")
    created = (
        await client.post(
            "/avatars", json={"name": "Sobrevivente", "slug": slug, "metadata": {"antes": True}}
        )
    ).json()
    updated = (
        await client.patch(
            f"/avatars/{created['id']}",
            json={"status": "identity_locked", "expected_version": created["version"]},
        )
    ).json()
    assert updated["version"] == 2

    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    response = await client.get(f"/avatars/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["status"] == "identity_locked"
    assert body["version"] == 2
    assert body["metadata"] == {"antes": True}
