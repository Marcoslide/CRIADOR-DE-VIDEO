"""Fixtures dos testes de Storage.

`fake_service_account_file` gera uma credencial sintaticamente válida (chave RSA real,
gerada na hora) mas não registrada em lugar nenhum — usada para exercitar o carregamento
real de credencial sem depender de segredo nenhum. Os testes *unitários* além disso
substituem `_get_token` para nunca tocar a rede (nem para renovar token); os testes de
*integração* (`test_google_drive_integration.py`) usam uma credencial real de verdade e são
pulados quando ela não está configurada.
"""

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dhf_storage.config import GoogleDriveSettings
from dhf_storage.google_drive import GoogleDriveStorageProvider


@pytest.fixture
def fake_service_account_file(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    service_account_info = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": pem,
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    path = tmp_path / "fake_service_account.json"
    path.write_text(json.dumps(service_account_info))
    return str(path)


@pytest.fixture
def unit_settings(fake_service_account_file) -> GoogleDriveSettings:
    return GoogleDriveSettings(
        google_drive_service_account_file=fake_service_account_file,
        google_drive_root_folder_id="root-folder-id",
        google_drive_max_retries=1,
        google_drive_retry_base_delay_s=0.001,
        google_drive_status_cache_ttl_s=0,
    )


@pytest.fixture
async def provider(unit_settings, monkeypatch):
    p = GoogleDriveStorageProvider(unit_settings)

    async def _fake_token():
        return "fake-access-token"

    monkeypatch.setattr(p, "_get_token", _fake_token)
    yield p
    await p.aclose()


@pytest.fixture
def unconfigured_provider():
    settings = GoogleDriveSettings(
        google_drive_service_account_json="",
        google_drive_service_account_file="",
    )
    return GoogleDriveStorageProvider(settings)
