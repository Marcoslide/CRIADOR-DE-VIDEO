"""Carregamento de credencial — sem rede: só parsing/validação local."""

import json
import stat

import pytest
from dhf_schemas.storage import StorageAuthExpiredError
from dhf_storage import auth
from dhf_storage.auth import (
    DRIVE_SCOPES,
    CredentialLoadError,
    authorize_oauth_user,
    ensure_fresh_token,
    load_credentials,
)
from dhf_storage.config import GoogleDriveAuthMode, GoogleDriveSettings
from google.auth.exceptions import RefreshError
from pydantic import ValidationError


def test_no_credential_source_returns_none() -> None:
    settings = GoogleDriveSettings(
        google_drive_service_account_json="",
        google_drive_service_account_file="",
        google_drive_oauth_user_json="",
        google_drive_oauth_user_file="",
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
    assert credentials.mode is GoogleDriveAuthMode.SERVICE_ACCOUNT
    assert (
        credentials.credentials.service_account_email == "test@test-project.iam.gserviceaccount.com"
    )


def test_has_credential_source_true_with_file(fake_service_account_file) -> None:
    settings = GoogleDriveSettings(google_drive_service_account_file=fake_service_account_file)
    assert settings.has_credential_source is True


def test_upload_chunk_must_be_positive_multiple_of_256_kib() -> None:
    with pytest.raises(ValidationError, match="256 KiB"):
        GoogleDriveSettings(google_drive_upload_chunk_size_bytes=1000)


def test_retry_count_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="não pode ser negativo"):
        GoogleDriveSettings(google_drive_max_retries=-1)


def test_v1_uses_drive_file_scope_only() -> None:
    assert DRIVE_SCOPES == ["https://www.googleapis.com/auth/drive.file"]


def test_oauth_client_id_and_secret_must_be_configured_together() -> None:
    with pytest.raises(ValidationError, match="devem ser configurados juntos"):
        GoogleDriveSettings(google_drive_client_id="client-id")


def test_valid_oauth_user_file_loads(fake_oauth_user_file) -> None:
    settings = GoogleDriveSettings(
        google_drive_auth_mode="oauth_user",
        google_drive_oauth_user_file=fake_oauth_user_file,
    )
    loaded = load_credentials(settings)
    assert loaded is not None
    assert loaded.mode is GoogleDriveAuthMode.OAUTH_USER
    assert loaded.credentials.refresh_token == "test-refresh-token"


def test_oauth_user_requires_refresh_token(tmp_path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "client_id": "id",
                "client_secret": "secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    )
    settings = GoogleDriveSettings(google_drive_oauth_user_file=str(token_file))
    with pytest.raises(CredentialLoadError, match="refresh_token"):
        load_credentials(settings)


def test_rejects_service_account_and_oauth_user_together(
    fake_service_account_file, fake_oauth_user_file
) -> None:
    settings = GoogleDriveSettings(
        google_drive_service_account_file=fake_service_account_file,
        google_drive_oauth_user_file=fake_oauth_user_file,
    )
    with pytest.raises(CredentialLoadError, match="não podem ser usadas ao mesmo tempo"):
        load_credentials(settings)


def test_rejects_mode_that_disagrees_with_source(fake_oauth_user_file) -> None:
    settings = GoogleDriveSettings(
        google_drive_auth_mode="service_account",
        google_drive_oauth_user_file=fake_oauth_user_file,
    )
    with pytest.raises(CredentialLoadError, match="diverge"):
        load_credentials(settings)


def test_authorize_oauth_user_writes_private_durable_token(tmp_path, monkeypatch) -> None:
    client_file = tmp_path / "client.json"
    client_file.write_text('{"installed": {}}')
    destination = tmp_path / "secrets" / "oauth-user.json"

    class FakeCredentials:
        refresh_token = "refresh-token"

        @staticmethod
        def to_json() -> str:
            return '{"refresh_token":"refresh-token"}'

    class FakeFlow:
        def run_local_server(self, **kwargs):
            assert kwargs["host"] == "127.0.0.1"
            assert kwargs["port"] == 0
            assert kwargs["access_type"] == "offline"
            assert kwargs["prompt"] == "consent"
            return FakeCredentials()

    monkeypatch.setattr(
        auth.InstalledAppFlow,
        "from_client_secrets_file",
        lambda path, scopes: FakeFlow(),
    )

    result = authorize_oauth_user(str(destination), client_secrets_file=str(client_file))

    assert result == destination.resolve()
    assert destination.read_text() == '{"refresh_token":"refresh-token"}'
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700


def test_authorize_accepts_client_id_and_secret_from_environment(tmp_path, monkeypatch) -> None:
    destination = tmp_path / "oauth-user.json"

    class FakeCredentials:
        refresh_token = "refresh-token"

        @staticmethod
        def to_json() -> str:
            return '{"refresh_token":"refresh-token"}'

    class FakeFlow:
        def run_local_server(self, **kwargs):
            return FakeCredentials()

    def fake_from_client_config(config, scopes):
        assert config["installed"]["client_id"] == "client-id"
        assert config["installed"]["client_secret"] == "client-secret"
        assert scopes == ["https://www.googleapis.com/auth/drive.file"]
        return FakeFlow()

    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_config", fake_from_client_config)

    authorize_oauth_user(str(destination), client_id="client-id", client_secret="client-secret")

    assert destination.exists()


def test_invalid_grant_becomes_auth_expired_without_retry() -> None:
    class ExpiredCredentials:
        valid = False
        token = None
        refresh_calls = 0

        def refresh(self, request):
            self.refresh_calls += 1
            raise RefreshError("invalid_grant: token expired")

    credentials = ExpiredCredentials()
    with pytest.raises(StorageAuthExpiredError):
        ensure_fresh_token(credentials)
    assert credentials.refresh_calls == 1
