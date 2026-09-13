"""Carregamento de credenciais e obtenção de access token para a Drive API v3.

`google-auth` não tem variante assíncrona — usado só para ler/validar/renovar a credencial
(operação local ou uma chamada de rede curta ao endpoint de token do Google), nunca para
falar com a Drive API em si (isso é `google_drive.py`, via `httpx` assíncrono). As funções
daqui são síncronas de propósito; quem chama a partir de código assíncrono usa
`asyncio.to_thread`.

Regra de segurança: nunca logar `settings.google_drive_service_account_json`, o conteúdo do
arquivo de credencial, nem `credentials.token`. Só o "acontecimento" (ex.: "carreguei uma
credencial de arquivo") e erros com mensagem genérica.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dhf_schemas.storage import StorageAuthExpiredError
from google.auth.credentials import Credentials
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import credentials as oauth_user_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow

from dhf_storage.config import GoogleDriveAuthMode, GoogleDriveSettings

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class CredentialLoadError(Exception):
    """Uma fonte de credencial foi configurada, mas o conteúdo é inválido."""


@dataclass(frozen=True)
class LoadedCredentials:
    credentials: Credentials
    mode: GoogleDriveAuthMode


def _configured_sources(settings: GoogleDriveSettings) -> tuple[list[str], list[str]]:
    service_account_sources = [
        name
        for name, value in (
            ("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", settings.google_drive_service_account_json),
            ("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", settings.google_drive_service_account_file),
        )
        if value.strip()
    ]
    oauth_user_sources = [
        name
        for name, value in (
            ("GOOGLE_DRIVE_OAUTH_USER_JSON", settings.google_drive_oauth_user_json),
            ("GOOGLE_DRIVE_OAUTH_USER_FILE", settings.google_drive_oauth_user_file),
        )
        if value.strip()
    ]
    return service_account_sources, oauth_user_sources


def resolve_auth_mode(settings: GoogleDriveSettings) -> GoogleDriveAuthMode | None:
    service_account_sources, oauth_user_sources = _configured_sources(settings)

    if len(service_account_sources) > 1:
        raise CredentialLoadError("configure apenas uma fonte de Service Account: JSON ou FILE")
    if len(oauth_user_sources) > 1:
        raise CredentialLoadError("configure apenas uma fonte de OAuth User: JSON ou FILE")
    if service_account_sources and oauth_user_sources:
        raise CredentialLoadError(
            "fontes de Service Account e OAuth User não podem ser usadas ao mesmo tempo"
        )

    detected: GoogleDriveAuthMode | None = None
    if service_account_sources:
        detected = GoogleDriveAuthMode.SERVICE_ACCOUNT
    elif oauth_user_sources:
        detected = GoogleDriveAuthMode.OAUTH_USER

    configured = settings.google_drive_auth_mode
    if configured is GoogleDriveAuthMode.AUTO:
        return detected
    if detected is None:
        return None
    if configured is not detected:
        raise CredentialLoadError(
            f"GOOGLE_DRIVE_AUTH_MODE={configured.value} diverge da fonte configurada"
        )
    return configured


def _parse_json_source(raw: str, variable_name: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CredentialLoadError(f"{variable_name} não é um JSON válido") from exc
    if not isinstance(value, dict):
        raise CredentialLoadError(f"{variable_name} precisa conter um objeto JSON")
    return value


def _read_json_file(path_text: str, variable_name: str) -> dict:
    try:
        return _parse_json_source(Path(path_text).read_text(), variable_name)
    except OSError as exc:
        raise CredentialLoadError(
            f"não foi possível carregar o arquivo indicado por {variable_name}"
        ) from exc


def _load_service_account(settings: GoogleDriveSettings) -> service_account.Credentials:
    if settings.google_drive_service_account_json.strip():
        info = _parse_json_source(
            settings.google_drive_service_account_json, "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"
        )
        try:
            return service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        except (ValueError, KeyError) as exc:
            raise CredentialLoadError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON não contém uma service account válida"
            ) from exc

    try:
        return service_account.Credentials.from_service_account_file(
            settings.google_drive_service_account_file, scopes=DRIVE_SCOPES
        )
    except (OSError, ValueError) as exc:
        raise CredentialLoadError(
            "não foi possível carregar o arquivo indicado por GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE"
        ) from exc


def _load_oauth_user(settings: GoogleDriveSettings) -> oauth_user_credentials.Credentials:
    variable_name = (
        "GOOGLE_DRIVE_OAUTH_USER_JSON"
        if settings.google_drive_oauth_user_json.strip()
        else "GOOGLE_DRIVE_OAUTH_USER_FILE"
    )
    info = (
        _parse_json_source(settings.google_drive_oauth_user_json, variable_name)
        if settings.google_drive_oauth_user_json.strip()
        else _read_json_file(settings.google_drive_oauth_user_file, variable_name)
    )
    missing = sorted(
        field for field in ("client_id", "client_secret", "refresh_token") if not info.get(field)
    )
    if missing:
        raise CredentialLoadError(
            f"{variable_name} não contém uma credencial OAuth User durável; faltam: "
            + ", ".join(missing)
        )
    try:
        return oauth_user_credentials.Credentials.from_authorized_user_info(
            info, scopes=DRIVE_SCOPES
        )
    except (ValueError, KeyError) as exc:
        raise CredentialLoadError(
            f"{variable_name} não contém uma credencial OAuth User válida"
        ) from exc


def load_credentials(settings: GoogleDriveSettings) -> LoadedCredentials | None:
    """None (não exceção) quando nenhuma fonte de credencial está configurada — esse é o
    caminho normal para NOT_CONFIGURED. CredentialLoadError é para quando uma fonte *foi*
    configurada mas está quebrada (JSON inválido, arquivo ausente/corrompido) — isso é
    ERROR, não NOT_CONFIGURED, porque alguém tentou configurar e falhou.
    """
    mode = resolve_auth_mode(settings)
    if mode is None:
        return None
    if mode is GoogleDriveAuthMode.SERVICE_ACCOUNT:
        credentials = _load_service_account(settings)
    else:
        credentials = _load_oauth_user(settings)
    return LoadedCredentials(credentials=credentials, mode=mode)


def ensure_fresh_token(credentials: Credentials) -> str:
    """Síncrono — chamar via asyncio.to_thread. Renova o token só se necessário."""
    if not credentials.valid:
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            if _is_invalid_grant(exc):
                raise StorageAuthExpiredError(
                    "A autorização do Google Drive expirou ou foi revogada; "
                    "execute o bootstrap OAuth novamente."
                ) from exc
            raise
    if not credentials.token:
        raise CredentialLoadError("Google não retornou access token após o refresh")
    return credentials.token


def _is_invalid_grant(exc: RefreshError) -> bool:
    for value in exc.args:
        if isinstance(value, dict) and value.get("error") == "invalid_grant":
            return True
        if isinstance(value, str) and "invalid_grant" in value.lower():
            return True
    return False


def _installed_app_flow(
    *,
    client_secrets_file: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> InstalledAppFlow:
    if client_secrets_file.strip():
        client_path = Path(client_secrets_file).expanduser().resolve()
        if not client_path.is_file():
            raise CredentialLoadError("arquivo de OAuth Client não encontrado")
        try:
            return InstalledAppFlow.from_client_secrets_file(str(client_path), scopes=DRIVE_SCOPES)
        except (OSError, ValueError) as exc:
            raise CredentialLoadError("OAuth Client Desktop inválido") from exc

    if not client_id.strip() or not client_secret.strip():
        raise CredentialLoadError(
            "informe um OAuth Client Desktop por arquivo ou por CLIENT_ID/CLIENT_SECRET"
        )
    return InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=DRIVE_SCOPES,
    )


def authorize_oauth_user(
    token_file: str,
    *,
    client_secrets_file: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> Path:
    """Executa OAuth Desktop App por loopback e grava a credencial durável com modo 0600.

    Esta função é propositalmente síncrona e só é usada pelo comando CLI interativo.
    """
    try:
        flow = _installed_app_flow(
            client_secrets_file=client_secrets_file,
            client_id=client_id,
            client_secret=client_secret,
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
            authorization_prompt_message=(
                "Abra esta URL no navegador se ele não abrir automaticamente:\n{url}"
            ),
            success_message=(
                "Autorização concluída. Você pode fechar esta aba e voltar ao terminal."
            ),
        )
    except (OSError, ValueError) as exc:
        raise CredentialLoadError("não foi possível concluir o fluxo OAuth User") from exc

    if not credentials.refresh_token:
        raise CredentialLoadError(
            "Google não retornou refresh token; revogue o acesso anterior e autorize novamente"
        )

    destination = Path(token_file).expanduser().resolve()
    client_path = (
        Path(client_secrets_file).expanduser().resolve() if client_secrets_file.strip() else None
    )
    if destination == client_path:
        raise CredentialLoadError("arquivo de token deve ser diferente do OAuth Client")
    parent_already_existed = destination.parent.exists()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not parent_already_existed:
        os.chmod(destination.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(credentials.to_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        os.chmod(destination, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass
    return destination
