"""Carregamento de credencial — sem rede: só parsing/validação local."""

import pytest
from dhf_storage.auth import CredentialLoadError, load_credentials
from dhf_storage.config import GoogleDriveSettings


def test_no_credential_source_returns_none() -> None:
    settings = GoogleDriveSettings(
        google_drive_service_account_json="", google_drive_service_account_file=""
    )
    assert settings.has_credential_source is False
    assert load_credentials(settings) is None


def test_invalid_json_raises_credential_load_error() -> None:
    settings = GoogleDriveSettings(google_drive_service_account_json="{not valid json")
    with pytest.raises(CredentialLoadError, match="JSON válido"):
        load_credentials(settings)


def test_json_missing_required_fields_raises_credential_load_error() -> None:
    settings = GoogleDriveSettings(google_drive_service_account_json='{"type": "service_account"}')
    with pytest.raises(CredentialLoadError):
        load_credentials(settings)


def test_missing_file_raises_credential_load_error(tmp_path) -> None:
    settings = GoogleDriveSettings(
        google_drive_service_account_file=str(tmp_path / "nao-existe.json")
    )
    with pytest.raises(CredentialLoadError, match="GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE"):
        load_credentials(settings)


def test_valid_fake_service_account_file_loads(fake_service_account_file) -> None:
    settings = GoogleDriveSettings(google_drive_service_account_file=fake_service_account_file)
    credentials = load_credentials(settings)
    assert credentials is not None
    assert credentials.service_account_email == "test@test-project.iam.gserviceaccount.com"


def test_has_credential_source_true_with_file(fake_service_account_file) -> None:
    settings = GoogleDriveSettings(google_drive_service_account_file=fake_service_account_file)
    assert settings.has_credential_source is True
