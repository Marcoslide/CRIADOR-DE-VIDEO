"""Fixtures compartilhadas por `tests/api/` — hoje só o dublê de Storage usado pelos
testes do Avatar Factory Control Plane (upload de referências)."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dhf_schemas.storage import StorageManifestEntry


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
