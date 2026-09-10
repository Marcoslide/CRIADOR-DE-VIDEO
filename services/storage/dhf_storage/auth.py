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

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from dhf_storage.config import GoogleDriveSettings

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


class CredentialLoadError(Exception):
    """Uma fonte de credencial foi configurada, mas o conteúdo é inválido."""


def load_credentials(settings: GoogleDriveSettings) -> service_account.Credentials | None:
    """None (não exceção) quando nenhuma fonte de credencial está configurada — esse é o
    caminho normal para NOT_CONFIGURED. CredentialLoadError é para quando uma fonte *foi*
    configurada mas está quebrada (JSON inválido, arquivo ausente/corrompido) — isso é
    ERROR, não NOT_CONFIGURED, porque alguém tentou configurar e falhou.
    """
    if settings.google_drive_service_account_json.strip():
        try:
            info = json.loads(settings.google_drive_service_account_json)
        except json.JSONDecodeError as exc:
            raise CredentialLoadError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON não é um JSON válido"
            ) from exc
        try:
            return service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        except (ValueError, KeyError) as exc:
            raise CredentialLoadError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON não contém uma service account válida"
            ) from exc

    if settings.google_drive_service_account_file.strip():
        try:
            return service_account.Credentials.from_service_account_file(
                settings.google_drive_service_account_file, scopes=DRIVE_SCOPES
            )
        except (OSError, ValueError) as exc:
            raise CredentialLoadError(
                "não foi possível carregar o arquivo indicado por GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE"
            ) from exc

    return None


def ensure_fresh_token(credentials: service_account.Credentials) -> str:
    """Síncrono — chamar via asyncio.to_thread. Renova o token só se necessário."""
    if not credentials.valid:
        credentials.refresh(GoogleAuthRequest())
    return credentials.token
