"""Testes de integração REAIS contra o Google Drive — sem mocks.

Só rodam quando uma credencial de verdade está configurada (`GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
ou `_FILE`, apontando para uma service account com acesso à pasta raiz oficial). Sem
credencial, `pytest.skip` com um motivo claro — nunca um "passed" enganoso.

Regra dura seguida à risca aqui: nada além de `02_SISTEMA_STORAGE/_tmp/` é tocado. O teste
de proteção contra exclusão permanente nem chega a fazer uma chamada de rede (a guarda roda
antes da resolução de caminho — ver GoogleDriveStorageProvider.delete()), então é seguro
rodar mesmo contra o Drive de produção.
"""

import hashlib
import os
import uuid

import pytest
from dhf_schemas.storage import StorageConnectionStatus, StoragePermanentDeleteBlockedError
from dhf_storage.config import get_google_drive_settings
from dhf_storage.google_drive import GoogleDriveStorageProvider

pytestmark = pytest.mark.integration


@pytest.fixture
async def real_provider():
    settings = get_google_drive_settings()
    if not settings.has_credential_source:
        pytest.skip(
            "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON/_FILE não configurados — teste de "
            "integração real do Google Drive pulado (ver docs/STORAGE_GOOGLE_DRIVE.md)."
        )
    provider = GoogleDriveStorageProvider(settings)
    yield provider
    await provider.aclose()


async def test_real_connection_and_official_tree(real_provider: GoogleDriveStorageProvider) -> None:
    status = await real_provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.CONNECTED, (
        f"esperado CONNECTED, obtido {status.status.value}: {status.detail} (árvore: {status.tree})"
    )
    assert status.tree is not None
    assert status.tree.missing == []


async def test_real_upload_download_roundtrip_and_delete(
    real_provider: GoogleDriveStorageProvider, tmp_path
) -> None:
    content = os.urandom(4096)
    local_upload = tmp_path / "upload.bin"
    local_upload.write_bytes(content)
    local_download = tmp_path / "download.bin"

    remote_path = f"02_SISTEMA_STORAGE/_tmp/dhf-integration-test-{uuid.uuid4().hex}.bin"

    try:
        # upload real
        entry = await real_provider.upload(str(local_upload), remote_path)
        assert entry.size_bytes == len(content)
        assert entry.checksum == hashlib.md5(content).hexdigest()  # noqa: S324 - md5 é o algoritmo do próprio Drive

        # leitura real (exists + metadata)
        assert await real_provider.exists(remote_path) is True
        metadata = await real_provider.get_metadata(remote_path)
        assert metadata.provider_id == entry.provider_id
        assert metadata.size_bytes == len(content)

        # download real — precisa ser byte-idêntico ao enviado
        await real_provider.download(remote_path, str(local_download))
        downloaded = local_download.read_bytes()
        assert downloaded == content
        assert hashlib.md5(downloaded).hexdigest() == entry.checksum  # noqa: S324

        # remoção real de um arquivo temporário (dentro da área de scratch)
        await real_provider.delete(remote_path)
        assert await real_provider.exists(remote_path) is False
    finally:
        # limpeza best-effort mesmo se alguma asserção acima falhar
        try:
            if await real_provider.exists(remote_path):
                await real_provider.delete(remote_path, allow_permanent=True)
        except Exception:  # noqa: BLE001 - limpeza de teste, nunca deve mascarar a falha original
            pass


async def test_real_permanent_delete_is_blocked_outside_scratch(
    real_provider: GoogleDriveStorageProvider,
) -> None:
    """A guarda roda antes de qualquer chamada de rede (ver delete()) — seguro rodar mesmo
    que este caminho não exista e mesmo contra o Drive real/de produção."""
    with pytest.raises(StoragePermanentDeleteBlockedError):
        await real_provider.delete(
            f"03_AVATAR_IDENTITY_FOTOS/dhf-integration-test-guard-{uuid.uuid4().hex}.bin"
        )
