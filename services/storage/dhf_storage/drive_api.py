"""Primitivas REST de baixo nível contra a Google Drive API v3.

Funções puras (recebem `httpx.AsyncClient` + token de acesso, não guardam estado). Cada
chamada de rede passa por `with_retry`. `google_drive.py` compõe estas primitivas para
implementar `StorageProvider`.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from dhf_storage.retry import RETRYABLE_STATUS, RetryExhaustedError, with_retry

FILES_URL = "https://www.googleapis.com/drive/v3/files"
ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
METADATA_FIELDS = (
    "id,name,size,mimeType,md5Checksum,modifiedTime,webViewLink,parents,driveId,trashed,"
    "appProperties"
)

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
UPLOAD_CHUNK_GRANULARITY = 256 * 1024
_RANGE_RE = re.compile(r"^bytes=0-(\d+)$")

ChunkReader = Callable[[int, int], Awaitable[bytes]]


class ResumableUploadSessionExpiredError(RuntimeError):
    """A sessão resumable expirou e precisa ser iniciada novamente."""


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def get_storage_quota(
    client: httpx.AsyncClient,
    token: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, int | None]:
    """Retorna somente os números de cota necessários ao health check.

    ``about.get`` aceita ``drive.file``. Ausência de ``limit`` significa armazenamento
    ilimitado/gerenciado e, portanto, não deve ser interpretada como zero.
    """

    async def _call():
        response = await client.get(
            ABOUT_URL,
            params={"fields": "storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"},
            headers=_auth_headers(token),
        )
        response.raise_for_status()
        return response.json()

    payload = await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )
    raw = payload.get("storageQuota", {})

    def _integer(name: str) -> int | None:
        value = raw.get(name)
        return int(value) if value is not None else None

    return {
        "limit": _integer("limit"),
        "usage": _integer("usage"),
        "usage_in_drive": _integer("usageInDrive"),
        "usage_in_drive_trash": _integer("usageInDriveTrash"),
    }


async def list_children(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    *,
    name: str | None = None,
    folders_only: bool = False,
    shared_drive_id: str | None = None,
    app_properties: dict[str, str] | None = None,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> list[dict[str, Any]]:
    """Lista (com paginação completa) os filhos não-lixeira de `parent_id`, opcionalmente
    filtrando por nome exato e/ou só pastas."""
    query = f"'{parent_id}' in parents and trashed = false"
    if name is not None:
        query += f" and name = '{_escape_query_value(name)}'"
    if folders_only:
        query += f" and mimeType = '{FOLDER_MIME_TYPE}'"
    if app_properties:
        for key, value in sorted(app_properties.items()):
            query += (
                " and appProperties has { "
                f"key = '{_escape_query_value(key)}' and "
                f"value = '{_escape_query_value(value)}' }}"
            )

    results: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "q": query,
            "fields": f"nextPageToken,files({METADATA_FIELDS})",
            "pageSize": 200,
            "spaces": "drive",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if shared_drive_id:
            params.update(
                {
                    "corpora": "drive",
                    "driveId": shared_drive_id,
                }
            )
        if page_token:
            params["pageToken"] = page_token

        async def _call(p=params):
            response = await client.get(FILES_URL, params=p, headers=_auth_headers(token))
            response.raise_for_status()
            return response.json()

        payload = await with_retry(
            _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
        )
        results.extend(payload.get("files", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return results


async def create_folder(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    name: str,
    *,
    app_properties: dict[str, str] | None = None,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.post(
            FILES_URL,
            params={"fields": METADATA_FIELDS, "supportsAllDrives": "true"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={
                "name": name,
                "mimeType": FOLDER_MIME_TYPE,
                "parents": [parent_id],
                **({"appProperties": app_properties} if app_properties else {}),
            },
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def initiate_resumable_upload(
    client: httpx.AsyncClient,
    token: str,
    parent_id: str,
    name: str,
    mime_type: str,
    size_bytes: int,
    *,
    existing_file_id: str | None = None,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> str:
    """Retorna a Location (URL da sessão de upload). Se `existing_file_id` for informado,
    atualiza o conteúdo desse arquivo (PATCH) em vez de criar um novo (POST) — é assim que
    upload() evita duplicar arquivos quando o remote_path já existe."""
    if existing_file_id:
        method, url = "PATCH", f"{UPLOAD_URL}/{existing_file_id}"
    else:
        method, url = "POST", UPLOAD_URL

    async def _call():
        response = await client.request(
            method,
            url,
            params={
                "uploadType": "resumable",
                "fields": METADATA_FIELDS,
                "supportsAllDrives": "true",
            },
            headers={
                **_auth_headers(token),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(size_bytes),
            },
            json={"name": name} if existing_file_id else {"name": name, "parents": [parent_id]},
        )
        response.raise_for_status()
        return response

    response = await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )
    location = response.headers.get("Location")
    if not location:
        raise RuntimeError("Drive não retornou Location para a sessão de upload resumable")
    return location


def _next_upload_offset(response: httpx.Response) -> int:
    range_header = response.headers.get("Range")
    if not range_header:
        return 0
    match = _RANGE_RE.fullmatch(range_header.strip())
    if not match:
        raise RuntimeError("Drive retornou Range inválido durante upload resumable")
    return int(match.group(1)) + 1


def _google_error_reason(response: httpx.Response) -> str | None:
    """Extrai apenas o código estável do erro, sem logar corpo, URL ou credenciais."""
    try:
        payload = response.json()
        errors = payload.get("error", {}).get("errors", [])
        reason = errors[0].get("reason") if errors else None
        return str(reason) if reason else None
    except (AttributeError, IndexError, TypeError, ValueError):
        return None


async def query_resumable_upload_status(
    client: httpx.AsyncClient,
    token: str,
    upload_url: str,
    size_bytes: int,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> httpx.Response:
    """Consulta quantos bytes o Drive já confirmou para uma sessão resumable."""

    async def _call():
        response = await client.put(
            upload_url,
            content=b"",
            headers={
                **_auth_headers(token),
                "Content-Length": "0",
                "Content-Range": f"bytes */{size_bytes}",
            },
        )
        if response.status_code in {200, 201, 308, 404}:
            return response
        response.raise_for_status()
        return response

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def upload_content_resumable(
    client: httpx.AsyncClient,
    token: str,
    upload_url: str,
    read_chunk: ChunkReader,
    mime_type: str,
    size_bytes: int,
    chunk_size: int,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    """Envia blocos e retoma pelo offset confirmado pelo Drive após falha de rede/5xx.

    A URL da sessão nunca é registrada: ela contém um identificador de upload sensível.
    """
    if chunk_size <= 0 or chunk_size % UPLOAD_CHUNK_GRANULARITY:
        raise ValueError("chunk de upload deve ser múltiplo positivo de 256 KiB")

    offset = 0
    transient_failures = 0
    while offset < size_bytes or size_bytes == 0:
        remaining = size_bytes - offset
        length = min(chunk_size, remaining) if size_bytes else 0
        # O último bloco pode ter qualquer tamanho, mas o backend do Drive já respondeu
        # incorretamente com storageQuotaExceeded quando recebeu uma cauda menor que a
        # granularidade. Juntar essa cauda ao bloco final continua dentro do protocolo e
        # evita o falso erro sem alterar o conteúdo ou o offset confirmado.
        if remaining > chunk_size and remaining - chunk_size < UPLOAD_CHUNK_GRANULARITY:
            length = remaining
        content = await read_chunk(offset, length) if length else b""
        if len(content) != length:
            raise OSError("arquivo local mudou ou terminou durante o upload")

        end = offset + length - 1
        content_range = f"bytes {offset}-{end}/{size_bytes}" if size_bytes else "bytes */0"
        try:
            response = await client.put(
                upload_url,
                content=content,
                headers={
                    **_auth_headers(token),
                    "Content-Type": mime_type,
                    "Content-Length": str(length),
                    "Content-Range": content_range,
                },
            )
            if response.status_code not in {200, 201, 308}:
                if logger is not None:
                    logger.error(
                        "storage.resumable_upload_rejected",
                        status_code=response.status_code,
                        reason=_google_error_reason(response),
                    )
                response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                exc.response.status_code in RETRYABLE_STATUS
            )
            if not retryable:
                raise
            transient_failures += 1
            if transient_failures > max_retries:
                raise RetryExhaustedError(transient_failures, exc) from exc
            delay = base_delay_s * (2 ** (transient_failures - 1))
            if logger is not None:
                logger.warning(
                    "storage.resumable_upload_retry",
                    attempt=transient_failures,
                    max_retries=max_retries,
                    delay_s=round(delay, 2),
                    error_type=type(exc).__name__,
                    status_code=(
                        exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                    ),
                )
            await asyncio.sleep(delay)
            status_response = await query_resumable_upload_status(
                client,
                token,
                upload_url,
                size_bytes,
                max_retries=max_retries,
                base_delay_s=base_delay_s,
                logger=logger,
            )
            if status_response.status_code == 404:
                raise ResumableUploadSessionExpiredError(
                    "sessão de upload resumable expirou"
                ) from exc
            if status_response.status_code in {200, 201}:
                return status_response.json()
            offset = _next_upload_offset(status_response)
            continue

        if response.status_code in {200, 201}:
            return response.json()

        next_offset = _next_upload_offset(response)
        if next_offset <= offset:
            transient_failures += 1
            if transient_failures > max_retries:
                raise RetryExhaustedError(
                    transient_failures,
                    RuntimeError("upload resumable não avançou no Drive"),
                )
        else:
            transient_failures = 0
        if next_offset > size_bytes:
            raise RuntimeError("Drive confirmou bytes além do tamanho local")
        offset = next_offset

    raise RuntimeError("Drive encerrou o upload resumable sem retornar metadata")


async def get_file_metadata(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.get(
            f"{FILES_URL}/{file_id}",
            params={"fields": METADATA_FIELDS, "supportsAllDrives": "true"},
            headers=_auth_headers(token),
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def download_stream(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
) -> AsyncIterator[bytes]:
    """Não usa with_retry (o corpo é um generator consumido pelo caller — retry teria que
    envolver o caller inteiro). Erros de status são levantados ao abrir a resposta."""
    async with client.stream(
        "GET",
        f"{FILES_URL}/{file_id}",
        params={"alt": "media", "supportsAllDrives": "true"},
        headers=_auth_headers(token),
    ) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            yield chunk


async def trash_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> None:
    async def _call():
        response = await client.patch(
            f"{FILES_URL}/{file_id}",
            params={"supportsAllDrives": "true"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"trashed": True},
        )
        response.raise_for_status()
        return None

    await with_retry(_call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger)


async def delete_file_permanently(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> None:
    async def _call():
        response = await client.delete(
            f"{FILES_URL}/{file_id}",
            params={"supportsAllDrives": "true"},
            headers=_auth_headers(token),
        )
        if response.status_code != 404:
            response.raise_for_status()
        return None

    await with_retry(_call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger)


async def copy_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    new_name: str,
    new_parent_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        response = await client.post(
            f"{FILES_URL}/{file_id}/copy",
            params={"fields": METADATA_FIELDS, "supportsAllDrives": "true"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"name": new_name, "parents": [new_parent_id]},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )


async def move_file(
    client: httpx.AsyncClient,
    token: str,
    file_id: str,
    new_name: str,
    old_parent_id: str,
    new_parent_id: str,
    *,
    max_retries: int,
    base_delay_s: float,
    logger=None,
) -> dict[str, Any]:
    async def _call():
        params = {"fields": METADATA_FIELDS, "supportsAllDrives": "true"}
        if old_parent_id != new_parent_id:
            params.update({"addParents": new_parent_id, "removeParents": old_parent_id})
        response = await client.patch(
            f"{FILES_URL}/{file_id}",
            params=params,
            headers={**_auth_headers(token), "Content-Type": "application/json"},
            json={"name": new_name},
        )
        response.raise_for_status()
        return response.json()

    return await with_retry(
        _call, max_retries=max_retries, base_delay_s=base_delay_s, logger=logger
    )
