"""Fixtures e helpers compartilhados por `tests/api/`.

`FakeStorageProvider`/`fake_storage_provider`: dublê de Storage usado pelos testes do
Avatar Factory Control Plane (upload de referências).

`advance_to_identity_locked`/`complete_full_multiview_and_approve`: fixtures-factory
(devolvem uma função async) que existem porque a correção P1-1 proíbe usar o PATCH
genérico (`_force_status`, removido) para pular etapas do pipeline — qualquer teste que
precise de um avatar além de DRAFT agora precisa passar pelo fluxo real (Identity Lock
aprovado -> gate identity aprovado -> ...), exatamente como a API exige em produção.
Expostas como fixtures (não funções soltas importadas) porque `tests/` não tem
`__init__.py` — `conftest.py` não é importável como módulo Python normal, só carregável
pelo mecanismo de plugin do pytest."""

from __future__ import annotations

import hashlib
import io
import mimetypes
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from dhf_avatar_factory.enums import EXPRESSION_CATEGORIES, REQUIRED_ANGLES, SPECIALIZED_CATEGORIES
from dhf_schemas.storage import StorageManifestEntry
from PIL import Image

AdvanceToIdentityLocked = Callable[[httpx.AsyncClient, dict], Awaitable[dict]]
CompleteFullMultiview = Callable[[httpx.AsyncClient, dict], Awaitable[dict]]
UploadFullMultiviewSet = Callable[[httpx.AsyncClient, str], Awaitable[None]]


class FakeStorageProvider:
    """Satisfaz só os métodos de `StorageProvider` que o Avatar Factory realmente chama
    (`upload`/`download`) — não é um teste do Google Drive em si (isso já é
    responsabilidade de `tests/storage/`), é um dublê da fronteira externa para testar
    NOSSA lógica de verdade (QA, gates, transições) sem precisar de credencial real."""

    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    async def upload(self, local_path: str, remote_path: str) -> StorageManifestEntry:
        data = Path(local_path).read_bytes()
        self.uploaded[remote_path] = data
        mime_type, _ = mimetypes.guess_type(remote_path)
        return StorageManifestEntry(
            remote_path=remote_path,
            provider_id=f"fake-{hashlib.sha1(remote_path.encode()).hexdigest()[:16]}",
            size_bytes=len(data),
            mime_type=mime_type or "application/octet-stream",
            checksum=hashlib.md5(data).hexdigest(),
            version=None,
            modified_at=datetime.now(UTC),
            web_view_url=None,
        )

    async def download(self, remote_path: str, local_path: str) -> None:
        Path(local_path).write_bytes(self.uploaded[remote_path])


@pytest.fixture
def fake_storage_provider(monkeypatch: pytest.MonkeyPatch) -> FakeStorageProvider:
    fake = FakeStorageProvider()
    monkeypatch.setattr("dhf_avatar_factory.service.get_storage_provider", lambda: fake)
    return fake


def photo_bytes(seed: int = 0) -> bytes:
    """Ruído por pixel (não cor sólida) — passa nos checks determinísticos de verdade,
    inclusive o heurístico de blur (ver tests/avatar_factory/test_qa_checks.py)."""
    rng = random.Random(seed)
    image = Image.new("RGB", (640, 640))
    pixels = image.load()
    for x in range(640):
        for y in range(640):
            value = rng.randint(20, 235)
            pixels[x, y] = (value, value, value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def advance_to_identity_locked() -> AdvanceToIdentityLocked:
    async def _advance(client: httpx.AsyncClient, avatar: dict) -> dict:
        """Sobe um avatar em DRAFT até IDENTITY_LOCKED pelo fluxo REAL — cria e aprova um
        Identity Lock, depois aprova o gate 'identity'. Nunca usa PATCH genérico para
        isso (P1-1: PATCH DRAFT->IDENTITY_LOCKED é bloqueado por design, mesmo em
        teste)."""
        draft = (
            await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
        ).json()
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock/approve",
            json={"expected_version": draft["version"], "approved_by": "marcos"},
        )
        response = await client.post(
            f"/avatars/{avatar['id']}/quality-gates/identity/approve",
            json={"expected_version": avatar["version"], "actor": "marcos"},
        )
        assert response.status_code == 200, response.text
        updated_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
        assert updated_avatar["status"] == "identity_locked"
        return updated_avatar

    return _advance


async def _upload_and_approve(
    client: httpx.AsyncClient,
    avatar_id: str,
    *,
    category: str,
    angle: int | None,
    seed: int,
) -> None:
    data = {"category": category}
    if angle is not None:
        data["angle"] = str(angle)
    files = {"file": ("ref.png", photo_bytes(seed), "image/png")}
    uploaded = (
        await client.post(f"/avatars/{avatar_id}/references", data=data, files=files)
    ).json()
    approved = await client.post(
        f"/avatars/{avatar_id}/references/{uploaded['id']}/approve",
        json={"expected_version": uploaded["version"], "reviewed_by": "marcos"},
    )
    assert approved.status_code == 200, approved.text


@pytest.fixture
def upload_and_approve_full_multiview_set() -> UploadFullMultiviewSet:
    async def _upload_all(client: httpx.AsyncClient, avatar_id: str) -> None:
        """Sobe TODOS os 108 ângulos 360° + 32 especializadas + 19 expressões e aprova
        cada um — deixa a evidência 100% satisfeita SEM aprovar o gate multiview em si
        (usado tanto por `complete_full_multiview_and_approve` quanto por testes que
        precisam de evidência completa para correr uma corrida real contra o approve)."""
        seed = 0
        for category in ("head_360", "half_body_360", "full_body_360"):
            for angle in REQUIRED_ANGLES:
                seed += 1
                await _upload_and_approve(
                    client, avatar_id, category=category, angle=angle, seed=seed
                )
        for category in SPECIALIZED_CATEGORIES:
            seed += 1
            await _upload_and_approve(
                client, avatar_id, category=category.value, angle=None, seed=seed
            )
        for category in EXPRESSION_CATEGORIES:
            seed += 1
            await _upload_and_approve(
                client, avatar_id, category=category.value, angle=None, seed=seed
            )

    return _upload_all


@pytest.fixture
def complete_full_multiview_and_approve(
    upload_and_approve_full_multiview_set: UploadFullMultiviewSet,
) -> CompleteFullMultiview:
    async def _complete(client: httpx.AsyncClient, avatar: dict) -> dict:
        """Avatar já em MULTIVIEW_IN_PROGRESS -> sobe o conjunto completo de evidência e
        aprova o gate multiview de verdade. Sem isso não existe outro jeito de alcançar
        MULTIVIEW_APPROVED (P1-1) — é deliberadamente pesado, exatamente o que "sem
        bypass" custa."""
        await upload_and_approve_full_multiview_set(client, avatar["id"])

        response = await client.post(
            f"/avatars/{avatar['id']}/quality-gates/multiview/approve",
            json={"expected_version": avatar["version"], "actor": "marcos"},
        )
        assert response.status_code == 200, response.text
        updated_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
        assert updated_avatar["status"] == "multiview_approved"
        return updated_avatar

    return _complete
